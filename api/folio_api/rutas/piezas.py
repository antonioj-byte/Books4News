"""Una pieza: detalle, estado, HTML de sus diapositivas y evaluación."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from folio import edicion
from folio.almacen import Evaluacion, MensajeChat, escribir_evaluacion_md
from folio.llm import LLM
from folio.modelos import InformeDiario
from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import EstadoEjecucion
from folio_api.esquemas import (CambioEstado, EdicionDiapositiva, MensajeNuevo, PiezaDetalle, RespuestaChat,
                                ResultadoEdicion)
from folio_api.rutas.dias import lomos
from folio_api.servicio import hechos_ligados

router = APIRouter()


def _video(ctx: Contexto, fecha: str, pid: str):
    """El MP4 de la portada que deja `folio render --video` (la ejecución diaria y el botón lo hacen)."""
    return ctx.cfg.dir_informes / fecha / "render" / pid / "01-portada.mp4"


@router.get("/api/ejecuciones/{eid}/piezas/{pid}", response_model=PiezaDetalle)
def pieza(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    fecha, inf = ctx.ejecucion(eid)
    p, v = ctx.pieza(eid, pid)
    ev = ctx.almacen.evaluacion(eid, pid)
    hay_video = v == 1 and _video(ctx, fecha, pid).is_file()
    return PiezaDetalle(ejecucion_id=eid, fecha=fecha, version=v, pieza=p,
                        aviso_jefe=inf.seleccion.aviso if inf.seleccion else None,
                        hechos_no_verificados=hechos_ligados(p),
                        evaluacion=ev[0] if ev else None, evaluacion_version=ev[1] if ev else None,
                        versiones=ctx.almacen.versiones(eid, pid),
                        video_portada=f"/api/ejecuciones/{eid}/piezas/{pid}/video.mp4" if hay_video else None,
                        lomos=lomos(ctx, p))


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/video.mp4", include_in_schema=False)
def video(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    fecha, _ = ctx.ejecucion(eid)
    ctx.pieza(eid, pid)
    ruta = _video(ctx, fecha, pid)
    if not ruta.is_file():
        raise HTTPException(404, "Esta pieza no tiene vídeo de portada")
    return FileResponse(ruta, media_type="video/mp4")


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


@router.put("/api/ejecuciones/{eid}/piezas/{pid}/diapositivas/{n}", response_model=ResultadoEdicion)
def editar_diapositiva(eid: int, pid: str, n: int, cambio: EdicionDiapositiva, ctx: Contexto = Depends(contexto)):
    """Edición directa sobre la diapositiva: una versión nueva («manual»). Si rompe alguna regla del
    guion se guarda igual y la respuesta trae los avisos."""
    p, _ = ctx.pieza(eid, pid)
    if not p.guion or not 1 <= n <= len(p.guion.diapositivas):
        raise HTTPException(404, "Diapositiva no encontrada")
    nueva, avisos = edicion.editar_diapositiva(ctx.cfg, p, n, cambio.texto, cambio.subtitulo)
    v = ctx.almacen.guardar_version(eid, pid, nueva, "manual", f"Diapositiva {n} editada a mano")
    return ResultadoEdicion(version=v, avisos=avisos)


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/chat", response_model=list[MensajeChat])
def leer_chat(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    ctx.pieza(eid, pid)
    return ctx.almacen.chat(eid, pid)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/chat", response_model=RespuestaChat)
def escribir_chat(eid: int, pid: str, m: MensajeNuevo, ctx: Contexto = Depends(contexto)):
    """Un turno del chat de edición (Opus, unos céntimos). Si el editor cambia la pieza, es una versión
    nueva («chat») que ya ha pasado las reglas del guion."""
    p, _ = ctx.pieza(eid, pid)
    if not p.guion:
        raise HTTPException(409, "Esta pieza no tiene guion")
    historial = [(x.rol, x.texto) for x in ctx.almacen.chat(eid, pid)]
    respuesta, nueva, avisos = edicion.chat(ctx.llm or LLM(ctx.cfg), ctx.cfg, p, historial, m.mensaje.strip())
    v = ctx.almacen.guardar_version(eid, pid, nueva, "chat", m.mensaje.strip()[:120]) if nueva else None
    ctx.almacen.anadir_mensaje(eid, pid, "usuario", m.mensaje.strip())
    ctx.almacen.anadir_mensaje(eid, pid, "editor", respuesta, v)
    return RespuestaChat(respuesta=respuesta, version=v, avisos=avisos)


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/descarga.zip", include_in_schema=False)
def descargar(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    """El carrusel listo para publicar, en su versión actual: JPEG de cada diapositiva (1080×1350),
    en vídeo las diapositivas animadas y pie.txt con los créditos. Se pinta en el momento (hasta unos
    minutos); si la pieza no se ha editado, reutiliza los vídeos que dejó el render del día."""
    import io
    import zipfile

    from folio.publicacion.preparar import preparar
    fecha, _ = ctx.ejecucion(eid)
    p, v = ctx.pieza(eid, pid)
    if not p.guion:
        raise HTTPException(409, "Esta pieza no tiene guion")
    render = _video(ctx, fecha, pid).parent
    lista = preparar(ctx.cfg, p, videos_de=render if v == 1 and any(render.glob("[0-9][0-9]-*.mp4")) else None)
    zona = io.BytesIO()
    with zipfile.ZipFile(zona, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(lista.carpeta.iterdir()):
            if f.suffix in (".jpg", ".mp4", ".txt"):
                z.write(f, f.name)
    nombre = f"folio-{pid}-v{v}.zip"
    return Response(zona.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/desarrollar", response_model=EstadoEjecucion, status_code=202)
def desarrollar(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    """«Proceder»: escribe una propuesta pendiente de la mesa (`folio desarrollar`, en un proceso aparte;
    unos minutos y unos 0,3 $). Comparte turno con la ejecución del día: una cosa a la vez."""
    import sys
    p, _ = ctx.pieza(eid, pid)
    if p.guion or p.estado not in ("pendiente", "fallida"):
        raise HTTPException(409, "Esta pieza ya está escrita")
    if not ctx.ejecutor.lanzar([[sys.executable, "-m", "folio.cli", "desarrollar", pid, "--ejecucion", str(eid), "--quiet"]]):
        raise HTTPException(409, "Hay otra ejecución en marcha; prueba cuando termine")
    return ctx.ejecutor.estado()
