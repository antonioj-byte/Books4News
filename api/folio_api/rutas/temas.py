"""Temas que propone la redacción al jefe de cultura (2/11): ahora (una pieza pendiente en la mesa, uno o dos minutos y
unos céntimos) o para la selección de la madrugada siguiente (folio.temas)."""

import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from folio import temas
from folio.almacen import Tema
from folio.llm import ErrorLLM
from folio_api.dependencias import Contexto, contexto

router = APIRouter()
# Un tema a la vez: dos a la vez podrían llevarse el mismo número de pieza o pisarse las historias del día
_un_tema = threading.Lock()


# 3/11: la redacción pega encargos enteros, no solo una línea (el límite de 1.500 se quedaba corto)
MAX_TEXTO_TEMA = 6000


class TemaNuevo(BaseModel):
    texto: str = Field(min_length=8, max_length=MAX_TEXTO_TEMA)
    enlaces: list[str] = Field(default_factory=list, max_length=temas.MAX_ENLACES)
    cuando: Literal["ahora", "manana"]
    ejecucion: int | None = None          # para «ahora»: la ejecución de la mesa en que entra la pieza
    # 3/11 (a petición del usuario): «elige», el jefe decide el formato; «noticia», contar la noticia, sin ensayo
    enfoque: Literal["elige", "noticia"] = "elige"


class TemaCreado(BaseModel):
    tema: Tema
    pieza_id: str | None = None
    estado_pieza: str | None = None
    avisos: list[str] = []
    preguntas: list[str] = []             # si el jefe necesita saber algo antes de proponer (2/11)
    respuesta: str = ""                   # lo que dice el jefe


class Replica(BaseModel):
    texto: str = Field(min_length=2, max_length=MAX_TEXTO_TEMA)
    ejecucion: int
    enfoque: Literal["elige", "noticia"] | None = None   # si la réplica cambia lo que se pide (p. ej. «solo la noticia»)


def _fallido(ctx: Contexto, tid: int, motivo: str) -> None:
    """Un tema que no llegó a la mesa queda «fallido» con su motivo, no «pendiente» para siempre (revisión, 2/11)."""
    tema = next((x for x in ctx.almacen.temas() if x.id == tid), None)
    if tema and tema.estado == "pendiente":
        ctx.almacen.actualizar_tema(tid, estado="fallido", nota=motivo[:300])


def _resultado(ctx: Contexto, eid: int, tid: int, replica: str | None = None) -> TemaCreado:
    if not _un_tema.acquire(blocking=False):
        raise HTTPException(409, "El jefe ya está con otro tema; espera a que responda")
    try:
        r = temas.crear_pieza(ctx.cfg, ctx.almacen, eid, tid, ctx.llm, replica=replica)
    except temas.SinFuentes as exc:
        _fallido(ctx, tid, str(exc))
        raise HTTPException(422, str(exc))
    except ErrorLLM as exc:
        _fallido(ctx, tid, str(exc))
        raise HTTPException(502, f"El jefe de cultura no ha podido responder: {exc}")
    except temas.NoSePuede as exc:
        raise HTTPException(409, str(exc))
    finally:
        _un_tema.release()
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
    if t.cuando == "ahora" and ctx.ejecutor.con_pipeline():
        raise HTTPException(409, "Se está preparando la mesa del día; prueba cuando termine o guárdalo para mañana")
    if t.cuando == "ahora" and _un_tema.locked():
        # Antes de guardarlo: un 409 dejaba un tema «pendiente» huérfano para siempre (revisión general, 2/11)
        raise HTTPException(409, "El jefe ya está con otro tema; espera a que responda")
    if t.cuando == "manana" and t.enfoque == "noticia":
        # La mesa de madrugada no cuenta noticias sueltas: solo propone piezas con libro
        raise HTTPException(422, "«Solo la noticia» se propone ahora, no para la mesa de mañana")
    tid = ctx.almacen.guardar_tema(texto, enlaces, t.cuando, t.enfoque)
    if t.cuando == "manana":
        return TemaCreado(tema=next(x for x in ctx.almacen.temas() if x.id == tid))
    return _resultado(ctx, t.ejecucion, tid)


@router.post("/api/temas/{tid}/replica", response_model=TemaCreado)
def replicar(tid: int, r: Replica, ctx: Contexto = Depends(contexto)):
    """La redacción contesta al jefe (a sus preguntas o a su propuesta): vuelve a pensar y propone, o pregunta otra vez.
    Si la pieza del tema aún no está escrita, se rehace en el sitio."""
    if ctx.ejecutor.con_pipeline():
        raise HTTPException(409, "Se está preparando la mesa del día; prueba cuando termine")
    tema = next((x for x in ctx.almacen.temas() if x.id == tid), None)
    if tema is None:
        raise HTTPException(404, "No existe ese tema")
    if tema.pieza_id and ctx.ejecutor.en_marcha(tema.pieza_id):
        raise HTTPException(409, "La pieza de este tema se está escribiendo con «Proceder»; espera a que acabe")
    if r.enfoque and r.enfoque != tema.enfoque:
        ctx.almacen.cambiar_enfoque_tema(tid, r.enfoque)
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
