"""Textos de las noticias para el guionista.

Se pasan los textos de todos los medios del grupo, priorizando los de acceso abierto: así una
historia que venga de FT o NYT no deja al guionista solo con el titular. Si el texto completo
no se puede extraer, se usa titular + entradilla del RSS.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import trafilatura

from folio.config import Config
from folio.modelos import Articulo, FuenteNoticia, Historia

log = logging.getLogger(__name__)

_PRIORIDAD = {"abierto": 0, "parcial": 1, "muro": 2}
_MIN_CARACTERES = 600


def _extraer(cliente: httpx.Client, a: Articulo, max_caracteres: int) -> str | None:
    if a.acceso == "muro":
        return None
    try:
        r = cliente.get(a.url)
        r.raise_for_status()
        texto = trafilatura.extract(r.text, include_comments=False, include_tables=False)
    except Exception as exc:
        log.info("Sin texto completo de %s: %s", a.url, exc)
        return None
    if not texto or len(texto) < _MIN_CARACTERES:
        return None
    return texto[:max_caracteres]


def textos_historia(cfg: Config, historia: Historia) -> list[tuple[FuenteNoticia, str]]:
    """Hasta `max_textos` textos, uno por medio, ordenados por accesibilidad."""
    max_textos = cfg.pipeline["guion"]["max_textos"]
    max_car = cfg.pipeline["guion"]["max_caracteres_texto"]
    por_medio: dict[str, Articulo] = {}
    for a in sorted(historia.articulos, key=lambda a: _PRIORIDAD[a.acceso]):
        por_medio.setdefault(a.medio, a)
    elegidos = sorted(por_medio.values(), key=lambda a: _PRIORIDAD[a.acceso])[:max_textos]

    with httpx.Client(
        timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FolioLateral/0.1)"},
    ) as cliente, ThreadPoolExecutor(max_workers=5) as pool:
        completos = list(pool.map(lambda a: _extraer(cliente, a, max_car), elegidos))

    salida = []
    for a, texto in zip(elegidos, completos):
        fuente = FuenteNoticia(medio=a.medio, titulo=a.titulo, url=a.url, acceso=a.acceso,
                               texto_completo=texto is not None)
        salida.append((fuente, texto or f"{a.titulo}\n{a.entradilla}"))
    return salida
