"""«La newsletter del jueves» (4/11): la versión corta en Instagram del ensayo de la newsletter. Se pega el texto, se
lanza `folio newsletter` en un proceso aparte (como «Cinco del libro») y la pieza entra escrita en la mesa del día. La
foto de quien firma se sube una vez y vale para todos los jueves. Desde el 7/11, lo mismo para la «Opinión» de otras
firmas: cada una con su nombre, cargo, dónde se publica entera y su foto (`/api/firmantes`)."""

from __future__ import annotations

import re
import sys
from datetime import date
from typing import Literal

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
    formato: Literal["newsletter", "opinion"] = "newsletter"
    firmante: str | None = None        # slug; por defecto, la firma de la casa


class FirmaWeb(BaseModel):
    slug: str
    nombre: str
    cargo: str = ""
    publicacion: str = ""
    url: str = ""
    foto: str | None = None


class FirmaNueva(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    cargo: str = Field("", max_length=120)
    publicacion: str = Field("", max_length=80)
    url: str = Field("", max_length=200)


class EstadoNewsletter(BaseModel):
    trabajo: EstadoEjecucion
    foto: str | None = None            # la foto de quien firma, si se subió (dirección en /api/medios/)
    autor: str
    cargo: str
    firmantes: list[FirmaWeb] = []     # la de la casa primero


def _foto(ctx: Contexto, slug: str) -> str | None:
    ruta = newsletter.ruta_foto(ctx.cfg, slug)
    if not ruta.exists():
        return None
    rel = ruta.relative_to(ctx.cfg.dir_cache("x").parent).as_posix()
    return f"/api/medios/{rel}?v={int(ruta.stat().st_mtime)}"


def _estado(ctx: Contexto) -> EstadoNewsletter:
    nl = ctx.cfg.pipeline.newsletter
    firmas = [FirmaWeb(**f.model_dump(), foto=_foto(ctx, f.slug)) for f in newsletter.firmantes(ctx.cfg)]
    return EstadoNewsletter(trabajo=ctx.ejecutor.estado_desarrollo(TRABAJO) or EstadoEjecucion(en_marcha=False),
                            foto=firmas[0].foto, autor=nl.autor, cargo=nl.cargo, firmantes=firmas)


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
    firma = newsletter.firmante(ctx.cfg, cuerpo.firmante)
    if cuerpo.firmante and firma.slug != cuerpo.firmante:
        raise HTTPException(404, "No está esa firma: añádela antes")
    archivo = ctx.cfg.dir_datos / "newsletter" / (f"{fecha}.md" if cuerpo.formato == "newsletter" else f"{fecha}-opinion-{firma.slug}.md")
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(cuerpo.texto, encoding="utf-8")
    motivo = ctx.ejecutor.desarrollar(TRABAJO, [[sys.executable, "-m", "folio.cli", "newsletter", str(archivo),
                                                 "--fecha", fecha, "--formato", cuerpo.formato,
                                                 "--firmante", firma.slug, "--quiet"]])
    if motivo:
        raise HTTPException(409, "Ya se está escribiendo una newsletter u opinión" if motivo == YA_EN_MARCHA else motivo)
    return _estado(ctx)


async def _subir(request: Request, ctx: Contexto, slug: str) -> EstadoNewsletter:
    datos = await request.body()
    if not datos or len(datos) > MAX_FOTO:
        raise HTTPException(422, "Sube una foto de hasta 8 MB")
    try:
        newsletter.guardar_foto(ctx.cfg, datos, slug)
    except Exception:
        raise HTTPException(422, "No es una imagen que se pueda leer (JPEG, PNG o WebP)")
    return _estado(ctx)


@router.put("/api/newsletter/foto", response_model=EstadoNewsletter)
async def subir_foto(request: Request, ctx: Contexto = Depends(contexto)):
    """La foto de quien firma, en el cuerpo (sin multipart, como los materiales). Sustituye a la anterior."""
    return await _subir(request, ctx, newsletter.CASA)


@router.post("/api/firmantes", response_model=EstadoNewsletter)
def nueva_firma(cuerpo: FirmaNueva, ctx: Contexto = Depends(contexto)):
    """Una firma para las piezas de opinión (7/11). Con el mismo nombre, la actualiza."""
    if not cuerpo.nombre.strip():
        raise HTTPException(422, "Falta el nombre")
    newsletter.guardar_firmante(ctx.cfg, cuerpo.nombre, cuerpo.cargo, cuerpo.publicacion, cuerpo.url)
    return _estado(ctx)


@router.put("/api/firmantes/{slug}/foto", response_model=EstadoNewsletter)
async def foto_firma(slug: str, request: Request, ctx: Contexto = Depends(contexto)):
    if slug not in {f.slug for f in newsletter.firmantes(ctx.cfg)}:
        raise HTTPException(404, "No está esa firma")
    return await _subir(request, ctx, slug)
