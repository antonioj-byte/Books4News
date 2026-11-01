"""Temas que propone la redacción al jefe de cultura (2/11): ahora (una pieza pendiente en la mesa, uno o dos minutos y
unos céntimos) o para la selección de la madrugada siguiente (folio.temas)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from folio import temas
from folio.almacen import Tema
from folio.llm import ErrorLLM
from folio_api.dependencias import Contexto, contexto

router = APIRouter()


class TemaNuevo(BaseModel):
    texto: str = Field(min_length=8, max_length=1500)
    enlaces: list[str] = Field(default_factory=list, max_length=temas.MAX_ENLACES)
    cuando: Literal["ahora", "manana"]
    ejecucion: int | None = None          # para «ahora»: la ejecución de la mesa en que entra la pieza


class TemaCreado(BaseModel):
    tema: Tema
    pieza_id: str | None = None
    estado_pieza: str | None = None
    avisos: list[str] = []


@router.get("/api/temas", response_model=list[Tema])
def lista(ctx: Contexto = Depends(contexto)):
    return ctx.almacen.temas()


@router.post("/api/temas", response_model=TemaCreado)
def proponer(t: TemaNuevo, ctx: Contexto = Depends(contexto)):
    texto = " ".join(t.texto.split())
    enlaces = [u.strip() for u in t.enlaces if u.strip()]
    if t.cuando == "ahora" and not t.ejecucion:
        raise HTTPException(422, "Para proponerlo ahora hace falta la mesa del día: lanza antes la ejecución")
    if t.cuando == "ahora" and ctx.ejecutor.ocupado():
        raise HTTPException(409, "Hay una ejecución en marcha; prueba cuando termine o guárdalo para mañana")
    tid = ctx.almacen.guardar_tema(texto, enlaces, t.cuando)
    if t.cuando == "manana":
        return TemaCreado(tema=next(x for x in ctx.almacen.temas() if x.id == tid))
    try:
        pieza, avisos = temas.crear_pieza(ctx.cfg, ctx.almacen, t.ejecucion, tid, ctx.llm)
    except temas.SinFuentes as exc:
        raise HTTPException(422, str(exc))
    except ErrorLLM as exc:
        raise HTTPException(502, f"El jefe de cultura no ha podido responder: {exc}")
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return TemaCreado(tema=next(x for x in ctx.almacen.temas() if x.id == tid), pieza_id=pieza.id,
                      estado_pieza=pieza.estado, avisos=avisos + ([pieza.error] if pieza.error else []))


@router.delete("/api/temas/{tid}", response_model=Tema)
def descartar(tid: int, ctx: Contexto = Depends(contexto)):
    t = next((x for x in ctx.almacen.temas() if x.id == tid), None)
    if not t:
        raise HTTPException(404, "No existe ese tema")
    if t.estado != "pendiente":
        raise HTTPException(409, f"El tema ya está «{t.estado}»")
    ctx.almacen.actualizar_tema(tid, estado="descartado")
    return next(x for x in ctx.almacen.temas() if x.id == tid)
