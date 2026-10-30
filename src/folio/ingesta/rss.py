"""Descarga y normalización de los feeds RSS."""

from __future__ import annotations

import hashlib
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

from folio.config import Config, Fuente
from folio.modelos import Articulo

log = logging.getLogger(__name__)

_ETIQUETAS = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"\s+")


def limpiar(texto: str | None) -> str:
    if not texto:
        return ""
    return _ESPACIOS.sub(" ", html.unescape(_ETIQUETAS.sub(" ", texto))).strip()


def normalizar_url(url: str) -> str:
    """Quita query y fragmento (parámetros de seguimiento) para deduplicar."""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", ""))


def _fecha(entrada) -> datetime | None:
    for campo in ("published_parsed", "updated_parsed"):
        t = entrada.get(campo)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def parsear(contenido: bytes, fuente: Fuente) -> list[Articulo]:
    feed = feedparser.parse(contenido)
    articulos = []
    for e in feed.entries:
        url = e.get("link")
        titulo = limpiar(e.get("title"))
        if not url or not titulo:
            continue
        url = normalizar_url(url)
        articulos.append(Articulo(
            id=hashlib.sha1(url.encode()).hexdigest()[:12],
            medio=fuente.medio,
            url=url,
            titulo=titulo,
            entradilla=limpiar(e.get("summary"))[:600],
            publicado_en=_fecha(e),
            idioma=fuente.idioma,
            acceso=fuente.acceso,
        ))
    return articulos


def _descargar(cliente: httpx.Client, fuente: Fuente) -> tuple[Fuente, list[Articulo], str | None]:
    try:
        r = cliente.get(fuente.url)
        r.raise_for_status()
        return fuente, parsear(r.content, fuente), None
    except Exception as exc:  # un feed caído no detiene la ingesta
        return fuente, [], f"{fuente.medio} ({fuente.url}): {exc}"


def ingerir(cfg: Config, ahora: datetime | None = None) -> tuple[list[Articulo], list[str]]:
    """Devuelve los artículos dentro de la ventana, deduplicados, y los errores por feed."""
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=cfg.pipeline.ingesta.ventana_horas)
    errores: list[str] = []
    vistos_url: set[str] = set()
    vistos_titulo: set[tuple[str, str]] = set()
    articulos: list[Articulo] = []

    with httpx.Client(
        timeout=cfg.pipeline.ingesta.timeout_s,
        follow_redirects=True,
        headers={"User-Agent": f"Mozilla/5.0 (compatible; {cfg.user_agent})"},
    ) as cliente, ThreadPoolExecutor(max_workers=8) as pool:
        for fuente, lote, error in pool.map(lambda f: _descargar(cliente, f), cfg.fuentes):
            if error:
                errores.append(error)
                log.warning("Feed fallido: %s", error)
                continue
            for a in lote:
                if a.publicado_en and a.publicado_en < limite:
                    continue
                clave_titulo = (a.medio, a.titulo.lower())
                if a.url in vistos_url or clave_titulo in vistos_titulo:
                    continue
                vistos_url.add(a.url)
                vistos_titulo.add(clave_titulo)
                articulos.append(a)
    return articulos, errores
