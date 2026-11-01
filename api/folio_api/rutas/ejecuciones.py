"""Lanzar la ejecución del día y seguir su progreso."""

from fastapi import APIRouter, Depends, HTTPException

from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import EstadoEjecucion
from folio_api.programador import EstadoProgramada

router = APIRouter()


@router.post("/api/ejecuciones/lanzar", response_model=EstadoEjecucion, status_code=202)
def lanzar(ctx: Contexto = Depends(contexto)):
    """Lanza la ejecución del día, igual que la diaria: `folio run` (~1 $) y después el render (PNG y
    vídeos de las diapositivas animadas). La ejecución aparece en la portada del día en cuanto termina el pipeline (la
    guarda en la base de datos); el vídeo, cuando termina el render."""
    if not ctx.ejecutor.lanzar(ctx.ejecutor.diaria):
        raise HTTPException(409, ctx.ejecutor.motivo_ocupado() or "Ya hay una ejecución en marcha")
    return ctx.ejecutor.estado()


@router.get("/api/ejecuciones/en-marcha", response_model=EstadoEjecucion)
def en_marcha(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado()


@router.get("/api/ejecuciones/programada", response_model=EstadoProgramada)
def programada(ctx: Contexto = Depends(contexto)):
    """La ejecución diaria automática (FOLIO_EJECUCION_DIARIA): si está activa, a qué hora y cuándo toca."""
    return ctx.programador.estado() if ctx.programador else EstadoProgramada(activa=False)
