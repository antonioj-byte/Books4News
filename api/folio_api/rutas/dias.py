"""Días y portada del día."""

from fastapi import APIRouter, Depends, HTTPException

from folio_api.dependencias import Contexto, contexto
from folio_api.esquemas import Dia, DiaDetalle, Ejecucion, PiezaResumen
from folio_api.servicio import marcas

router = APIRouter()


def _ejecuciones(ctx: Contexto, fecha: str) -> list[Ejecucion]:
    dia = next((d for d in ctx.almacen.dias() if d["fecha"] == fecha), None)
    return [Ejecucion(**e) for e in dia["ejecuciones"]] if dia else []


@router.get("/api/dias", response_model=list[Dia])
def dias(ctx: Contexto = Depends(contexto)):
    return ctx.almacen.dias()


@router.get("/api/dias/{fecha}", response_model=DiaDetalle)
def dia(fecha: str, ejecucion: int | None = None, ctx: Contexto = Depends(contexto)):
    ejecuciones = _ejecuciones(ctx, fecha)
    eid = ejecucion or ctx.almacen.ultima_ejecucion(fecha)
    if not eid or eid not in {e.id for e in ejecuciones}:
        raise HTTPException(404, "No hay ejecuciones para esa fecha")
    _, inf = ctx.ejecucion(eid)
    piezas = [PiezaResumen(
        ejecucion_id=eid, pieza_id=p.id, titular=p.eleccion.titular,
        portada=p.guion.diapositivas[0].texto if p.guion else None, estado=p.estado, n_medios=p.n_medios,
        reserva=p.reserva, version=v, marcas=marcas(p), evaluada=ctx.almacen.evaluacion(eid, p.id) is not None,
    ) for p, v in ctx.almacen.piezas(eid)]
    return DiaDetalle(fecha=fecha, ejecucion=next(e for e in ejecuciones if e.id == eid), ejecuciones=ejecuciones,
                      aviso_jefe=inf.seleccion.aviso if inf.seleccion else None, avisos=inf.avisos,
                      coste_usd=inf.coste_total_usd, piezas=piezas)
