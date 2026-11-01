"""Días y portada del día."""

from fastapi import APIRouter, Depends, HTTPException

from folio_api.dependencias import Contexto, contexto
from folio_api.esquemas import Dia, DiaDetalle, Ejecucion, Lomo, PiezaResumen
from folio_api.servicio import marcas

router = APIRouter()


def _ejecuciones(ctx: Contexto, fecha: str) -> list[Ejecucion]:
    dia = next((d for d in ctx.almacen.dias() if d["fecha"] == fecha), None)
    return [Ejecucion(**e) for e in dia["ejecuciones"]] if dia else []


def lomos(ctx: Contexto, p) -> list[Lomo]:
    """Los libros de la pieza con su cubierta (de la caché: la mesa y la etapa de arte las dejan allí)."""
    from folio.imagenes import cubiertas
    raiz = ctx.cfg.dir_cache("x").parent
    return [Lomo(titulo=l.titulo_propuesto, autor=l.autores[0] if l.autores else "",
                 cubierta=ctx.plantillas.medios.url_medio(ruta) if (ruta := cubiertas.en_cache(l, raiz)) else None)
            for l in p.libros]


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
        # En el lomo, el título que propuso el jefe: el de la ficha puede venir bilingüe («La Rusia de Putin/ Putin's Russia»)
        libros=lomos(ctx, p), formato=p.eleccion.formato, gancho=p.eleccion.gancho_libro,
        radar=p.radar, por_que=p.eleccion.por_que,
    ) for p, v in ctx.almacen.piezas(eid)]
    return DiaDetalle(fecha=fecha, ejecucion=next(e for e in ejecuciones if e.id == eid), ejecuciones=ejecuciones,
                      aviso_jefe=inf.seleccion.aviso if inf.seleccion else None, avisos=inf.avisos,
                      coste_usd=inf.coste_total_usd, piezas=piezas)
