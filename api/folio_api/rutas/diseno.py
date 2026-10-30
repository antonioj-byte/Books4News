"""El design system para la web, y las imágenes y cubiertas que usan las diapositivas."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from folio.render import cargar_tokens, css_tokens
from folio_api.dependencias import Contexto, contexto

router = APIRouter()


@router.get("/api/diseno/tokens.css", response_class=PlainTextResponse)
def tokens_css(ctx: Contexto = Depends(contexto)):
    """Variables CSS del design system, para que la web use los mismos colores y fuentes."""
    return PlainTextResponse(css_tokens(cargar_tokens(ctx.cfg)), media_type="text/css")


# Solo se sirven las imágenes de las piezas y las cubiertas; nada más de data/cache.
_MEDIO = re.compile(r"^(cubiertas/[\w.-]+|\d{4}-\d{2}-\d{2}/imagenes/[\w.-]+)\.(jpg|jpeg|png)$")


def ruta_medio(raiz_cache: Path, ruta: str) -> Path | None:
    if not _MEDIO.match(ruta) or ".." in ruta:
        return None
    archivo = (raiz_cache / ruta).resolve()
    return archivo if archivo.is_relative_to(raiz_cache.resolve()) and archivo.is_file() else None


def url_medio(raiz_cache: Path):
    """Archivo de data/cache → URL de la API (para la vista previa de las diapositivas)."""
    return lambda archivo: "/api/medios/" + archivo.resolve().relative_to(raiz_cache.resolve()).as_posix()


@router.get("/api/medios/{ruta:path}")
def medio(ruta: str, ctx: Contexto = Depends(contexto)):
    """Imagen de una pieza o cubierta de un libro."""
    archivo = ruta_medio(ctx.cfg.dir_cache("x").parent, ruta)
    if not archivo:
        raise HTTPException(404, "No existe")
    return FileResponse(archivo, headers={"Cache-Control": "public, max-age=86400"})
