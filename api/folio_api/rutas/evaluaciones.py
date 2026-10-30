"""Resumen de las evaluaciones."""

from fastapi import APIRouter, Depends

from folio_api.dependencias import Contexto, contexto
from folio_api.esquemas import ResumenDia

router = APIRouter()


@router.get("/api/evaluaciones/resumen", response_model=list[ResumenDia])
def resumen(ctx: Contexto = Depends(contexto)):
    return ctx.almacen.resumen_evaluaciones()
