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
    preguntas: list[str] = []             # si el jefe necesita saber algo antes de proponer (2/11)
    respuesta: str = ""                   # lo que dice el jefe


class Replica(BaseModel):
    texto: str = Field(min_length=2, max_length=1500)
    ejecucion: int


def _resultado(ctx: Contexto, eid: int, tid: int, replica: str | None = None) -> TemaCreado:
    try:
        r = temas.crear_pieza(ctx.cfg, ctx.almacen, eid, tid, ctx.llm, replica=replica)
    except temas.SinFuentes as exc:
        raise HTTPException(422, str(exc))
    except ErrorLLM as exc:
        raise HTTPException(502, f"El jefe de cultura no ha podido responder: {exc}")
    except temas.NoSePuede as exc:
        raise HTTPException(409, str(exc))
    tema = next(x for x in ctx.almacen.temas() if x.id == tid)
    p = r.pieza
    return TemaCreado(tema=tema, pieza_id=p.id if p else None, estado_pieza=p.estado if p else None,
                      avisos=r.avisos + ([p.error] if p is not None and p.error else []),
                      preguntas=r.preguntas, respuesta=r.respuesta)


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
    return _resultado(ctx, t.ejecucion, tid)


@router.post("/api/temas/{tid}/replica", response_model=TemaCreado)
def replicar(tid: int, r: Replica, ctx: Contexto = Depends(contexto)):
    """La redacción contesta al jefe (a sus preguntas o a su propuesta): vuelve a pensar y propone, o pregunta otra vez.
    Si la pieza del tema aún no está escrita, se rehace en el sitio."""
    if ctx.ejecutor.ocupado():
        raise HTTPException(409, "Hay una ejecución en marcha; prueba cuando termine")
    if not any(x.id == tid for x in ctx.almacen.temas()):
        raise HTTPException(404, "No existe ese tema")
    return _resultado(ctx, r.ejecucion, tid, replica=r.texto)


@router.delete("/api/temas/{tid}", response_model=Tema)
def descartar(tid: int, ctx: Contexto = Depends(contexto)):
    t = next((x for x in ctx.almacen.temas() if x.id == tid), None)
    if not t:
        raise HTTPException(404, "No existe ese tema")
    if t.estado != "pendiente":
        raise HTTPException(409, f"El tema ya está «{t.estado}»")
    ctx.almacen.actualizar_tema(tid, estado="descartado")
    return next(x for x in ctx.almacen.temas() if x.id == tid)
