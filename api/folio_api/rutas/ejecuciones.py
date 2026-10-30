"""Lanzar la ejecución del día y seguir su progreso."""

from fastapi import APIRouter, Depends, HTTPException

from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import EstadoEjecucion

router = APIRouter()


@router.post("/api/ejecuciones/lanzar", response_model=EstadoEjecucion, status_code=202)
def lanzar(ctx: Contexto = Depends(contexto)):
    """Lanza `folio run` (pipeline completo del día, ~1 $). Al terminar, la ejecución aparece en
    la portada del día: el pipeline la guarda en la base de datos."""
    if not ctx.ejecutor.lanzar():
        raise HTTPException(409, "Ya hay una ejecución en marcha")
    return ctx.ejecutor.estado()


@router.get("/api/ejecuciones/en-marcha", response_model=EstadoEjecucion)
def en_marcha(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado()
