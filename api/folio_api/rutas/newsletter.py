"""«La newsletter del jueves» (4/11): la versión corta en Instagram del ensayo de la newsletter. Se pega el texto, se
lanza `folio newsletter` en un proceso aparte (como «Cinco del libro») y la pieza entra escrita en la mesa del día. La
foto de quien firma se sube una vez y vale para todos los jueves."""

from __future__ import annotations

import re
import sys
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from folio import newsletter
from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import YA_EN_MARCHA, EstadoEjecucion

router = APIRouter()
TRABAJO = "newsletter"
MAX_TEXTO = 40000          # una newsletter de unas 2.000 palabras ronda los 12.000 caracteres
MAX_FOTO = 8 * 1024 * 1024


class NewsletterNueva(BaseModel):
    texto: str = Field(min_length=newsletter.MIN_TEXTO, max_length=MAX_TEXTO)
    fecha: str | None = None


class EstadoNewsletter(BaseModel):
    trabajo: EstadoEjecucion
    foto: str | None = None            # la foto de quien firma, si se subió (dirección en /api/medios/)
    autor: str
    cargo: str


def _estado(ctx: Contexto) -> EstadoNewsletter:
    nl = ctx.cfg.pipeline.newsletter
    ruta = newsletter.ruta_foto(ctx.cfg)
    foto = f"/api/medios/newsletter/{ruta.name}?v={int(ruta.stat().st_mtime)}" if ruta.exists() else None
    return EstadoNewsletter(trabajo=ctx.ejecutor.estado_desarrollo(TRABAJO) or EstadoEjecucion(en_marcha=False),
                            foto=foto, autor=nl.autor, cargo=nl.cargo)


@router.get("/api/newsletter", response_model=EstadoNewsletter)
def estado(ctx: Contexto = Depends(contexto)):
    return _estado(ctx)


@router.post("/api/newsletter", response_model=EstadoNewsletter, status_code=202)
def lanzar(cuerpo: NewsletterNueva, ctx: Contexto = Depends(contexto)):
    fecha = cuerpo.fecha or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise HTTPException(422, "Fecha no válida")
    if not ctx.almacen.ultima_ejecucion(fecha):
        raise HTTPException(409, f"No hay ejecución del {fecha}: la pieza entra en la mesa del día, lanza antes la del día")
    archivo = ctx.cfg.dir_datos / "newsletter" / f"{fecha}.md"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(cuerpo.texto, encoding="utf-8")
    motivo = ctx.ejecutor.desarrollar(TRABAJO, [[sys.executable, "-m", "folio.cli", "newsletter", str(archivo),
                                                 "--fecha", fecha, "--quiet"]])
    if motivo:
        raise HTTPException(409, "Ya se está escribiendo la newsletter" if motivo == YA_EN_MARCHA else motivo)
    return _estado(ctx)


@router.put("/api/newsletter/foto", response_model=EstadoNewsletter)
async def subir_foto(request: Request, ctx: Contexto = Depends(contexto)):
    """La foto de quien firma, en el cuerpo (sin multipart, como los materiales). Sustituye a la anterior."""
    datos = await request.body()
    if not datos or len(datos) > MAX_FOTO:
        raise HTTPException(422, "Sube una foto de hasta 8 MB")
    try:
        newsletter.guardar_foto(ctx.cfg, datos)
    except Exception:
        raise HTTPException(422, "No es una imagen que se pueda leer (JPEG, PNG o WebP)")
    return _estado(ctx)
