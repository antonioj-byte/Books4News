"""Banco de pruebas de la voz (2/11, rondas de mejora del guionista): unas pocas piezas reales, con sus libros
verificados y sus textos congelados, sobre las que `folio ab` reescribe cada variante.

Cada pieza se monta con el pipeline de producción, sin atajos: las noticias se leen de enlaces reales (o se buscan en
la web), el jefe propone (`temas.proponer`, o el editor del libro con el catálogo de las independientes), los libros
se verifican contra las APIs, la prensa del libro se busca y el guion lo escribe el guionista de producción, que hace
de control. Se guarda en data/cache/<fecha>/ (historias.json, textos/, piezas.json) y no toca el historial ni la base
de datos de la web. Si una pieza ya está en el banco, no se rehace (para rehacerla, se borra de piezas.json).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import date

from folio import catalogo, temas
from folio.config import Config
from folio.etapas import EtapasGuardadas
from folio.llm import LLM, ErrorLLM
from folio.modelos import Historia, Pieza

log = logging.getLogger(__name__)


@dataclass
class TemaBanco:
    """Una pieza del banco. `formato` «recomendado» sale del catálogo; los demás, de un tema con sus enlaces."""
    clave: str
    formato: str
    texto: str = ""
    enlaces: list[str] = field(default_factory=list)


def _guardar(etapas: EtapasGuardadas, h: Historia, pieza: Pieza) -> None:
    try:
        al_jefe, resumidas, stats = etapas.historias()
    except (OSError, ValueError, KeyError):
        al_jefe, resumidas, stats = [], [], {}
    etapas.guardar_historias([*[x for x in al_jefe if x.id != h.id], h], resumidas, stats)
    try:
        piezas = etapas.piezas()
    except (OSError, ValueError):
        piezas = []
    etapas.guardar_piezas([*[p for p in piezas if p.id != pieza.id], pieza])


def _del_tema(llm: LLM, cfg: Config, fecha: str, n: int, t: TemaBanco) -> tuple[Historia, Pieza]:
    from folio.pipeline import Pipeline
    fuentes, avisos = temas.fuentes_del_tema(llm, cfg, t.texto, t.enlaces)
    if not fuentes:
        raise ErrorLLM(f"{t.clave}: no hay noticias que se puedan leer ({'; '.join(avisos)})")
    h = temas.historia(900 + n, t.texto, fuentes)
    r = temas.proponer(llm, cfg, h, t.texto, fuentes, fecha)
    if r.propuesta is None:
        raise ErrorLLM(f"{t.clave}: el jefe pregunta en vez de proponer: {r.preguntas}")
    temas.guardar_en_el_dia(cfg, fecha, h, fuentes)
    tuberia = Pipeline(cfg, fecha, llm=llm)
    tuberia.sin_novedad = t.formato == "balda"        # un perfil necesita la obra, como en los temas de la redacción
    return h, _escribir(tuberia, fecha, n, h, r.propuesta, avisos)


def _del_catalogo(llm: LLM, cfg: Config, fecha: str, n: int) -> tuple[Historia, Pieza]:
    from folio.pipeline import Pipeline
    from folio.seleccion import _mesa, bloque_cajon, bloque_catalogo, bloque_historias, criterios
    cfg_cat = copy.deepcopy(cfg)                      # pocas peticiones al portal: basta con unos candidatos
    cfg_cat.pipeline.catalogo.candidatos, cfg_cat.pipeline.catalogo.editoriales_por_dia = 6, 8
    libros, avisos = catalogo.candidatos(cfg_cat, date.fromisoformat(fecha))
    if any(" 403 " in a or " 429 " in a for a in avisos):
        raise ErrorLLM(f"El catálogo bloqueó: {avisos}")
    if not libros:
        raise ErrorLLM(f"El catálogo no dio candidatos ({avisos})")
    sel, _ = _mesa(llm, "banco-recomendado", "editor_libro", "seleccion_libro", {
        "[pegar criterios]": criterios(cfg, fecha), "[pegar lista editorial]": bloque_historias([], "mundo_del_libro"),
        "[pegar cajón]": bloque_cajon([]), "[pegar catálogo]": bloque_catalogo(libros)}, {"recomendado": 1},
        {h.id: h.carril for h in libros})
    e = next((x for x in sel.elegidas if x.formato == "recomendado"), None)
    if e is None:
        raise ErrorLLM("El editor del libro no eligió ningún recomendado")
    h = next(x for x in libros if x.id == e.historia_id)
    tuberia = Pipeline(cfg, fecha, llm=llm)
    return h, _escribir(tuberia, fecha, n, h, e, avisos)


def _escribir(tuberia, fecha: str, n: int, h: Historia, e, avisos: list[str]) -> Pieza:
    pieza = Pieza(id=f"{fecha}-{n}", fecha=fecha, estado="fallida", historia_id=h.id, eleccion=e, n_medios=h.n_medios,
                  avisos=["Banco de pruebas de la voz", *avisos])
    if not tuberia._verificar(pieza, set()):
        return pieza
    tuberia._escribir(pieza, tuberia._textos(pieza, h))
    if pieza.estado != "propuesta":
        pieza.estado = "fallida"
    return pieza


def montar(cfg: Config, fecha: str, lista: list[TemaBanco], llm: LLM | None = None) -> list[Pieza]:
    """Monta (o completa) el banco de `fecha`. Devuelve las piezas del banco."""
    llm = llm or LLM(cfg)
    etapas = EtapasGuardadas(cfg.dir_cache(fecha))
    try:
        hechas = {p.id: p for p in etapas.piezas()}
    except (OSError, ValueError):
        hechas = {}
    for n, t in enumerate(lista, 1):
        pid = f"{fecha}-{n}"
        if pid in hechas and hechas[pid].estado == "propuesta":
            continue
        log.info("Banco: %s (%s)", t.clave, t.formato)
        h, pieza = _del_catalogo(llm, cfg, fecha, n) if t.formato == "recomendado" else _del_tema(llm, cfg, fecha, n, t)
        if pieza.eleccion.formato != t.formato:
            pieza.avisos.append(f"Se pidió «{t.formato}» y el jefe propuso «{pieza.eleccion.formato}»")
        _guardar(etapas, h, pieza)
        hechas[pid] = pieza
    coste = sum(x.coste_usd for x in llm.trazas)
    log.info("Banco: %.3f $ en %d llamadas", coste, len(llm.trazas))
    return [hechas[f"{fecha}-{n}"] for n in range(1, len(lista) + 1) if f"{fecha}-{n}" in hechas]
