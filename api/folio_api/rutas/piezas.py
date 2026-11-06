"""Una pieza: detalle, estado, HTML de sus diapositivas y evaluación."""

import logging
from pathlib import Path

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from folio import edicion, materiales
from folio.almacen import Evaluacion, MensajeChat, escribir_evaluacion_md
from folio.llm import LLM, ErrorLLM
from folio.modelos import InformeDiario
from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import EstadoEjecucion
from folio_api.esquemas import (CambioEstado, EdicionDiapositiva, EdicionPie, EstadoBuffer, MensajeNuevo, PiezaDetalle,
                                ProgramadaBuffer, ProgramarBuffer, RespuestaChat, ResultadoEdicion, VideoDiapositiva)
from folio_api.rutas.dias import lomos
from folio_api.servicio import hechos_ligados

# Mientras «Proceder» escribe una pieza, lo que la cambia espera: si no, el último en guardar pisa al otro (revisión
# general, 2/11: una réplica o «Volver a verificar» borraban el guion recién escrito)
ESCRIBIENDOSE = "La pieza se está escribiendo con «Proceder»; espera a que acabe"

router = APIRouter()
log = logging.getLogger(__name__)


def _video(ctx: Contexto, fecha: str, pid: str):
    """El MP4 de la portada que deja `folio render --video` (la ejecución diaria y el botón lo hacen)."""
    return ctx.cfg.dir_informes / fecha / "render" / pid / "01-portada.mp4"


def _render_vigente(ctx: Contexto, eid: int, fecha: str, pid: str, v: int) -> bool:
    """Si lo que hay en render/<pieza>/ es de esta ejecución y versión (render.json lo dice); sin esa
    marca (renders antiguos), solo la versión 1 de la última ejecución del día."""
    import json
    marca = ctx.cfg.dir_informes / fecha / "render" / pid / "render.json"
    if marca.is_file():
        try:
            datos = json.loads(marca.read_text(encoding="utf-8"))
        except ValueError:
            return False
        return datos.get("ejecucion") == eid and datos.get("version") == v
    return v == 1 and ctx.almacen.ultima_ejecucion(fecha) == eid


def _videos(ctx: Contexto, fecha: str, pid: str, p=None) -> dict[int, Path]:
    """Los MP4 de cada diapositiva animada (NN-tipo.mp4), por número; con la pieza, solo los que casan
    con el tipo de su diapositiva actual."""
    carpeta = ctx.cfg.dir_informes / fecha / "render" / pid
    if not carpeta.is_dir():
        return {}
    tipos = {i: d.tipo for i, d in enumerate(p.guion.diapositivas, 1)} if p is not None and p.guion else None
    out = {}
    for f in sorted(carpeta.glob("[0-9][0-9]-*.mp4")):
        n = int(f.name[:2])
        if tipos is None or tipos.get(n) == f.stem[3:]:
            out[n] = f
    return out


