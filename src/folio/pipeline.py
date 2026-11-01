"""Orquestador: ingesta → selección → verificación y guion → comprobación de hechos → informe.

Cada etapa guarda su resultado con folio.etapas para poder relanzar desde ella sin repetir la
ingesta ni gastar en llamadas ya hechas.
"""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import numpy as np
from folio import guion as guionista
from folio import arte, cajon, catalogo, hechos, informe, radar, seleccion, textos
from folio.imagenes import cubiertas
from folio.libros import citas
from folio.etapas import ORDEN, Etapa, EtapasGuardadas
from folio.config import Config
from folio.historial import Historial
from folio.ingesta import agrupacion, resumen, rss
from folio.libros.verificacion import NoVerificado, Verificador
from folio.llm import LLM
from folio.modelos import (
    SIN_LIBRO_OBLIGATORIO, Articulo, FuenteNoticia, Historia, HistoriaElegida, HistoriaResumida, InformeDiario,
    LibroDescartado, LibroVerificado, Pieza, SeleccionJefe,
)
from folio.verificacion_texto import clave_libro

log = logging.getLogger(__name__)


_RELOJ: dict = {}


def progreso(etapa: str) -> None:
    """Anuncia la etapa en curso. La web la lee del registro de la ejecución (líneas «ETAPA: …»). Cada línea
    lleva lo que duró la etapa anterior, para saber dónde se va el tiempo («TIEMPO: 12,3 s · Leyendo…»)."""
    import time
    ahora = time.monotonic()
    if "etapa" in _RELOJ:
        print(f"TIEMPO: {ahora - _RELOJ['inicio']:.1f} s · {_RELOJ['etapa']}", flush=True)
    _RELOJ.update(etapa=etapa, inicio=ahora)
    print(f"ETAPA: {etapa}", flush=True)



def anio_de_publicacion(l: LibroVerificado) -> int | None:
    """El año más reciente entre la primera edición y la edición española verificada (una traducción
    nueva también es novedad para el lector de Folio)."""
    anios = [l.anio_primera_edicion] if l.anio_primera_edicion else []
    if l.edicion_es == "si" and l.edicion_es_detalle and (l.edicion_es_detalle.anio or "")[:4].isdigit():
        anios.append(int(l.edicion_es_detalle.anio[:4]))
    return max(anios) if anios else None


def fuera_de_novedad(l: LibroVerificado, desde: int) -> str | None:
    """Motivo de descarte si el libro no es novedad (publicado antes de `desde` o sin año verificado)."""
    anio = anio_de_publicacion(l)
    if anio is None:
        return "sin año de publicación verificado: no se puede comprobar que sea novedad"
    return None if anio >= desde else f"publicado en {anio}: Folio va de novedades (desde {desde})"

