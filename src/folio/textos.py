"""Textos de las noticias para el guionista.

En los grupos grandes (un evento con decenas de artículos) no vale el primero de cada medio: se
eligen los más cercanos al hecho principal, uno por medio, priorizando los de acceso abierto.
Si el texto completo no se puede extraer, se usa titular + entradilla del RSS.
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


def elegir_articulos(cfg: Config, historia: Historia, puntuaciones: dict[str, float] | None = None) -> list[Articulo]:
    """Los artículos que leerá el guionista: uno por medio, los más cercanos al hecho principal.

    `puntuaciones` (id → similitud con el centro del grupo y con lo que el jefe resumió como «de
    qué se habla») ordena; el acceso abierto suma un poco. Se toman entre `min_textos` y
    `max_textos`: los que quedan a más de `margen` del mejor se descartan mientras queden al
    menos `min_textos`. Sin puntuaciones, se ordena solo por acceso.
    """
    p = cfg.pipeline["guion"]
    sel = cfg.pipeline.get("seleccion_textos", {})
    bonus = sel.get("bonus_acceso", {"abierto": 0.02, "parcial": 0.01, "muro": 0.0})
    def valor(a: Articulo) -> float:
        base = puntuaciones.get(a.id, 0.0) if puntuaciones else 0.0
        return base + bonus.get(a.acceso, 0.0)
    por_medio: dict[str, Articulo] = {}
    for a in sorted(historia.articulos, key=lambda a: (-valor(a), _PRIORIDAD[a.acceso])):
        por_medio.setdefault(a.medio, a)
    elegidos = sorted(por_medio.values(), key=lambda a: (-valor(a), _PRIORIDAD[a.acceso]))[: p["max_textos"]]
    if puntuaciones and elegidos:
        mejor = valor(elegidos[0])
        minimo = sel.get("min_textos", 3)
        cercanos = [a for a in elegidos if mejor - valor(a) <= sel.get("margen", 0.06)]
        elegidos = cercanos if len(cercanos) >= minimo else elegidos[:minimo]
    return elegidos


def textos_historia(cfg: Config, historia: Historia, puntuaciones: dict[str, float] | None = None
                    ) -> list[tuple[FuenteNoticia, str]]:
    """Textos de los artículos elegidos (ver elegir_articulos), priorizando el acceso abierto."""
    max_car = cfg.pipeline["guion"]["max_caracteres_texto"]
    elegidos = elegir_articulos(cfg, historia, puntuaciones)

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
