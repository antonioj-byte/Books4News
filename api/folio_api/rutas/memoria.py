"""Memoria del feedback (página «Memoria» de la web): los patrones con su propuesta de regla, analizar el
feedback (una llamada a Opus, unos céntimos) y decidir si cada propuesta se acepta o se rechaza."""

import sys

from fastapi import APIRouter, Depends, HTTPException, Query

from folio import memoria
from folio.almacen import Patron
from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import YA_EN_MARCHA, EstadoEjecucion
from folio_api.esquemas import DecisionPatron, EstadoMemoria

router = APIRouter()


@router.get("/api/memoria", response_model=list[Patron])
def patrones(ctx: Contexto = Depends(contexto)):
    return ctx.almacen.patrones()


@router.get("/api/memoria/estado", response_model=EstadoMemoria)
def estado(ctx: Contexto = Depends(contexto)):
    u = ctx.almacen.ultimo_analisis()
    return EstadoMemoria(ultimo=u["ts"] if u else None, ultimo_origen=u["origen"] if u else None,
                         proximo=memoria.proximo_analisis(ctx.almacen).isoformat(),
                         de_conversacion=sum(p.origen == "conversacion" for p in ctx.almacen.patrones()))


TRABAJO = "memoria-analisis"


@router.post("/api/memoria/analizar", response_model=EstadoEjecucion)
def analizar(dias: int = Query(14, ge=1, le=90), ctx: Contexto = Depends(contexto)):
    """Lanza el análisis en un proceso aparte (2/11: dentro de la petición, la web cortaba a los 5 minutos y salía
    «500 Internal Server Error»); la página sigue su estado con GET /api/memoria/analisis."""
    motivo = ctx.ejecutor.desarrollar(TRABAJO, [[sys.executable, "-m", "folio.cli", "memoria", "analizar", "--dias", str(dias)]])
    if motivo:
        raise HTTPException(409, "Ya se está analizando" if motivo == YA_EN_MARCHA else motivo)
    return ctx.ejecutor.estado_desarrollo(TRABAJO)


@router.get("/api/memoria/analisis", response_model=EstadoEjecucion | None)
def analisis(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado_desarrollo(TRABAJO)


@router.patch("/api/memoria/{pid}", response_model=DecisionPatron)
def decidir(pid: int, d: DecisionPatron, ctx: Contexto = Depends(contexto)):
    if pid not in {p.id for p in ctx.almacen.patrones()}:
        raise HTTPException(404, "No existe ese patrón")
    if d.estado == "retirada":
        from folio import estilo_vivo
        estilo_vivo.retirar(ctx.cfg, ctx.almacen, pid, d.nota)
        return d
    ctx.almacen.decidir_patron(pid, d.estado, d.nota, d.capa)
    if d.estado == "aceptada":
        # El libro de estilo vivo (6/11): aceptar una poda retira lo que funde; aceptar una de código abre su encargo
        from folio import estilo_vivo
        estilo_vivo.al_aceptar(ctx.cfg, ctx.almacen, pid)
    return d