class Pipeline:
    def __init__(self, cfg: Config, fecha: str, llm: LLM | None = None,
                 verificador: Verificador | None = None, historial: Historial | None = None,
                 dev: bool = False, solo_pieza: int | None = None):
        """`dev` y `solo_pieza` son ejecuciones de prueba: no registran el día en el historial, no
        sobrescriben la selección ni las piezas guardadas y escriben el informe en su propia carpeta."""
        self.cfg = cfg
        self.fecha = fecha
        self.cache = cfg.dir_cache(fecha)
        self.llm = llm or LLM(cfg)
        self.verificador = verificador
        self.historial = historial or Historial(cfg.ruta_db)
        self.avisos: list[str] = []
        self.dev = dev
        self.solo_pieza = solo_pieza
        self.prueba = dev or solo_pieza is not None
        self.etapas = EtapasGuardadas(self.cache)
        # Estado de la ejecución: lo rellenan las etapas
        self.stats: dict = {}
        self.vectores_articulos: dict[str, np.ndarray] | None = None
        self.radar: list[HistoriaElegida] = []     # temas del radar del libro (folio.radar)
        self._embedder: agrupacion.Embedder | None = None

    @property
    def dir_informe(self):
        if self.dev:
            return self.cfg.dir_informes / f"{self.fecha}-dev"
        if self.solo_pieza is not None:
            return self.cfg.dir_informes / self.fecha / f"solo-pieza-{self.solo_pieza}"
        return self.cfg.dir_informes / self.fecha

    def _guardar_etapa(self, guardar, *datos) -> None:
        """Las ejecuciones de prueba leen las etapas guardadas, pero no las sobrescriben."""
        if not self.prueba:
            guardar(*datos)

    # --- Etapa 1: ingesta y agrupación ---------------------------------------

    def ingesta(self, usar_cache: bool) -> list[Articulo]:
        if usar_cache and self.etapas.hay_articulos():
            return self.etapas.articulos()
        articulos, errores = rss.ingerir(self.cfg)
        self.avisos += [f"Feed fallido: {e}" for e in errores]
        self._guardar_etapa(self.etapas.guardar_articulos, articulos)
        return articulos

    @property
    def embedder(self) -> agrupacion.Embedder:
        """Un único modelo de embeddings por ejecución: cargarlo cuesta 2 GB de memoria."""
        if self._embedder is None:
            self._embedder = agrupacion.Embedder(self.cfg.pipeline.agrupacion.modelo_embeddings, self.cache)
        return self._embedder

    def vectores(self, articulos: list[Articulo]) -> dict[str, np.ndarray]:
        return self.embedder.vectores({a.id: agrupacion.texto_articulo(a) for a in articulos})

    def _no_repetidas(self, candidatas: list[Historia], vectores, maximo: int, usadas,
                      excluidas: dict[str, str]) -> list[Historia]:
        """Las primeras `maximo` candidatas que no se han usado en los últimos días."""
        p = self.cfg.pipeline
        elegidas: list[Historia] = []
        for h in candidatas:
            if len(elegidas) >= maximo:
                break
            c = agrupacion.centroide(h, vectores)
            repetida = next(((f, t) for f, t, cu in usadas
                             if float(np.dot(c, cu)) >= p.exclusion.umbral_historia_repetida), None)
            if repetida:
                excluidas[h.id] = f"ya usada el {repetida[0]} («{repetida[1]}»)"
            else:
                elegidas.append(h)
        return elegidas

    def _del_libro(self, editoriales: list[Articulo], vectores, usadas, excluidas: dict[str, str],
                   con_llm: bool) -> list[Historia]:
        """Carril editorial: grupos más estrictos y sin fusión, ordenados por medios, medios tier 1 y
        fecha. Se resumen el doble de los que se necesitan y se quedan los que tratan de libros."""
        p = self.cfg.pipeline
        if not editoriales:
            return []
        grupos = agrupacion.agrupar(editoriales, vectores, p.agrupacion.umbral_similitud_editorial, None)
        grupos.sort(key=lambda h: (h.n_medios, sum(a.tier == 1 for a in h.articulos),
                                   h.ultima_publicacion.timestamp() if h.ultima_publicacion else 0), reverse=True)
        maximo = p.seleccion.historias_editoriales
        # Se resumen el doble de las que ve el jefe (o las que pide el radar, que ve también las que no le llegan)
        resumir = max(2 * maximo, p.radar.historias if p.radar.activo else 0)
        del_libro = self._no_repetidas(grupos, vectores, resumir if con_llm else maximo, usadas, excluidas)
        for h in del_libro:
            h.carril = "editorial"
        if con_llm:
            self.avisos += resumen.resumir(self.llm, del_libro)
            del_libro = [h for h in del_libro if h.sobre_libros is not False]
        for h in del_libro[maximo:]:
            h.carril = "radar"          # no pasan al jefe, pero sí al radar del libro
        return del_libro

    def _del_cajon(self) -> list[Historia]:
        """Cajón de curiosidades: las historias sin percha que no se han usado en los últimos días
        (`seleccion.dias_curiosidades`). Nada si el reparto no pide ninguna."""
        p = self.cfg.pipeline.seleccion
        if not p.reparto.get("curiosidad"):
            return []
        try:
            from folio import nevera
            return cajon.disponibles(self.cfg.raiz, self.historial.curiosidades_recientes(self.fecha, p.dias_curiosidades),
                                     nevera.ruta(self.cfg))
        except Exception as exc:
            self.avisos.append(f"No se pudo leer el cajón de curiosidades: {exc}")
            return []

    def _del_catalogo(self) -> list[Historia]:
        """Formato «recomendado»: novedades de las editoriales independientes (folio.catalogo), sin los libros
        usados en los últimos días. Nada si el reparto no pide ninguno."""
        if not self.cfg.pipeline.seleccion.reparto.get("recomendado"):
            return []
        progreso("Leyendo el catálogo de las editoriales independientes")
        dias = self.cfg.pipeline.exclusion.dias_libros
        try:
            libros, avisos = catalogo.candidatos(
                self.cfg, date.fromisoformat(self.fecha),
                lambda t, a: self.historial.libro_usado(self.fecha, dias, t, a, None) is not None)
        except Exception as exc:
            self.avisos.append(f"No se pudo leer el catálogo de las independientes: {type(exc).__name__}: {exc}")
            return []
        self.avisos += avisos
        return libros

    def historias(self, articulos: list[Articulo], vectores, con_llm: bool) -> tuple[list[Historia], list[HistoriaResumida]]:
        """Agrupa, excluye las ya usadas y resume las que pasan al jefe de cultura.

        Dos carriles: la actualidad (historias de al menos `min_medios` medios) y el mundo del libro
        (config/fuentes_editoriales.yaml), que se agrupa aparte y entra aunque lo cubra un solo
        medio: es contexto para el jefe de cultura, que puede elegir una si es buena."""
        p = self.cfg.pipeline
        actualidad = [a for a in articulos if a.carril == "actualidad"]
        editoriales = [a for a in articulos if a.carril == "editorial"]
        todas = agrupacion.agrupar(actualidad, vectores, p.agrupacion.umbral_similitud, p.agrupacion.umbral_fusion)
        candidatas = [h for h in todas if h.n_medios >= p.agrupacion.min_medios]
        usadas = self.historial.centroides_recientes(self.fecha, p.exclusion.dias_historias)
        excluidas: dict[str, str] = {}
        al_jefe = self._no_repetidas(candidatas, vectores, p.seleccion.historias_al_jefe, usadas, excluidas)

        if con_llm:
            self.avisos += resumen.resumir(self.llm, al_jefe)
        del_libro = self._del_libro(editoriales, vectores, usadas, excluidas, con_llm)
        candidatas += del_libro
        al_jefe += del_libro
        del_cajon = self._del_cajon()
        al_jefe += del_cajon
        del_catalogo = self._del_catalogo()
        al_jefe += del_catalogo
        ids_jefe = {h.id for h in al_jefe}
        mostradas = [h for h in candidatas if h.id in ids_jefe or h.id in excluidas]
        resumidas = [HistoriaResumida(
            id=h.id, titular_es=h.titular_es or h.articulos[0].titulo, resumen_es=h.resumen_es,
            seccion=h.seccion, n_medios=h.n_medios, medios=h.medios, excluida=excluidas.get(h.id), carril=h.carril,
        ) for h in mostradas]
        self.stats = {
            "articulos": len(articulos),
            "medios": len({a.medio for a in articulos}),
            "historias": len(todas),
            "historias_multimedio": len(candidatas),
            "historias_al_jefe": len(al_jefe) - len(del_libro) - len(del_cajon) - len(del_catalogo),
            "articulos_editoriales": len(editoriales),
            "historias_editoriales_al_jefe": sum(h.carril == "editorial" for h in del_libro),
            "historias_solo_radar": sum(h.carril == "radar" for h in del_libro),
            "libros_del_catalogo": len(del_catalogo),
            "curiosidades_al_jefe": len(del_cajon),
        }
        self._guardar_etapa(self.etapas.guardar_historias, al_jefe, resumidas, self.stats)
        return al_jefe, resumidas

    # --- Etapa 2: selección -------------------------------------------------

    def seleccion(self, al_jefe: list[Historia]) -> SeleccionJefe:
        sel, avisos = seleccion.seleccionar(self.llm, al_jefe, self.fecha)
        self.avisos += avisos
        self._guardar_etapa(self.etapas.guardar_seleccion, sel)
        try:
            self.radar, avisos_radar = radar.temas(self.llm, al_jefe, sel)
            self.avisos += avisos_radar
        except Exception as exc:
            self.radar = []
            self.avisos.append(f"Radar del libro: no se pudo ({type(exc).__name__}: {exc})")
        self._guardar_etapa(self.etapas.guardar_radar, self.radar)
        return sel

    # --- Etapa 3: verificación y guion --------------------------------------

    def _verificar_libros(self, e: HistoriaElegida, ya_usados: set[str]) -> tuple[list[LibroVerificado], list[LibroDescartado]]:
        if self.verificador is None:
            self.verificador = Verificador(self.cfg)
        dias = self.cfg.pipeline.exclusion.dias_libros
        ok, descartes = [], []
        for c in e.libros_candidatos:
            try:
                l = self.verificador.verificar(c)
            except NoVerificado as exc:
                descartes.append(LibroDescartado(titulo=c.titulo, autor=c.autor, motivo=exc.motivo))
                continue
            viejo = fuera_de_novedad(l, seleccion.anio_minimo(self.fecha, self.cfg.pipeline.seleccion.antiguedad_libros))
            if viejo:
                descartes.append(LibroDescartado(titulo=c.titulo, autor=c.autor, motivo=viejo))
                continue
            clave = clave_libro(c.titulo, c.autor)
            usado = self.historial.libro_usado(self.fecha, dias, c.titulo, c.autor, l.olid)
            if usado:
                descartes.append(LibroDescartado(titulo=c.titulo, autor=c.autor, motivo=f"ya usado el {usado}"))
            elif clave in ya_usados or (l.olid and l.olid in ya_usados):
                descartes.append(LibroDescartado(titulo=c.titulo, autor=c.autor, motivo="ya usado hoy en otra pieza"))
            else:
                ok.append(l)
        return ok, descartes

    def vector_texto(self, texto: str) -> np.ndarray:
        """Embedding de un texto suelto, con la misma caché que los artículos."""
        clave = "texto:" + hashlib.sha1(texto.encode()).hexdigest()[:12]
        return self.embedder.vectores({clave: texto})[clave]

    def _puntuaciones(self, h: Historia, e: HistoriaElegida | None) -> dict[str, float] | None:
        """Similitud de cada artículo con el centro del grupo y con el hecho principal («de qué se habla»)."""
        vectores = self.vectores_articulos
        if not vectores or not all(a.id in vectores for a in h.articulos):
            return None
        centro = agrupacion.centroide(h, vectores)
        eje = centro
        if e is not None:
            eje = self.vector_texto(f"{e.titular}. {e.de_que_se_habla}")
        return {a.id: 0.5 * float(np.dot(vectores[a.id], centro)) + 0.5 * float(np.dot(vectores[a.id], eje))
                for a in h.articulos}

    def textos_de_historia(self, h: Historia, e: HistoriaElegida | None = None) -> list[tuple[FuenteNoticia, str]]:
        """Textos de la historia, congelados en data/cache/<fecha>/textos/ la primera vez.

        Los medios cambian sus páginas y a veces bloquean (403): relanzar el mismo día con los
        mismos textos permite comparar guiones y comprobar hechos sobre lo que vio el guionista.
        Para descargarlos de nuevo, se borra el archivo.
        """
        guardados = self.etapas.textos(h.id)
        if guardados is not None:
            return guardados
        ficha = catalogo.ficha_guardada(self.cfg, h.id) if catalogo.es_del_catalogo(h.id) else None
        tx = catalogo.textos(ficha) if ficha else textos.textos_historia(self.cfg, h, self._puntuaciones(h, e))
        self.etapas.guardar_textos(h.id, tx)  # también en las pruebas: son las noticias, no un resultado
        return tx

    def _verificar(self, pieza: Pieza, reservados: set[str]) -> bool:
        """Verifica los libros de una propuesta. Va en orden, propuesta a propuesta: una no puede
        repetir un libro de otra (`reservados`). False si ningún candidato pasa."""
        e = pieza.eleccion
        libros, descartes = self._verificar_libros(e, reservados)
        if not libros and e.formato == "recomendado" and catalogo.es_del_catalogo(pieza.historia_id):
            # Novedad reciente que Open Library y Google Books aún no tienen: vale la ficha de las librerías
            ficha = catalogo.ficha_guardada(self.cfg, pieza.historia_id)
            if ficha:
                libros = [catalogo.libro_de_ficha(ficha)]
        pieza.libros, pieza.libros_descartados = libros, descartes
        if not libros and e.formato in SIN_LIBRO_OBLIGATORIO:
            # La curiosidad del cajón y los temas del radar no necesitan libro (decisión del usuario, 1/11)
            if e.libros_candidatos:
                pieza.avisos.append("Ningún libro candidato se pudo verificar: la pieza sale sin libro")
            return True
        if not libros:
            pieza.error = "Ningún libro candidato se pudo verificar"
            return False
        for l in libros:
            if l.edicion_es != "si":
                pieza.avisos.append(f"«{l.titulo_propuesto}»: edición española {l.edicion_es}")
            # Se reservan todos los verificados: los guiones se escriben a la vez y aún no se sabe cuál usará
            reservados.add(clave_libro(l.titulo_propuesto, l.autores[0] if l.autores else ""))
            if l.olid:
                reservados.add(l.olid)
        if not any(l.edicion_es == "si" for l in libros):
            pieza.avisos.append("Ningún libro verificado tiene edición española")
        return True

    def _cubiertas_de(self, pieza: Pieza) -> None:
        """Las cubiertas de los libros verificados, para enseñarlas en la mesa antes de escribir nada."""
        for l in pieza.libros:
            try:
                cubiertas.buscar(l, self.cache.parent, self.cfg.google_books_api_key)
            except Exception as exc:
                pieza.avisos.append(f"No se pudo buscar la cubierta de {l.titulo_propuesto}: {type(exc).__name__}")

    def _textos(self, pieza: Pieza, h: Historia) -> list[tuple[FuenteNoticia, str]]:
        """Los textos de los medios para el guion. En orden, no en paralelo: el modelo de embeddings,
        que se usa para elegirlos, no se comparte entre hilos."""
        textos_h = self.textos_de_historia(h, pieza.eleccion)
        pieza.fuentes = [f for f, _ in textos_h]
        if not any(f.texto_completo for f in pieza.fuentes):
            pieza.avisos.append("Ningún texto completo disponible: el guionista solo tuvo titulares y entradillas")
        return textos_h

    @property
    def _verificar_cita(self):
        """Busca las citas literales en el texto del libro (Google Books); sin clave de Google Books, ninguna pasa."""
        if self.verificador is None:
            self.verificador = Verificador(self.cfg)
        return citas.verificador_google_books(self.verificador.gb) if self.verificador.gb else None

    def _escribir(self, pieza: Pieza, textos_h: list[tuple[FuenteNoticia, str]]) -> None:
        """Guion de una pieza (se ejecuta en paralelo con los de las demás)."""
        try:
            pieza.guion, avisos, pieza.citas = guionista.escribir(self.llm, pieza.id, pieza.eleccion, textos_h, pieza.libros,
                                                                  self._verificar_cita)
        except Exception as exc:
            pieza.error = str(exc)
            return
        pieza.avisos += avisos
        pieza.discrepancias_edicion = guionista.ajustar_libros(pieza.guion, pieza.libros)
        pieza.revisar_edicion = bool(pieza.discrepancias_edicion)
        pieza.revision_humana = [f"Afirma que no hay traducción ({a}): compruébalo antes de publicar"
                                 for a in guionista.afirmaciones_traduccion(pieza.guion)]
        pieza.estado = "propuesta"
        # En el orden del guion: el primero es el libro principal (el de la portada y el retrato)
        usados: list[LibroVerificado] = []          # las fichas no son hashables: sin dict.fromkeys
        for lg in pieza.guion.libros:
            v = guionista.libro_verificado(lg, pieza.libros)
            if v and all(v is not u for u in usados):
                usados.append(v)
        pieza.libros = usados or pieza.libros

    def piezas(self, sel: SeleccionJefe, al_jefe: list[Historia]) -> list[Pieza]:
        """La mesa del día: cada propuesta con sus libros verificados y sus cubiertas, y el guion de
        las primeras (`seleccion.desarrollar_al_inicio`, por orden de preferencia). Las demás quedan
        «pendiente» hasta que se pulse «Proceder» en la web (`folio desarrollar`). Si un guion falla,
        se escribe el de la siguiente propuesta con libro."""
        por_id = {h.id: h for h in al_jefe}
        cola = [(e, False) for e in sel.elegidas] + [(e, True) for e in sel.reserva]
        objetivo = min(self.cfg.pipeline.seleccion.desarrollar_al_inicio, len(sel.elegidas))
        if self.solo_pieza is not None:
            if not 1 <= self.solo_pieza <= len(sel.elegidas):
                raise ValueError(f"--solo-pieza debe estar entre 1 y {len(sel.elegidas)}")
            objetivo, cola = 1, [(sel.elegidas[self.solo_pieza - 1], False)]
        piezas: list[Pieza] = []
        reservados: set[str] = set()
        for i, (e, es_reserva) in enumerate(cola, 1):
            n = self.solo_pieza or i
            h = por_id[e.historia_id]
            pieza = Pieza(id=f"{self.fecha}-{n}", fecha=self.fecha, estado="fallida", reserva=es_reserva,
                          historia_id=h.id, eleccion=e, n_medios=h.n_medios)
            piezas.append(pieza)
            progreso(f"Verificando los libros de la propuesta {i} de {len(cola)}")
            log.info("Propuesta %s (%s): %s", pieza.id, e.formato, e.titular)
            if self._verificar(pieza, reservados):
                pieza.estado = "pendiente"
                self._cubiertas_de(pieza)
        if self.solo_pieza is None:
            for j, e in enumerate(self.radar, len(cola) + 1):
                h = por_id.get(e.historia_id)
                if h:
                    piezas.append(Pieza(id=f"{self.fecha}-{j}", fecha=self.fecha, estado="pendiente", radar=True,
                                        historia_id=h.id, eleccion=e, n_medios=h.n_medios))
        por_escribir = [p for p in piezas if p.estado == "pendiente" and not p.radar]
        while por_escribir and sum(p.estado == "propuesta" for p in piezas) < objetivo:
            faltan = objetivo - sum(p.estado == "propuesta" for p in piezas)
            lote = [(p, self._textos(p, por_id[p.historia_id])) for p in por_escribir[:faltan]]
            por_escribir = por_escribir[faltan:]
            hechas = 0
            progreso(f"Escribiendo guiones (0 de {len(lote)})")
            with ThreadPoolExecutor(max_workers=len(lote)) as pool:
                for _ in as_completed([pool.submit(self._escribir, p, t) for p, t in lote]):
                    hechas += 1
                    progreso(f"Escribiendo guiones ({hechas} de {len(lote)})")
            for p, _ in lote:
                if p.estado != "propuesta":
                    p.estado = "fallida"
        return piezas

    def desarrollar(self, pieza: Pieza, al_jefe: list[Historia], otras: list[Pieza]) -> Pieza:
        """«Proceder» en la web: escribe la pieza de una propuesta pendiente (textos, guion, hechos y
        arte), sin tocar las demás del día (`otras`: las ya desarrolladas, para no repetir imagen ni
        composición). Si el guion falla, la pieza vuelve como «fallida» con el error."""
        h = {x.id: x for x in al_jefe}[pieza.historia_id]
        pieza.error = None
        self._escribir(pieza, self._textos(pieza, h))
        if pieza.estado != "propuesta":
            pieza.estado = "fallida"
            return pieza
        self.comprobar_hechos([pieza], al_jefe)
        self.dirigir_arte([*[o for o in otras if o.guion and o.id != pieza.id], pieza], al_jefe, solo={pieza.id})
        return pieza

    # --- Etapa 4: comprobación de hechos ------------------------------------

    def comprobar_hechos(self, piezas: list[Pieza], al_jefe: list[Historia]) -> None:
        """Comprobación de hechos de todas las piezas a la vez (los textos se leen antes, en orden)."""
        por_id = {h.id: h for h in al_jefe}
        con_guion = [(p, self.textos_de_historia(por_id[p.historia_id])) for p in piezas if p.guion]

        def una(pieza: Pieza, textos_h) -> None:
            pieza.avisos = [a for a in pieza.avisos if not a.startswith("No se pudo comprobar los hechos")]
            try:
                pieza.hechos = hechos.comprobar(self.llm, pieza.id, pieza.guion, textos_h)
            except Exception as exc:
                pieza.hechos = []
                pieza.avisos.append(f"No se pudo comprobar los hechos: {exc}")

        if not con_guion:
            return
        hechas = 0
        progreso(f"Comprobando hechos (0 de {len(con_guion)})")
        with ThreadPoolExecutor(max_workers=len(con_guion)) as pool:
            for _ in as_completed([pool.submit(una, p, t) for p, t in con_guion]):
                hechas += 1
                progreso(f"Comprobando hechos ({hechas} de {len(con_guion)})")

    # --- Etapa 5: director de arte -------------------------------------------

    def dirigir_arte(self, piezas: list[Pieza], al_jefe: list[Historia], solo: set[str] | None = None) -> None:
        """Tono, imagen libre, cifra destacada y cubiertas de cada pieza. Una pieza tras otra, para
        que dos piezas del día no lleven la misma imagen (unos 10 s por pieza). Con `solo`, se dirige
        únicamente esas piezas: las demás cuentan para no repetir imagen ni composición."""
        por_id = {h.id: h for h in al_jefe}
        con_guion = [p for p in piezas if p.guion and p.estado != "fallida"]
        usadas: set[str] = {x for p in con_guion if solo and p.id not in solo and p.arte
                            for x in (p.arte.imagen, p.arte.imagen_noticia) if x}
        for i, pieza in enumerate(con_guion):
            if solo is not None and pieza.id not in solo:
                continue
            progreso(f"Dirección de arte ({i} de {len(con_guion)})")
            pieza.avisos = [a for a in pieza.avisos if not a.startswith("Director de arte:")]
            h = por_id.get(pieza.historia_id)
            try:
                pieza.arte = arte.dirigir(self.llm, self.cfg, pieza, h.seccion if h else None, usadas,
                                          [f"{p.arte.portada} en {p.arte.acento or 'blanco y negro'}"
                                           + (f" (sin foto: {p.arte.sin_foto.recurso})" if p.arte.sin_foto else "")
                                           for p in con_guion if p.arte and p.id != pieza.id and (solo is not None or con_guion.index(p) < i)],
                                          self.cache / "prueba" if self.prueba else None,
                                          [p.arte.registro for p in con_guion
                                           if p.arte and p.id != pieza.id and (solo is not None or con_guion.index(p) < i)])
            except Exception as exc:
                pieza.arte = None
                pieza.avisos.append(f"Director de arte: no se pudo ({type(exc).__name__}: {exc}); sale sin imagen")
        if con_guion:
            progreso(f"Dirección de arte ({len(con_guion)} de {len(con_guion)})")

    # --- Ejecución completa -------------------------------------------------

    def ejecutar(self, desde: Etapa = "ingesta", sin_llm: bool = False) -> tuple[InformeDiario, tuple]:
        """Ejecuta el pipeline desde la etapa `desde`, leyendo de data/cache/<fecha>/ las anteriores."""
        inicio = ORDEN[desde]
        articulos, vectores = self._noticias(inicio)
        al_jefe, resumidas = self._historias_del_dia(inicio, articulos, vectores, sin_llm)
        sel, piezas = (None, []) if sin_llm else self._piezas_del_dia(inicio, al_jefe, vectores)
        self._avisos_de_prueba()
        inf = InformeDiario(
            fecha=self.fecha, generado_en=datetime.now(timezone.utc), stats=self.stats,
            top_historias=resumidas, seleccion=sel, piezas=piezas, trazas=self.llm.trazas,
            coste_total_usd=round(sum(t.coste_usd for t in self.llm.trazas), 4), avisos=self.avisos,
        )
        progreso("Guardando el informe")
        rutas = informe.escribir(inf, self.dir_informe)
        if not self.prueba and not sin_llm and piezas:
            # La web lee las ejecuciones de la base de datos (Fase 3)
            from folio.almacen import Almacen
            Almacen(self.cfg.ruta_db).registrar(inf)
        return inf, rutas

    def _noticias(self, inicio: int) -> tuple[list[Articulo], dict[str, np.ndarray]]:
        progreso("Leyendo las noticias" if inicio == 0 else "Cargando las noticias guardadas")
        articulos = self.ingesta(usar_cache=inicio > 0)
        progreso("Agrupando las noticias por evento (embeddings)")
        vectores = self.vectores(articulos)
        self.vectores_articulos = vectores
        return articulos, vectores

    def _historias_del_dia(self, inicio: int, articulos: list[Articulo], vectores,
                           sin_llm: bool) -> tuple[list[Historia], list[HistoriaResumida]]:
        if inicio <= 1 or sin_llm:
            if not sin_llm:
                progreso("Resumiendo las historias")
            return self.historias(articulos, vectores, con_llm=not sin_llm)
        al_jefe, resumidas, self.stats = self.etapas.historias()
        return al_jefe, resumidas

    def _piezas_del_dia(self, inicio: int, al_jefe: list[Historia], vectores) -> tuple[SeleccionJefe, list[Pieza]]:
        """Selección, piezas y comprobación de hechos (cada una, nueva o la guardada)."""
        if inicio <= 1:
            progreso("Eligiendo las historias (jefe de cultura)")
            sel = self.seleccion(al_jefe)
        else:
            sel = self.etapas.seleccion()
            self.radar = self.etapas.radar()
        if inicio <= 2:
            piezas = self.piezas(sel, al_jefe)
            self._guardar_etapa(self.etapas.guardar_piezas, piezas)
        else:
            piezas = self.etapas.piezas()
        if inicio <= 3:
            self.comprobar_hechos(piezas, al_jefe)
            self._guardar_etapa(self.etapas.guardar_piezas, piezas)
        self.dirigir_arte(piezas, al_jefe)
        self._guardar_etapa(self.etapas.guardar_piezas, piezas)
        buenas = [p for p in piezas if p.estado == "propuesta"]
        if inicio <= 2 and not self.prueba:
            self._registrar_historial(buenas, al_jefe, vectores)
        previstas = min(self.cfg.pipeline.seleccion.desarrollar_al_inicio, len(sel.elegidas))
        if self.solo_pieza is None and len(buenas) < previstas:
            self.avisos.append(f"Solo {len(buenas)} piezas escritas de {previstas} previstas")
        if inicio >= 3:
            repetidas = "la comprobación de hechos y la dirección de arte" if inicio == 3 else "la dirección de arte"
            self.avisos.append(f"Solo se ha repetido {repetidas}: el coste del informe es solo el de esa etapa")
        return sel, piezas

    def _registrar_historial(self, buenas: list[Pieza], al_jefe: list[Historia], vectores) -> None:
        """Historias y libros usados hoy, para no repetirlos en los próximos días."""
        por_id = {h.id: h for h in al_jefe}
        noticias = [p for p in buenas if not cajon.es_del_cajon(p.historia_id) and not catalogo.es_del_catalogo(p.historia_id)]
        self.historial.registrar_dia(
            self.fecha,
            [(p.historia_id, p.eleccion.titular, agrupacion.centroide(por_id[p.historia_id], vectores)) for p in noticias],
            [(l.titulo_propuesto, l.autores[0] if l.autores else "", l.olid) for p in buenas for l in p.libros],
            [p.historia_id.removeprefix(cajon.PREFIJO) for p in buenas if cajon.es_del_cajon(p.historia_id)],
        )

    def _avisos_de_prueba(self) -> None:
        if self.dev:
            self.avisos.insert(0, "MODO DESARROLLO: modelos baratos; sirve para probar la tubería, no la calidad del texto")
        if self.solo_pieza is not None:
            self.avisos.insert(0, f"Ejecución de prueba: solo la pieza {self.solo_pieza}; no se registra en el historial")
