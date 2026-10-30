"""Resumen y clasificación de las historias con el modelo barato.

Se resume por historia (grupo), no por artículo: solo las que pueden llegar al jefe de
cultura, así son ~25-40 llamadas cortas al día en lugar de cientos.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from folio.llm import LLM, cargar_prompt, con_cache
from folio.modelos import Historia, ResumenHistoria

log = logging.getLogger(__name__)


def _bloque_articulos(h: Historia, max_articulos: int = 8) -> str:
    lineas = []
    for a in h.articulos[:max_articulos]:
        lineas.append(f"- [{a.medio}] {a.titulo}" + (f" — {a.entradilla[:300]}" if a.entradilla else ""))
    return "<articulos>\n" + "\n".join(lineas) + "\n</articulos>"


def resumir(llm: LLM, historias: list[Historia]) -> list[str]:
    """Rellena titular_es, resumen_es y seccion en cada historia. Devuelve errores."""
    errores: list[str] = []

    def uno(h: Historia):
        prompt = cargar_prompt(llm.cfg, "ingesta_resumen", {"[articulos]": _bloque_articulos(h)})
        try:
            r, _ = llm.estructurado(
                f"resumen:{h.id}", [{"role": "user", "content": con_cache(llm.cfg, "ingesta_resumen", prompt)}],
                ResumenHistoria,
                etapa_modelo="ingesta", max_tokens=2000,
            )
            h.titular_es, h.resumen_es, h.seccion, h.sobre_libros = r.titular_es, r.resumen_es, r.seccion, r.sobre_libros
        except Exception as exc:
            errores.append(f"resumen de {h.id}: {exc}")
            h.titular_es = h.articulos[0].titulo  # sin resumen: se usa el titular original
            h.resumen_es = h.articulos[0].entradilla[:300]

    with ThreadPoolExecutor(max_workers=llm.cfg.pipeline.ingesta.concurrencia_llm) as pool:
        list(pool.map(uno, historias))
    return errores
