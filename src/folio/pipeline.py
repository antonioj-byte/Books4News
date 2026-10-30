"""Orquestador de la Fase 1: ingesta → selección → verificación → guion → informe.

Cada etapa guarda su resultado en data/cache/<fecha>/ para poder relanzar desde una etapa
(`--desde seleccion`, `--desde guion`) sin repetir la ingesta ni gastar en llamadas ya hechas.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

import numpy as np
from pydantic import TypeAdapter

from folio import guion as guionista
from folio import informe, seleccion, textos
from folio.config import Config
from folio.historial import Historial
from folio.ingesta import agrupacion, resumen, rss
from folio.libros.verificacion import NoVerificado, Verificador
from folio.llm import LLM
from folio.modelos import (
    Articulo, Historia, HistoriaElegida, HistoriaResumida, InformeDiario, LibroDescartado,
    LibroVerificado, Pieza, SeleccionJefe,
)
from folio.verificacion_texto import clave_libro

log = logging.getLogger(__name__)

Etapa = Literal["ingesta", "seleccion", "guion"]
_ORDEN = {"ingesta": 0, "seleccion": 1, "guion": 2}


def _guardar(ruta, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _cargar(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}: ejecuta antes las etapas anteriores")
    return json.loads(ruta.read_text(encoding="utf-8"))


class Pipeline:
    def __init__(self, cfg: Config, fecha: str, llm: LLM | None = None,
                 verificador: Verificador | None = None, historial: Historial | None = None):
        self.cfg = cfg
        self.fecha = fecha
        self.cache = cfg.dir_cache(fecha)
        self.llm = llm or LLM(cfg)
        self.verificador = verificador
        self.historial = historial or Historial(cfg.ruta_db)
        self.avisos: list[str] = []

    # --- Etapa 1: ingesta y agrupación ---------------------------------------

    def ingesta(self, usar_cache: bool) -> list[Articulo]:
        ruta = self.cache / "articulos.json"
        if usar_cache and ruta.exists():
            return TypeAdapter(list[Articulo]).validate_python(_cargar(ruta))
        articulos, errores = rss.ingerir(self.cfg)
        self.avisos += [f"Feed fallido: {e}" for e in errores]
        _guardar(ruta, [a.model_dump(mode="json") for a in articulos])
        return articulos

    def vectores(self, articulos: list[Articulo]) -> dict[str, np.ndarray]:
        emb = agrupacion.Embedder(self.cfg.pipeline["agrupacion"]["modelo_embeddings"], self.cache)
        return emb.vectores({a.id: agrupacion.texto_articulo(a) for a in articulos})

    def historias(self, articulos: list[Articulo], vectores, con_llm: bool) -> tuple[list[Historia], list[HistoriaResumida]]:
        """Agrupa, excluye las ya usadas y resume las que pasan al jefe de cultura."""
        p = self.cfg.pipeline
        todas = agrupacion.agrupar(articulos, vectores, p["agrupacion"]["umbral_similitud"])
        candidatas = [h for h in todas if h.n_medios >= p["agrupacion"]["min_medios"]]
        usadas = self.historial.centroides_recientes(self.fecha, p["exclusion"]["dias_historias"])

        al_jefe: list[Historia] = []
        excluidas: dict[str, str] = {}
        for h in candidatas:
            if len(al_jefe) >= p["seleccion"]["historias_al_jefe"]:
                break
            c = agrupacion.centroide(h, vectores)
            repetida = next(((f, t) for f, t, cu in usadas
                             if float(np.dot(c, cu)) >= p["exclusion"]["umbral_historia_repetida"]), None)
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
        _guardar(self.cache / "historias.json", {
            "al_jefe": [h.model_dump(mode="json") for h in al_jefe],
            "resumidas": [r.model_dump(mode="json") for r in resumidas],
            "stats": self.stats,
        })
        return al_jefe, resumidas

    # --- Etapa 2: selección -------------------------------------------------

    def seleccion(self, al_jefe: list[Historia]) -> SeleccionJefe:
        sel, avisos = seleccion.seleccionar(self.llm, al_jefe)
        self.avisos += avisos
        _guardar(self.cache / "seleccion.json", sel.model_dump(mode="json"))
        return sel

    # --- Etapa 3: verificación y guion --------------------------------------

    def _verificar_libros(self, e: HistoriaElegida, ya_usados: set[str]) -> tuple[list[LibroVerificado], list[LibroDescartado]]:
        if self.verificador is None:
            self.verificador = Verificador(self.cfg)
        dias = self.cfg.pipeline["exclusion"]["dias_libros"]
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

    def piezas(self, sel: SeleccionJefe, al_jefe: list[Historia]) -> list[Pieza]:
        por_id = {h.id: h for h in al_jefe}
        objetivo = len(sel.elegidas)
        cola = [(e, False) for e in sel.elegidas] + [(e, True) for e in sel.reserva]
        piezas: list[Pieza] = []
        libros_hoy: set[str] = set()
        n = 0
        for e, es_reserva in cola:
            if sum(p.estado == "propuesta" for p in piezas) >= objetivo:
                break
            n += 1
            h = por_id[e.historia_id]
            pieza = Pieza(id=f"{self.fecha}-{n}", fecha=self.fecha, estado="fallida", reserva=es_reserva,
                          historia_id=h.id, eleccion=e, n_medios=h.n_medios)
            piezas.append(pieza)
            log.info("Pieza %s: %s", pieza.id, e.titular)
            libros, descartes = self._verificar_libros(e, libros_hoy)
            pieza.libros, pieza.libros_descartados = libros, descartes
            if not libros:
                pieza.error = "Ningún libro candidato se pudo verificar"
                continue
            for l in libros:
                if l.edicion_es != "si":
                    pieza.avisos.append(f"«{l.titulo_propuesto}»: edición española {l.edicion_es}")
            textos_h = textos.textos_historia(self.cfg, h)
            pieza.fuentes = [f for f, _ in textos_h]
            if not any(f.texto_completo for f in pieza.fuentes):
                pieza.avisos.append("Ningún texto completo disponible: el guionista solo tuvo titulares y entradillas")
            try:
                pieza.guion, avisos = guionista.escribir(self.llm, pieza.id, e, textos_h, libros)
            except Exception as exc:
                pieza.error = str(exc)
                continue
            pieza.avisos += avisos
            pieza.estado = "propuesta"
            usados = [l for l in libros if any(
                guionista._es_titulo_de_libro(lg.titulo, [l]) for lg in pieza.guion.libros)]
            pieza.libros = usados or libros
            for l in pieza.libros:
                libros_hoy.add(clave_libro(l.titulo_propuesto, l.autores[0] if l.autores else ""))
                if l.olid:
                    libros_hoy.add(l.olid)
        return piezas

    # --- Ejecución completa -------------------------------------------------

    def ejecutar(self, desde: Etapa = "ingesta", sin_llm: bool = False) -> tuple[InformeDiario, tuple]:
        inicio = _ORDEN[desde]
        articulos = self.ingesta(usar_cache=inicio > 0)
        vectores = self.vectores(articulos)
        if inicio <= 1 or sin_llm:
            al_jefe, resumidas = self.historias(articulos, vectores, con_llm=not sin_llm)
        else:
            datos = _cargar(self.cache / "historias.json")
            al_jefe = TypeAdapter(list[Historia]).validate_python(datos["al_jefe"])
            resumidas = TypeAdapter(list[HistoriaResumida]).validate_python(datos["resumidas"])
            self.stats = datos["stats"]

        sel = None
        piezas: list[Pieza] = []
        if not sin_llm:
            if inicio <= 1:
                sel = self.seleccion(al_jefe)
            else:
                sel = SeleccionJefe.model_validate(_cargar(self.cache / "seleccion.json"))
            piezas = self.piezas(sel, al_jefe)
            buenas = [p for p in piezas if p.estado == "propuesta"]
            por_id = {h.id: h for h in al_jefe}
            self.historial.registrar_dia(
                self.fecha,
                [(p.historia_id, p.eleccion.titular, agrupacion.centroide(por_id[p.historia_id], vectores)) for p in buenas],
                [(l.titulo_propuesto, l.autores[0] if l.autores else "", l.olid) for p in buenas for l in p.libros],
            )
            if len(buenas) < len(sel.elegidas):
                self.avisos.append(f"Solo {len(buenas)} piezas válidas de {len(sel.elegidas)} previstas")

        inf = InformeDiario(
            fecha=self.fecha, generado_en=datetime.now(timezone.utc), stats=self.stats,
            top_historias=resumidas, seleccion=sel, piezas=piezas, trazas=self.llm.trazas,
            coste_total_usd=round(sum(t.coste_usd for t in self.llm.trazas), 4), avisos=self.avisos,
        )
        rutas = informe.escribir(inf, self.cfg.dir_informes / self.fecha)
        return inf, rutas
