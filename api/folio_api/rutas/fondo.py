"""El fondo del mes (2/11, a petición del usuario): propuestas de actualidad lateral que valen unos meses
(folio.fondo). Se listan, se escriben (como un tema de la redacción, que busca lo último del tema) o se descartan, y se
preparan tandas nuevas en un proceso aparte."""

import sys
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from folio import fondo as fondo_folio
from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import EstadoEjecucion
from folio_api.rutas.temas import TemaCreado, _resultado

router = APIRouter()
TRABAJO = "fondo-del-mes"                   # nombre del proceso de preparación en el ejecutor


class PropuestaDelFondo(BaseModel):
    id: int
    mes: str
    formato: str
    titular: str
    cuestion: str
    vale_hasta: str
    estado: str
    tema_id: int | None = None
    de_que_se_habla: str = ""
    gancho_libro: str = ""
    por_que_dura: str = ""
    reactivar: str = ""
    potencial: int = 5
    puente: int | None = None
    libros: list[str] = []
    cosecha: str = ""                     # el tema de la cosecha en que se basa (días y medios)


class Fondo(BaseModel):
    propuestas: list[PropuestaDelFondo]
    preparando: EstadoEjecucion | None = None
    objetivo: dict[str, int] = {}


class Escribir(BaseModel):
    ejecucion: int


class Preparar(BaseModel):
    tandas: int = Field(default=1, ge=1, le=6)


def _propuesta(x: dict) -> PropuestaDelFondo:
    p, d = x["datos"]["propuesta"], x["datos"]
    c = d.get("cosecha")
    return PropuestaDelFondo(
        **{k: x[k] for k in ("id", "mes", "formato", "titular", "cuestion", "vale_hasta", "estado", "tema_id")},
        de_que_se_habla=p.get("de_que_se_habla", ""), gancho_libro=p.get("gancho_libro", ""),
        por_que_dura=p.get("por_que_dura", ""), reactivar=p.get("reactivar", ""), potencial=p.get("potencial", 5),
        puente=(d.get("puente") or [None])[0],
        libros=[f"{l['titulo_propuesto']} · {', '.join(l['autores'][:2])}" for l in d.get("libros", [])],
        cosecha=f"{c['titular']} ({c['dias']} días, {c['medios']} medios)" if c else "")


@router.get("/api/fondo", response_model=Fondo)
def lista(ctx: Contexto = Depends(contexto)):
    """Las disponibles que no han caducado, las usadas y las descartadas (las caducadas no se enseñan)."""
    hoy = date.today().isoformat()
    xs = [x for x in ctx.almacen.fondo() if x["estado"] != "disponible" or x["vale_hasta"] >= hoy]
    return Fondo(propuestas=[_propuesta(x) for x in reversed(xs)], preparando=ctx.ejecutor.estado_desarrollo(TRABAJO),
                 objetivo=fondo_folio.REPARTO_MES)


def _una(ctx: Contexto, fid: int) -> dict:
    x = next((x for x in ctx.almacen.fondo() if x["id"] == fid), None)
    if not x:
        raise HTTPException(404, "No existe esa propuesta del fondo")
    return x


@router.post("/api/fondo/{fid}/escribir", response_model=TemaCreado)
def escribir(fid: int, e: Escribir, ctx: Contexto = Depends(contexto)):
    """La propuesta entra en la mesa como un tema de la redacción: se buscan sus noticias más recientes, el jefe la
    ajusta y se verifican sus libros (uno o dos minutos y unos céntimos)."""
    x = _una(ctx, fid)
    if x["estado"] != "disponible":
        raise HTTPException(409, f"La propuesta ya está «{x['estado']}»")
    if ctx.ejecutor.con_pipeline():
        raise HTTPException(409, "Se está preparando la mesa del día; prueba cuando termine")
    tid = ctx.almacen.guardar_tema(fondo_folio.texto_tema(x), [], "ahora")
    r = _resultado(ctx, e.ejecucion, tid)
    if r.pieza_id:
        ctx.almacen.actualizar_fondo(fid, estado="usada", tema_id=tid)
    return r


@router.post("/api/fondo/{fid}/descartar", response_model=PropuestaDelFondo)
def descartar(fid: int, ctx: Contexto = Depends(contexto)):
    x = _una(ctx, fid)
    if x["estado"] != "disponible":
        raise HTTPException(409, f"La propuesta ya está «{x['estado']}»")
    ctx.almacen.actualizar_fondo(fid, estado="descartada")
    return _propuesta(_una(ctx, fid))


@router.post("/api/fondo/preparar", response_model=EstadoEjecucion)
def preparar(p: Preparar, ctx: Contexto = Depends(contexto)):
    """Lanza tandas nuevas del fondo en un proceso aparte (~0,30 $ y varios minutos cada una)."""
    motivo = ctx.ejecutor.desarrollar(TRABAJO, [[sys.executable, "-m", "folio.cli", "fondo", "preparar",
                                                 "--tandas", str(p.tandas)]])
    if motivo:
        raise HTTPException(409, "Ya se está preparando el fondo" if "ya se está" in motivo.lower() else motivo)
    return ctx.ejecutor.estado_desarrollo(TRABAJO)
