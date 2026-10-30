"""Una pieza: detalle, estado, HTML de sus diapositivas y evaluación."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from folio.almacen import Evaluacion, escribir_evaluacion_md
from folio.modelos import InformeDiario
from folio_api.dependencias import Contexto, contexto
from folio_api.esquemas import CambioEstado, PiezaDetalle
from folio_api.servicio import hechos_ligados

router = APIRouter()


@router.get("/api/ejecuciones/{eid}/piezas/{pid}", response_model=PiezaDetalle)
def pieza(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    fecha, inf = ctx.ejecucion(eid)
    p, v = ctx.pieza(eid, pid)
    ev = ctx.almacen.evaluacion(eid, pid)
    return PiezaDetalle(ejecucion_id=eid, fecha=fecha, version=v, pieza=p,
                        aviso_jefe=inf.seleccion.aviso if inf.seleccion else None,
                        hechos_no_verificados=hechos_ligados(p),
                        evaluacion=ev[0] if ev else None, evaluacion_version=ev[1] if ev else None,
                        versiones=ctx.almacen.versiones(eid, pid))


@router.patch("/api/ejecuciones/{eid}/piezas/{pid}/estado", response_model=CambioEstado)
def estado(eid: int, pid: str, cambio: CambioEstado, ctx: Contexto = Depends(contexto)):
    ctx.pieza(eid, pid)
    ctx.almacen.cambiar_estado(eid, pid, cambio.estado)
    return cambio


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/diapositivas/{n}.html", response_class=HTMLResponse)
def diapositiva(eid: int, pid: str, n: int, version: int | None = None, ctx: Contexto = Depends(contexto)):
    p, _ = ctx.pieza(eid, pid)
    if version:
        p = ctx.almacen.version(eid, pid, version) or p
    if not p.guion or not 1 <= n <= len(p.guion.diapositivas):
        raise HTTPException(404, "Diapositiva no encontrada")
    return ctx.plantillas.html_diapositiva(p, n, base_url="/diseno/")


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/evaluacion", response_model=Evaluacion | None)
def leer_evaluacion(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    ev = ctx.almacen.evaluacion(eid, pid)
    return ev[0] if ev else None


@router.put("/api/ejecuciones/{eid}/piezas/{pid}/evaluacion", response_model=Evaluacion)
def guardar_evaluacion(eid: int, pid: str, ev: Evaluacion, ctx: Contexto = Depends(contexto)):
    fecha, inf = ctx.ejecucion(eid)
    _, v = ctx.pieza(eid, pid)
    ctx.almacen.guardar_evaluacion(eid, pid, ev, v)
    # Copia en informe.md, si ese informe es el de esta ejecución (el formato de la Fase 1)
    ruta_json = ctx.cfg.dir_informes / fecha / "informe.json"
    if ruta_json.exists() and InformeDiario.model_validate_json(ruta_json.read_text(encoding="utf-8")).generado_en == inf.generado_en:
        escribir_evaluacion_md(ctx.cfg.dir_informes / fecha / "informe.md", pid, ev)
    return ev
