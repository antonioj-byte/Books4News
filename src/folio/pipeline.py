"""Orquestador: ingesta → selección → verificación y guion → comprobación de hechos → informe.

Cada etapa guarda su resultado con folio.etapas para poder relanzar desde ella sin repetir la
ingesta ni gastar en llamadas ya hechas.
"""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import numpy as np
from folio import guion as guionista
from folio import arte, hechos, informe, seleccion, textos
from folio.etapas import ORDEN, Etapa, EtapasGuardadas
from folio.config import Config
from folio.historial import Historial
from folio.ingesta import agrupacion, resumen, rss
from folio.libros.verificacion import NoVerificado, Verificador
from folio.llm import LLM
from folio.modelos import (
    Articulo, FuenteNoticia, Historia, HistoriaElegida, HistoriaResumida, InformeDiario, LibroDescartado,
    LibroVerificado, Pieza, SeleccionJefe,
)
from folio.verificacion_texto import clave_libro

log = logging.getLogger(__name__)


def progreso(etapa: str) -> None:
    """Anuncia la etapa en curso. La web la lee del registro de la ejecución (líneas «ETAPA: …»)."""
    print(f"ETAPA: {etapa}", flush=True)


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

    def historias(self, articulos: list[Articulo], vectores, con_llm: bool) -> tuple[list[Historia], list[HistoriaResumida]]:
        """Agrupa, excluye las ya usadas y resume las que pasan al jefe de cultura."""
        p = self.cfg.pipeline
        todas = agrupacion.agrupar(articulos, vectores, p.agrupacion.umbral_similitud, p.agrupacion.umbral_fusion)
        candidatas = [h for h in todas if h.n_medios >= p.agrupacion.min_medios]
        usadas = self.historial.centroides_recientes(self.fecha, p.exclusion.dias_historias)

        al_jefe: list[Historia] = []
        excluidas: dict[str, str] = {}
        for h in candidatas:
            if len(al_jefe) >= p.seleccion.historias_al_jefe:
                break
            c = agrupacion.centroide(h, vectores)
            repetida = next(((f, t) for f, t, cu in usadas
                             if float(np.dot(c, cu)) >= p.exclusion.umbral_historia_repetida), None)
            if repetida:
                excluidas[h.id] = f"ya usada el {repetida[0]} («{repetida[1]}»)"
            else:
                al_jefe.append(h)

        if con_llm:
            self.avisos += resumen.resumir(self.llm, al_jefe)
        ids_jefe = {h.id for h in al_jefe}
        mostradas = [h for h in candidatas if h.id in ids_jefe or h.id in excluidas]
        resumidas = [HistoriaResumida(
            id=h.id, titular_es=h.titular_es or h.articulos[0].titulo, resumen_es=h.resumen_es,
            seccion=h.seccion, n_medios=h.n_medios, medios=h.medios, excluida=excluidas.get(h.id),
        ) for h in mostradas]
        self.stats = {
            "articulos": len(articulos),
            "medios": len({a.medio for a in articulos}),
            "historias": len(todas),
            "historias_multimedio": len(candidatas),
            "historias_al_jefe": len(al_jefe),
        }
        self._guardar_etapa(self.etapas.guardar_historias, al_jefe, resumidas, self.stats)
        return al_jefe, resumidas

    # --- Etapa 2: selección -------------------------------------------------

    def seleccion(self, al_jefe: list[Historia]) -> SeleccionJefe:
        sel, avisos = seleccion.seleccionar(self.llm, al_jefe)
        self.avisos += avisos
        self._guardar_etapa(self.etapas.guardar_seleccion, sel)
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
        tx = textos.textos_historia(self.cfg, h, self._puntuaciones(h, e))
        self.etapas.guardar_textos(h.id, tx)  # también en las pruebas: son las noticias, no un resultado
        return tx

    def _preparar(self, pieza: Pieza, h: Historia, reservados: set[str]) -> list[tuple[FuenteNoticia, str]] | None:
        """Verifica los libros y prepara los textos de una pieza. Va en orden, pieza a pieza: una
        pieza no puede repetir un libro de otra (`reservados`) y el modelo de embeddings, que se
        usa para elegir los textos, no se comparte entre hilos. None si no hay libro verificado."""
        e = pieza.eleccion
        libros, descartes = self._verificar_libros(e, reservados)
        pieza.libros, pieza.libros_descartados = libros, descartes
        if not libros:
            pieza.error = "Ningún libro candidato se pudo verificar"
            return None
        for l in libros:
            if l.edicion_es != "si":
                pieza.avisos.append(f"«{l.titulo_propuesto}»: edición española {l.edicion_es}")
            # Se reservan todos los verificados: los guiones se escriben a la vez y aún no se sabe cuál usará
            reservados.add(clave_libro(l.titulo_propuesto, l.autores[0] if l.autores else ""))
            if l.olid:
                reservados.add(l.olid)
        if not any(l.edicion_es == "si" for l in libros):
            pieza.avisos.append("Ningún libro verificado tiene edición española")
        textos_h = self.textos_de_historia(h, e)
        pieza.fuentes = [f for f, _ in textos_h]
        if not any(f.texto_completo for f in pieza.fuentes):
            pieza.avisos.append("Ningún texto completo disponible: el guionista solo tuvo titulares y entradillas")
        return textos_h

    def _escribir(self, pieza: Pieza, textos_h: list[tuple[FuenteNoticia, str]]) -> None:
        """Guion de una pieza (se ejecuta en paralelo con los de las demás)."""
        try:
            pieza.guion, avisos = guionista.escribir(self.llm, pieza.id, pieza.eleccion, textos_h, pieza.libros)
        except Exception as exc:
            pieza.error = str(exc)
            return
        pieza.avisos += avisos
        pieza.discrepancias_edicion = guionista.ajustar_libros(pieza.guion, pieza.libros)
        pieza.revisar_edicion = bool(pieza.discrepancias_edicion)
        pieza.revision_humana = [f"Afirma que no hay traducción ({a}): compruébalo antes de publicar"
                                 for a in guionista.afirmaciones_traduccion(pieza.guion)]
        pieza.estado = "propuesta"
        usados = [l for l in pieza.libros if any(guionista.libro_verificado(lg, [l]) for lg in pieza.guion.libros)]
        pieza.libros = usados or pieza.libros

    def piezas(self, sel: SeleccionJefe, al_jefe: list[Historia]) -> list[Pieza]:
        """Prepara las piezas en orden y escribe sus guiones a la vez. Si alguna falla, entra la
        siguiente historia de reserva, hasta tener tantas piezas como elegidas."""
        por_id = {h.id: h for h in al_jefe}
        objetivo = len(sel.elegidas)
        cola = [(e, False) for e in sel.elegidas] + [(e, True) for e in sel.reserva]
        if self.solo_pieza is not None:
            if not 1 <= self.solo_pieza <= len(sel.elegidas):
                raise ValueError(f"--solo-pieza debe estar entre 1 y {len(sel.elegidas)}")
            objetivo, cola = 1, [(sel.elegidas[self.solo_pieza - 1], False)]
        piezas: list[Pieza] = []
        reservados: set[str] = set()
        n = 0
        while cola and sum(p.estado == "propuesta" for p in piezas) < objetivo:
            faltan = objetivo - sum(p.estado == "propuesta" for p in piezas)
            lote: list[tuple[Pieza, list]] = []
            while cola and len(lote) < faltan:
                e, es_reserva = cola.pop(0)
                n = self.solo_pieza or n + 1
                h = por_id[e.historia_id]
                pieza = Pieza(id=f"{self.fecha}-{n}", fecha=self.fecha, estado="fallida", reserva=es_reserva,
                              historia_id=h.id, eleccion=e, n_medios=h.n_medios)
                piezas.append(pieza)
                progreso(f"Verificando libros y textos de la pieza {n}")
                log.info("Pieza %s: %s", pieza.id, e.titular)
                textos_h = self._preparar(pieza, h, reservados)
                if textos_h is not None:
                    lote.append((pieza, textos_h))
            if not lote:
                continue
            hechas = 0
            progreso(f"Escribiendo guiones (0 de {len(lote)})")
            with ThreadPoolExecutor(max_workers=len(lote)) as pool:
                for _ in as_completed([pool.submit(self._escribir, p, t) for p, t in lote]):
                    hechas += 1
                    progreso(f"Escribiendo guiones ({hechas} de {len(lote)})")
        return piezas

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

    def dirigir_arte(self, piezas: list[Pieza], al_jefe: list[Historia]) -> None:
        """Tono, imagen libre, cifra destacada y cubiertas de cada pieza. Una pieza tras otra, para
        que dos piezas del día no lleven la misma imagen (unos 10 s por pieza)."""
        por_id = {h.id: h for h in al_jefe}
        con_guion = [p for p in piezas if p.guion and p.estado != "fallida"]
        usadas: set[str] = set()
        for i, pieza in enumerate(con_guion):
            progreso(f"Dirección de arte ({i} de {len(con_guion)})")
            pieza.avisos = [a for a in pieza.avisos if not a.startswith("Director de arte:")]
            h = por_id.get(pieza.historia_id)
            try:
                pieza.arte = arte.dirigir(self.llm, self.cfg, pieza, h.seccion if h else None, usadas,
                                          [p.arte.portada for p in con_guion[:i] if p.arte])
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
        if self.solo_pieza is None and len(buenas) < len(sel.elegidas):
            self.avisos.append(f"Solo {len(buenas)} piezas válidas de {len(sel.elegidas)} previstas")
        if inicio >= 3:
            repetidas = "la comprobación de hechos y la dirección de arte" if inicio == 3 else "la dirección de arte"
            self.avisos.append(f"Solo se ha repetido {repetidas}: el coste del informe es solo el de esa etapa")
        return sel, piezas

    def _registrar_historial(self, buenas: list[Pieza], al_jefe: list[Historia], vectores) -> None:
        """Historias y libros usados hoy, para no repetirlos en los próximos días."""
        por_id = {h.id: h for h in al_jefe}
        self.historial.registrar_dia(
            self.fecha,
            [(p.historia_id, p.eleccion.titular, agrupacion.centroide(por_id[p.historia_id], vectores)) for p in buenas],
            [(l.titulo_propuesto, l.autores[0] if l.autores else "", l.olid) for p in buenas for l in p.libros],
        )

    def _avisos_de_prueba(self) -> None:
        if self.dev:
            self.avisos.insert(0, "MODO DESARROLLO: modelos baratos; sirve para probar la tubería, no la calidad del texto")
        if self.solo_pieza is not None:
            self.avisos.insert(0, f"Ejecución de prueba: solo la pieza {self.solo_pieza}; no se registra en el historial")
