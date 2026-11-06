"""El libro de estilo vivo (6/11, folio.estilo_vivo): las fichas de cada rol con su ejemplo, su prueba y su encargo; los
ejemplos de la redacción; retirar una ficha, probarla en el banco y decidir los ejemplos."""

import json
import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from folio import estilo_vivo
from folio.almacen import Ejemplo, Patron
from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import YA_EN_MARCHA, EstadoEjecucion

router = APIRouter()
PRUEBA = "estilo-prueba"
ROLES = {"jefe_cultura": "Jefe de cultura", "guionista": "Guionista", "director_arte": "Director de arte", "codigo": "Código"}


class Rol(BaseModel):
    id: str
    nombre: str
    activas: int
    tope: int
    fichas: list[Patron]


class LibroEstilo(BaseModel):
    roles: list[Rol]
    ejemplos: list[Ejemplo]
    candidatos: int
    ejemplos_max: int
    github: bool                       # ¿se abren los encargos de código en GitHub?


@router.get("/api/estilo", response_model=LibroEstilo)
def libro(ctx: Contexto = Depends(contexto)):
    import os
    tope = ctx.cfg.pipeline.estilo.max_activas_por_rol
    por_rol: dict[str, list[Patron]] = {r: [] for r in ROLES}
    for f in ctx.almacen.patrones():
        if f.estado in ("rechazada",):
            continue
        por_rol.setdefault("guionista" if f.destino == "formatos" else f.destino, []).append(f)
    roles = [Rol(id=r, nombre=ROLES.get(r, r), activas=sum(f.estado in estilo_vivo.ACTIVAS for f in fs), tope=tope,
                 fichas=sorted(fs, key=lambda f: (f.estado not in estilo_vivo.ACTIVAS, f.estado == "retirada", -f.id)))
             for r, fs in por_rol.items()]
    return LibroEstilo(roles=roles, ejemplos=[e for e in ctx.almacen.ejemplos() if e.estado in ("activo", "retirado")][:30],
                       candidatos=len(ctx.almacen.ejemplos("candidato")), ejemplos_max=ctx.cfg.pipeline.estilo.ejemplos_max,
                       github=bool(os.getenv("FOLIO_GITHUB_TOKEN")))


class Hecho(BaseModel):
    avisos: list[str]


@router.post("/api/estilo/fichas/{fid}/retirar", response_model=Hecho)
def retirar(fid: int, ctx: Contexto = Depends(contexto)):
    if not ctx.almacen.patron(fid):
        raise HTTPException(404, "No existe esa ficha")
    return Hecho(avisos=estilo_vivo.retirar(ctx.cfg, ctx.almacen, fid, "Retirada desde el libro de estilo"))


@router.post("/api/estilo/fichas/{fid}/reactivar", response_model=Hecho)
def reactivar(fid: int, ctx: Contexto = Depends(contexto)):
    f = ctx.almacen.patron(fid)
    if not f or f.estado != "retirada":
        raise HTTPException(404, "No hay una ficha retirada con ese número")
    ctx.almacen.decidir_patron(fid, "aceptada", "Reactivada desde el libro de estilo")
    return Hecho(avisos=[])


@router.post("/api/estilo/fichas/{fid}/probar", response_model=EstadoEjecucion)
def probar(fid: int, ctx: Contexto = Depends(contexto)):
    """Prueba la ficha en el banco en un proceso aparte (~0,30 $, unos minutos)."""
    f = ctx.almacen.patron(fid)
    if not f:
        raise HTTPException(404, "No existe esa ficha")
    if f.destino not in estilo_vivo.PROBABLES:
        raise HTTPException(422, "Solo se prueban en el banco las fichas del guionista (reescribiendo piezas)")
    if f.estado == "aplicada":
        raise HTTPException(422, "Esta ficha ya está escrita en el prompt: no se puede quitar para comparar")
    motivo = ctx.ejecutor.desarrollar(PRUEBA, [[sys.executable, "-m", "folio.cli", "memoria", "probar", str(fid)]])
    if motivo:
        raise HTTPException(409, "Ya se está probando una ficha" if motivo == YA_EN_MARCHA else motivo)
    return ctx.ejecutor.estado_desarrollo(PRUEBA)


@router.get("/api/estilo/prueba", response_model=EstadoEjecucion | None)
def prueba(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado_desarrollo(PRUEBA)


class DecisionEjemplo(BaseModel):
    estado: str


@router.post("/api/estilo/ejemplos/{eid}", response_model=Hecho)
def decidir_ejemplo(eid: int, d: DecisionEjemplo, ctx: Contexto = Depends(contexto)):
    if d.estado not in ("activo", "retirado"):
        raise HTTPException(422, "Estado: activo o retirado")
    if eid not in {e.id for e in ctx.almacen.ejemplos()}:
        raise HTTPException(404, "No existe ese ejemplo")
    ctx.almacen.decidir_ejemplo(eid, d.estado)
    return Hecho(avisos=[])


def prueba_de(f: Patron) -> dict | None:
    try:
        return json.loads(f.prueba) if f.prueba else None
    except ValueError:
        return None
