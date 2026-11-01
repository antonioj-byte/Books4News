"""Memoria del feedback (página «Memoria» de la web): los patrones con su propuesta de regla, analizar el
feedback (una llamada a Opus, unos céntimos) y decidir si cada propuesta se acepta o se rechaza."""

from fastapi import APIRouter, Depends, HTTPException, Query

from folio import memoria
from folio.almacen import Patron
from folio.llm import LLM
from folio_api.dependencias import Contexto, contexto
from folio_api.esquemas import DecisionPatron, EstadoMemoria, ResultadoMemoria

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


@router.post("/api/memoria/analizar", response_model=ResultadoMemoria)
def analizar(dias: int = Query(14, ge=1, le=90), ctx: Contexto = Depends(contexto)):
    llm = ctx.llm or LLM(ctx.cfg)
    ids, aviso, n = memoria.analizar(llm, ctx.cfg, ctx.almacen, dias)
    return ResultadoMemoria(piezas=n, patrones=len(ids), aviso=aviso)


@router.patch("/api/memoria/{pid}", response_model=DecisionPatron)
def decidir(pid: int, d: DecisionPatron, ctx: Contexto = Depends(contexto)):
    if pid not in {p.id for p in ctx.almacen.patrones()}:
        raise HTTPException(404, "No existe ese patrón")
    ctx.almacen.decidir_patron(pid, d.estado, d.nota)
    return d
