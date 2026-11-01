"""Feedback por agente (2/11, a petición del usuario: «plantear cambios/feedback que luego puedan sumarse a la memoria
al jefe de cultura, al editor (guionista) y al director de arte»): el motivo de un descarte, para el jefe de cultura,
y notas sobre una diapositiva, para el director de arte o el guionista. No cambian la pieza: los lee la Memoria."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from folio.almacen import MOTIVOS_DESCARTE, Nota
from folio.modelos import Pieza
from folio_api.dependencias import Contexto, contexto

router = APIRouter()


class NotaNueva(BaseModel):
    destino: Literal["director_arte", "guionista"]
    diapositiva: int = Field(ge=1)
    texto: str = Field(min_length=2, max_length=1500)


class Descarte(BaseModel):
    etiquetas: list[str] = Field(default_factory=list, max_length=len(MOTIVOS_DESCARTE))
    texto: str = Field(default="", max_length=1500)


def recurso(p: Pieza, n: int) -> str:
    """Qué llevaba la diapositiva, para que la Memoria pueda sacar reglas de arte concretas."""
    if not p.guion or not 1 <= n <= len(p.guion.diapositivas):
        return "colofón" if p.guion and n == len(p.guion.diapositivas) + 1 else ""
    d, a = p.guion.diapositivas[n - 1], p.arte
    partes = [d.tipo]
    if a:
        if d.tipo == "portada":
            partes += [f"composición {a.portada}", f"imagen: {a.registro or a.recurso}"]
            if a.remate:
                partes.append(f"destacado «{a.remate}»")
        elif d.tipo == "actualidad":
            partes.append("cifra" if a.cifra else f"sin foto: {a.sin_foto.recurso}" if a.sin_foto else "foto" if a.imagen_noticia or a.imagen else "texto")
        elif d.tipo == "libro" and a.friso:
            partes.append("con friso")
        elif d.tipo == "idea" and a.infografia:
            partes.append(f"infografía {a.infografia.tipo}")
        if a.acento:
            partes.append(f"color {a.acento}")
        partes.append(f"tono {a.tono}")
    partes.append(f"{len(d.texto.split())} palabras")
    return " · ".join(partes)


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/notas", response_model=list[Nota])
def lista(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    ctx.pieza(eid, pid)
    return ctx.almacen.notas(eid, pid)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/notas", response_model=Nota)
def anadir(eid: int, pid: str, n: NotaNueva, ctx: Contexto = Depends(contexto)):
    p, v = ctx.pieza(eid, pid)
    nid = ctx.almacen.anadir_nota(eid, pid, n.destino, "diapositiva", n.texto, diapositiva=n.diapositiva,
                                  recurso=recurso(p, n.diapositiva), version_n=v)
    return next(x for x in ctx.almacen.notas(eid, pid) if x.id == nid)


@router.delete("/api/ejecuciones/{eid}/piezas/{pid}/notas/{nid}")
def borrar(eid: int, pid: str, nid: int, ctx: Contexto = Depends(contexto)):
    if not ctx.almacen.borrar_nota(eid, pid, nid):
        raise HTTPException(404, "No existe esa nota")
    return {"borrada": nid}


@router.get("/api/motivos-descarte", response_model=list[str])
def motivos():
    return list(MOTIVOS_DESCARTE)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/descartar", response_model=Nota | None)
def descartar(eid: int, pid: str, d: Descarte, ctx: Contexto = Depends(contexto)):
    """Descarta la pieza y, si se dice por qué, deja el motivo para el jefe de cultura."""
    _, v = ctx.pieza(eid, pid)
    raras = [e for e in d.etiquetas if e not in MOTIVOS_DESCARTE]
    if raras:
        raise HTTPException(422, f"Motivos desconocidos: {', '.join(raras)}")
    ctx.almacen.cambiar_estado(eid, pid, "descartada")
    if not (d.etiquetas or d.texto.strip()):
        return None
    nid = ctx.almacen.anadir_nota(eid, pid, "jefe_cultura", "descarte", d.texto, etiquetas=d.etiquetas, version_n=v)
    return next(x for x in ctx.almacen.notas(eid, pid) if x.id == nid)