@router.get("/api/ejecuciones/{eid}/piezas/{pid}", response_model=PiezaDetalle)
def pieza(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    fecha, inf = ctx.ejecucion(eid)
    p, v = ctx.pieza(eid, pid)
    ev = ctx.almacen.evaluacion(eid, pid)
    vigente = _render_vigente(ctx, eid, fecha, pid, v)
    hay_video = vigente and _video(ctx, fecha, pid).is_file()
    videos = _videos(ctx, fecha, pid, p) if vigente else {}
    return PiezaDetalle(ejecucion_id=eid, fecha=fecha, version=v, pieza=p,
                        aviso_jefe=inf.seleccion.aviso if inf.seleccion else None,
                        hechos_no_verificados=hechos_ligados(p),
                        evaluacion=ev[0] if ev else None, evaluacion_version=ev[1] if ev else None,
                        versiones=ctx.almacen.versiones(eid, pid),
                        video_portada=f"/api/ejecuciones/{eid}/piezas/{pid}/video.mp4" if hay_video else None,
                        videos=[VideoDiapositiva(n=n, url=f"/api/ejecuciones/{eid}/piezas/{pid}/videos/{n}.mp4") for n in videos],
                        total_diapositivas=ctx.plantillas.total(p),
                        lomos=lomos(ctx, p), creditos=_creditos(ctx, p), **_persona(ctx, p))


def _creditos(ctx: Contexto, p) -> list:
    from folio import equipo
    try:
        return equipo.creditos(ctx.cfg, ctx.almacen, p)
    except Exception:                     # los créditos nunca tumban la ficha
        log.exception("Créditos de %s", p.id)
        return []


def _persona(ctx: Contexto, p) -> dict:
    from folio.arte import autor_principal
    from folio.imagenes import libres
    persona = autor_principal(p) if (p.guion or p.libros or p.eleccion.protagonista) else None
    img = libres.de_pieza(f"{p.id}-retrato", ctx.cfg.dir_cache(p.fecha)) if persona else None
    return {"persona": persona, "foto_persona": img.credito if img else None}


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/video.mp4", include_in_schema=False)
def video(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    fecha, _ = ctx.ejecucion(eid)
    _, v = ctx.pieza(eid, pid)
    ruta = _video(ctx, fecha, pid)
    if not ruta.is_file() or not _render_vigente(ctx, eid, fecha, pid, v):
        raise HTTPException(404, "Esta pieza no tiene vídeo de portada")
    return FileResponse(ruta, media_type="video/mp4")


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/videos/{n}.mp4", include_in_schema=False)
def video_diapositiva(eid: int, pid: str, n: int, ctx: Contexto = Depends(contexto)):
    fecha, _ = ctx.ejecucion(eid)
    p, v = ctx.pieza(eid, pid)
    ruta = _videos(ctx, fecha, pid, p).get(n) if _render_vigente(ctx, eid, fecha, pid, v) else None
    if not ruta:
        raise HTTPException(404, "Esta diapositiva no tiene vídeo")
    return FileResponse(ruta, media_type="video/mp4")


@router.patch("/api/ejecuciones/{eid}/piezas/{pid}/estado", response_model=CambioEstado)
def estado(eid: int, pid: str, cambio: CambioEstado, ctx: Contexto = Depends(contexto)):
    ctx.pieza(eid, pid)
    if ctx.ejecutor.en_marcha(pid) and cambio.estado != "descartada":
        raise HTTPException(409, ESCRIBIENDOSE)
    ctx.almacen.cambiar_estado(eid, pid, cambio.estado)
    if cambio.estado == "publicada":            # memoria de lo publicado (3/11): mañana no vuelve la misma historia
        from folio.publicacion import programar as _prog
        _prog.recordar_publicada(ctx.cfg, ctx.pieza(eid, pid)[0], ["a mano"])
    return cambio


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/diapositivas/{n}.html", response_class=HTMLResponse)
def diapositiva(eid: int, pid: str, n: int, version: int | None = None, ctx: Contexto = Depends(contexto)):
    p, _ = ctx.pieza(eid, pid)
    if version:
        p = ctx.almacen.version(eid, pid, version) or p
    if not p.guion or not 1 <= n <= ctx.plantillas.total(p):          # la última puede ser el colofón
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


@router.delete("/api/ejecuciones/{eid}/piezas/{pid}/diapositivas/{n}", response_model=ResultadoEdicion)
def quitar_diapositiva(eid: int, pid: str, n: int, ctx: Contexto = Depends(contexto)):
    """Quita una diapositiva (6/11): una versión nueva («manual»); se deshace volviendo a la versión anterior."""
    p, _ = ctx.pieza(eid, pid)
    if ctx.ejecutor.en_marcha(pid):
        raise HTTPException(409, ESCRIBIENDOSE)
    try:
        nueva, avisos = edicion.quitar_diapositiva(ctx.cfg, p, n)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    v = ctx.almacen.guardar_version(eid, pid, nueva, "manual", f"Diapositiva {n} quitada")
    return ResultadoEdicion(version=v, avisos=avisos)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/versiones/{n}/restaurar", response_model=ResultadoEdicion)
def restaurar_version(eid: int, pid: str, n: int, ctx: Contexto = Depends(contexto)):
    """Vuelve a una versión anterior como versión nueva («deshacer»: las versiones solo se añaden)."""
    ctx.pieza(eid, pid)
    if ctx.ejecutor.en_marcha(pid):
        raise HTTPException(409, ESCRIBIENDOSE)
    vieja = ctx.almacen.version(eid, pid, n)
    if not vieja:
        raise HTTPException(404, "No existe esa versión")
    v = ctx.almacen.guardar_version(eid, pid, vieja, "deshacer", f"Vuelta a la versión {n}")
    return ResultadoEdicion(version=v, avisos=[])


@router.put("/api/ejecuciones/{eid}/piezas/{pid}/pie", response_model=ResultadoEdicion)
def editar_pie(eid: int, pid: str, cambio: EdicionPie, ctx: Contexto = Depends(contexto)):
    """El pie de Instagram editado a mano (4/11): versión nueva («manual»), aunque rompa reglas, con los avisos."""
    p, _ = ctx.pieza(eid, pid)
    if not p.guion:
        raise HTTPException(409, "Esta pieza no tiene guion")
    if ctx.ejecutor.en_marcha(pid):
        raise HTTPException(409, ESCRIBIENDOSE)
    nueva, avisos = edicion.editar_pie(ctx.cfg, p, cambio.pie)
    v = ctx.almacen.guardar_version(eid, pid, nueva, "manual", "Pie editado a mano")
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
    try:
        opciones: list[str] = []
        meta: dict = {}
        respuesta, nueva, avisos = edicion.chat(ctx.llm or LLM(ctx.cfg), ctx.cfg, p, historial, m.mensaje.strip(), opciones,
                                                m.para, meta)
    except ErrorLLM as exc:
        raise HTTPException(502, f"El editor no ha podido responder: {exc}. Prueba otra vez o reformula la petición.")
    except Exception as exc:
        # El 2/11 un turno dio un 500 sin explicación: ahora queda el error completo en el registro y la web lo dice
        log.exception("Chat de edición: %s/%s", eid, pid)
        raise HTTPException(500, f"Error en el chat de edición ({type(exc).__name__}: {str(exc)[:200]}). Está en el registro de la api.")
    v = ctx.almacen.guardar_version(eid, pid, nueva, "chat", m.mensaje.strip()[:120]) if nueva else None
    if nueva and nueva.estado != p.estado:
        # Cambiar el libro desde el chat (2/11) deja la pieza pendiente, para escribirla de nuevo con «Proceder»
        ctx.almacen.cambiar_estado(eid, pid, nueva.estado)
    agente = meta.get("agente") if nueva else "editor_chat"
    ctx.almacen.anadir_mensaje(eid, pid, "usuario", m.mensaje.strip(), para=m.para)
    ctx.almacen.anadir_mensaje(eid, pid, "editor", respuesta, v, opciones, agente=agente)
    return RespuestaChat(respuesta=respuesta, version=v, avisos=avisos, opciones=opciones)


# --- Materiales extra (2/11): fotos, PDF o texto que sube quien edita para el chat ---------------------------

@router.get("/api/ejecuciones/{eid}/piezas/{pid}/materiales", response_model=list[materiales.Material])
def leer_materiales(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    p, _ = ctx.pieza(eid, pid)
    return materiales.lista(ctx.cfg, p)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/materiales", response_model=materiales.Material)
async def subir_material(eid: int, pid: str, request: Request, nombre: str = Query(...), credito: str = Query(""),
                         nota: str = Query(""), ctx: Contexto = Depends(contexto)):
    """El archivo va en el cuerpo, tal cual, con su Content-Type (sin multipart). Como mucho 8 MB."""
    p, _ = ctx.pieza(eid, pid)
    datos = await request.body()
    try:
        return materiales.guardar(ctx.cfg, p, nombre, datos, request.headers.get("content-type", ""), credito, nota)
    except materiales.NoValido as exc:
        raise HTTPException(422, str(exc))


class FotoPuesta(BaseModel):
    version: int | None           # la versión nueva, si la pieza ya tenía arte
    nota: str


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/foto-persona", response_model=FotoPuesta)
async def subir_foto_persona(eid: int, pid: str, request: Request, nombre: str = Query(...), credito: str = Query(...),
                             modificable: bool = Query(False), tratamiento: str = Query("foto"),
                             ctx: Contexto = Depends(contexto)):
    """La foto del autor o protagonista, subida desde la ficha (3/11, a petición del usuario: «muchas veces no la
    encuentra; yo puedo buscar»). Va como retrato al momento, con su crédito en el pie, sin pasar por el chat.
    `tratamiento`: «foto» (tal cual), «papel» o «escena» (recorte en collage; solo si `modificable`). El archivo va en
    el cuerpo, como en los materiales."""
    p, _ = ctx.pieza(eid, pid)
    if ctx.ejecutor.en_marcha(pid):
        raise HTTPException(409, ESCRIBIENDOSE)
    if not " ".join(credito.split()):
        raise HTTPException(422, "Falta el crédito de la foto (va en el pie de la publicación)")
    if tratamiento not in ("foto", "papel", "escena"):
        raise HTTPException(422, "Tratamiento desconocido: foto, papel o escena")
    if tratamiento != "foto" and not modificable:
        raise HTTPException(422, "Para el collage hace falta poder modificar la foto")
    try:
        m = materiales.guardar(ctx.cfg, p, nombre, await request.body(), request.headers.get("content-type", ""),
                               credito, "Foto de la persona, subida desde la ficha")
        if m.tipo != "imagen":
            materiales.borrar(ctx.cfg, p, m.id)
            raise materiales.NoValido("Sube una foto (JPEG, PNG o WebP)")
        nueva, nota = edicion.foto_persona(ctx.llm or LLM(ctx.cfg), ctx.cfg, p, m.id, modificable, tratamiento)
    except (materiales.NoValido, ValueError) as exc:
        raise HTTPException(422, str(exc))
    v = ctx.almacen.guardar_version(eid, pid, nueva, "foto", f"Foto de la persona subida ({m.credito})") if p.arte else None
    return FotoPuesta(version=v, nota=nota)


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/materiales/{mid}", include_in_schema=False)
def ver_material(eid: int, pid: str, mid: str, ctx: Contexto = Depends(contexto)):
    p, _ = ctx.pieza(eid, pid)
    m = materiales.buscar(ctx.cfg, p, mid)
    if not m or not materiales.ruta(ctx.cfg, p, m).exists():
        raise HTTPException(404, "No existe ese material")
    tipo = {"imagen": "image/jpeg", "pdf": "application/pdf", "texto": "text/plain; charset=utf-8"}[m.tipo]
    return FileResponse(materiales.ruta(ctx.cfg, p, m), media_type=tipo)


@router.delete("/api/ejecuciones/{eid}/piezas/{pid}/materiales/{mid}")
def borrar_material(eid: int, pid: str, mid: str, ctx: Contexto = Depends(contexto)):
    p, _ = ctx.pieza(eid, pid)
    if not materiales.borrar(ctx.cfg, p, mid):
        raise HTTPException(404, "No existe ese material")
    return {"borrado": mid}


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
    reutilizar = _render_vigente(ctx, eid, fecha, pid, v) and bool(_videos(ctx, fecha, pid, p))
    lista = preparar(ctx.cfg, p, videos_de=render if reutilizar else None)
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
    unos minutos y unos 0,3 $). Varias piezas a la vez (como mucho tres), pero no mientras se prepara la mesa."""
    import sys
    p, _ = ctx.pieza(eid, pid)
    if p.guion or p.estado not in ("pendiente", "fallida"):
        raise HTTPException(409, "Esta pieza ya está escrita")
    motivo = ctx.ejecutor.desarrollar(pid, [[sys.executable, "-m", "folio.cli", "desarrollar", pid, "--ejecucion", str(eid), "--quiet"]])
    if motivo:
        raise HTTPException(409, motivo)
    return ctx.ejecutor.estado_desarrollo(pid)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/verificar", response_model=PiezaDetalle)
def verificar_de_nuevo(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    """Vuelve a verificar los libros candidatos de una pieza que falló sin libro (2/11: dos piezas de la madrugada
    fallaron porque un catálogo no respondía y no había forma de reintentar). Si ahora pasa alguno, la pieza vuelve a
    la mesa pendiente, lista para «Proceder». Las mismas reglas que la mesa (los temas de la redacción, sin novedad)."""
    from folio.pipeline import Pipeline
    p, _ = ctx.pieza(eid, pid)
    if ctx.ejecutor.en_marcha(pid):
        raise HTTPException(409, ESCRIBIENDOSE)
    if p.guion or p.estado not in ("fallida", "pendiente"):
        raise HTTPException(409, "Esta pieza ya tiene libro y guion")
    nueva = p.model_copy(deep=True)
    nueva.libros, nueva.libros_descartados, nueva.error = [], [], None
    tuberia = Pipeline(ctx.cfg, p.fecha)
    # Las mismas reglas que cuando se propuso, también las excepciones que pidió la redacción (revisión general, 2/11)
    tuberia.aplicar_politica(p.eleccion, p.historia_id.startswith("tema-"))
    ok = tuberia._verificar(nueva, set())
    if ok:
        tuberia._cubiertas_de(nueva)
        nueva.estado = "pendiente"
    else:
        nueva.estado = "fallida"
    ctx.almacen.guardar_version(eid, pid, nueva, "verificacion", "Libros verificados de nuevo" if ok else "Verificación repetida: sin libro")
    ctx.almacen.cambiar_estado(eid, pid, nueva.estado)
    return pieza(eid, pid, ctx)


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/desarrollo", response_model=EstadoEjecucion)
def estado_desarrollo(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    """Cómo va el «Proceder» de esta pieza (cada pieza tiene su proceso y su registro)."""
    e = ctx.ejecutor.estado_desarrollo(pid)
    if e is None:
        raise HTTPException(404, "Esta pieza no se está escribiendo")
    return e


# --- Programar en Buffer (2/11, a petición del usuario: el botón en la web) -----------------------------

def _estado_buffer(ctx: Contexto, fecha: str, pid: str, mensaje: str | None = None) -> EstadoBuffer:
    from folio.publicacion import programar
    faltan = [n for n, v in (("BUFFER_API_KEY", ctx.cfg.buffer_clave), ("FOLIO_URL_PUBLICA", ctx.cfg.url_publica),
                             ("FOLIO_CLAVE_ENLACES", ctx.cfg.clave_enlaces)) if not v]
    def de(hecha: dict | None) -> ProgramadaBuffer | None:
        return ProgramadaBuffer(hora=hecha.get("hora"), borrador=bool(hecha.get("borrador")), canal=hecha.get("canal", ""),
                                en=hecha.get("en"), version=hecha.get("version")) if hecha else None
    return EstadoBuffer(
        disponible=not faltan, motivo=f"Falta configurar {', '.join(faltan)}" if faltan else None,
        programada=de(programar.estado(ctx.cfg, fecha, pid)),
        linkedin=de(programar.estado(ctx.cfg, fecha, pid, "linkedin")), mensaje=mensaje)


@router.get("/api/ejecuciones/{eid}/piezas/{pid}/buffer", response_model=EstadoBuffer)
def estado_buffer(eid: int, pid: str, ctx: Contexto = Depends(contexto)):
    fecha, _ = ctx.ejecucion(eid)
    ctx.pieza(eid, pid)
    return _estado_buffer(ctx, fecha, pid)


@router.post("/api/ejecuciones/{eid}/piezas/{pid}/buffer", response_model=EstadoBuffer)
def programar_buffer(eid: int, pid: str, cuerpo: ProgramarBuffer, ctx: Contexto = Depends(contexto)):
    """Programa en Buffer la pieza aprobada, en su versión actual (lo mismo que `folio buffer programar --confirmar`).
    Pinta el carrusel en el momento si hace falta: puede tardar hasta un minuto."""
    import os

    from folio.publicacion import programar
    from folio.publicacion.buffer import ErrorBuffer
    fecha, _ = ctx.ejecucion(eid)
    p, v = ctx.pieza(eid, pid)
    try:
        cuando = programar.hora_de_publicacion(cuerpo.hora, os.getenv("FOLIO_ZONA") or "Europe/Madrid") if cuerpo.hora else None
    except ValueError as e:
        raise HTTPException(422, str(e))
    render = _video(ctx, fecha, pid).parent
    reutilizar = _render_vigente(ctx, eid, fecha, pid, v) and bool(_videos(ctx, fecha, pid, p))
    try:
        r = programar.programar(ctx.cfg, p, v, fecha, cuando, borrador=cuerpo.borrador, reemplazar=cuerpo.reemplazar,
                                videos_de=render if reutilizar else None, redes=cuerpo.redes)
    except programar.NoSePuede as e:
        raise HTTPException(409, str(e))
    except ErrorBuffer as e:
        raise HTTPException(502, f"Buffer: {e}")
    cuando_txt = cuando.strftime("%d/%m a las %H:%M") if cuando else "en la cola de Buffer"
    mensaje = (f"Borrador guardado en Buffer ({r.canal}): no se publica." if cuerpo.borrador
               else f"Programada en {r.canal}: {cuando_txt}.") + (f" Avisos: {'; '.join(r.avisos)}" if r.avisos else "")
    return _estado_buffer(ctx, fecha, pid, mensaje)
