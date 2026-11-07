"""API de la beta y la interfaz del asistente (estática, en `videos/web/`). Servicio aparte de Folio:
`uv run videos web` en http://127.0.0.1:8100.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from videos import almacen, conceptos, estilo, guion, imagenes, montaje, musica, trabajos, transcripcion, voz
from videos.config import RAIZ, Config
from videos.llm import LLM

log = logging.getLogger(__name__)
MAX_LIBRO = 60 * 1024 * 1024
WEB = RAIZ / "web"


class Mensaje(BaseModel):
    texto: str = Field(min_length=2, max_length=4000)


class Peticion(BaseModel):
    indicaciones: str = Field(default="", max_length=2000)


class Eleccion(BaseModel):
    concepto: str


class EleccionEstilo(BaseModel):
    preset: str | None = None
    peticion: str = Field(default="", max_length=2000)


class EleccionVariante(BaseModel):
    indice: int


class Texto(BaseModel):
    texto: str = Field(default="", max_length=400)


class Musica(BaseModel):
    activa: bool


class Edicion(BaseModel):
    cambios: dict[str, dict] = Field(default_factory=dict)
    quitar: list[str] = Field(default_factory=list)
    anadir_tras: str | None = None


def crear_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config()
    app = FastAPI(title="Alighieria · vídeos conceptuales (beta)")

    def proyecto(pid: str):
        try:
            return almacen.cargar(cfg, pid)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "No existe ese proyecto")

    def lanzar(pid: str, etapa: str, fn) -> dict:
        proyecto(pid)
        llm = LLM(cfg, al_gastar=almacen.apuntar_gasto(cfg, pid, etapa))
        try:
            return {"trabajo": trabajos.lanzar(cfg, pid, etapa, lambda anunciar: fn(llm, anunciar))}
        except trabajos.YaEnMarcha as e:
            raise HTTPException(409, str(e))

    @app.get("/api/estado")
    def estado():
        return {"simulado": {"magnific": cfg.magnific_simulado, "elevenlabs": cfg.elevenlabs_simulado},
                "anthropic": bool(cfg.anthropic_api_key)}

    @app.get("/api/proyectos")
    def proyectos():
        return almacen.lista(cfg)

    @app.post("/api/proyectos")
    async def crear(archivo: UploadFile | None = File(None), texto: str = Form(""), titulo: str = Form(""),
                    autor: str = Form(""), tipo: str = Form("libro")):
        """La fuente: un archivo (EPUB, PDF, TXT o una nota de voz) o un texto pegado."""
        if archivo is not None and archivo.filename:
            contenido, nombre = await archivo.read(), archivo.filename
        elif texto.strip():
            contenido, nombre = texto.encode("utf-8"), almacen.PEGADO
        else:
            raise HTTPException(422, "Sube un archivo o pega el texto.")
        if len(contenido) > MAX_LIBRO:
            raise HTTPException(413, "El archivo pasa de 60 MB.")
        try:
            p = await run_in_threadpool(almacen.crear, cfg, nombre, contenido, titulo, autor, tipo)
        except (ValueError, transcripcion.ErrorTranscripcion) as e:
            raise HTTPException(422, str(e))
        except Exception as e:
            log.exception("Ingesta fallida")
            raise HTTPException(422, f"No se pudo leer el libro: {type(e).__name__}: {e}")
        return p.model_dump()

    @app.get("/api/proyectos/{pid}")
    def ver(pid: str):
        p = proyecto(pid)
        d = p.model_dump()
        d["guion_actual"] = p.guion_actual.model_dump() if p.guion_actual else None
        d["gasto_total_usd"] = round(sum(g.usd for g in p.gasto), 3)
        dir_m = almacen.carpeta(cfg, pid) / "muestras"
        d["muestras"] = sorted(f.stem for f in dir_m.glob("*.jpg")) if dir_m.exists() else []
        return d

    @app.post("/api/proyectos/{pid}/conceptos")
    def proponer(pid: str, peticion: Peticion):
        return lanzar(pid, "conceptos",
                      lambda llm, a: len(conceptos.proponer(cfg, llm, pid, peticion.indicaciones, a)))

    @app.post("/api/proyectos/{pid}/conceptos/chat")
    def chat_conceptos(pid: str, m: Mensaje):
        return lanzar(pid, "conceptos", lambda llm, a: conceptos.chat(cfg, llm, pid, m.texto, a))

    @app.post("/api/proyectos/{pid}/conceptos/elegir")
    def elegir(pid: str, e: Eleccion):
        proyecto(pid)
        try:
            conceptos.elegir(cfg, pid, e.concepto)
        except ValueError as x:
            raise HTTPException(409, str(x))
        return {"ok": True}

    @app.post("/api/proyectos/{pid}/guion")
    def escribir(pid: str):
        p = proyecto(pid)
        if not p.concepto_elegido:
            raise HTTPException(409, "Elige antes un concepto")
        if p.etapas["guion"].estado == "bloqueado":
            raise HTTPException(409, "El guion está aprobado: desbloquéalo para rehacerlo")
        return lanzar(pid, "guion", lambda llm, a: guion.escribir(cfg, llm, pid, a).n)

    @app.post("/api/proyectos/{pid}/guion/chat")
    def chat_guion(pid: str, m: Mensaje):
        p = proyecto(pid)
        if p.etapas["guion"].estado == "bloqueado":
            raise HTTPException(409, "El guion está aprobado: desbloquéalo para cambiarlo")
        return lanzar(pid, "guion", lambda llm, a: guion.chat(cfg, llm, pid, m.texto, a))

    @app.put("/api/proyectos/{pid}/guion")
    def editar(pid: str, e: Edicion):
        proyecto(pid)
        try:
            v = guion.editar(cfg, pid, e.cambios, e.quitar, e.anadir_tras)
        except ValueError as x:
            raise HTTPException(409, str(x))
        return v.model_dump()

    @app.post("/api/proyectos/{pid}/guion/aprobar")
    def aprobar(pid: str):
        proyecto(pid)
        try:
            guion.aprobar(cfg, pid)
        except ValueError as x:
            raise HTTPException(409, str(x))
        return {"ok": True}

    @app.post("/api/proyectos/{pid}/guion/desbloquear")
    def desbloquear(pid: str):
        proyecto(pid)
        guion.desbloquear(cfg, pid)
        return {"ok": True}

    # ── Estilo ──
    @app.get("/api/estilos")
    def estilos():
        return estilo.predefinidos()

    @app.post("/api/proyectos/{pid}/estilo/muestras")
    def muestras(pid: str):
        return lanzar(pid, "estilo", lambda llm, a: imagenes.muestras(cfg, llm, pid, a))

    @app.post("/api/proyectos/{pid}/estilo")
    def elegir_estilo(pid: str, e: EleccionEstilo):
        p = proyecto(pid)
        if p.etapas["guion"].estado != "bloqueado":
            raise HTTPException(409, "Aprueba antes el guion")
        if e.preset:
            try:
                estilo.elegir(cfg, pid, e.preset)
            except ValueError as x:
                raise HTTPException(409, str(x))
            return {"ok": True}
        if len(e.peticion.strip()) < 8:
            raise HTTPException(422, "Describe el estilo que quieres en una frase")
        return lanzar(pid, "estilo", lambda llm, a: estilo.propio(cfg, llm, pid, e.peticion, a).nombre)

    # ── Voz ──
    @app.post("/api/proyectos/{pid}/voz")
    def generar_voz(pid: str):
        p = proyecto(pid)
        if p.etapas["guion"].estado != "bloqueado":
            raise HTTPException(409, "Aprueba antes el guion")
        return lanzar(pid, "voz", lambda llm, a: voz.generar(cfg, pid, a).duracion)

    @app.post("/api/proyectos/{pid}/planos/{plano}/voz")
    def rehacer_voz(pid: str, plano: str, t: Texto):
        if len(t.texto.strip()) < 2:
            raise HTTPException(422, "Escribe la locución nueva")
        return lanzar(pid, "voz", lambda llm, a: voz.rehacer_plano(cfg, pid, plano, t.texto, a).duracion)

    # ── Imágenes ──
    @app.post("/api/proyectos/{pid}/imagenes")
    def generar_imagenes(pid: str):
        p = proyecto(pid)
        if p.estilo is None:
            raise HTTPException(409, "Elige antes el estilo")
        return lanzar(pid, "imagenes", lambda llm, a: imagenes.generar_todas(cfg, llm, pid, a))

    @app.post("/api/proyectos/{pid}/planos/{plano}/imagenes")
    def otras_imagenes(pid: str, plano: str):
        return lanzar(pid, "imagenes", lambda llm, a: imagenes.generar_plano(cfg, llm, pid, plano, a))

    @app.post("/api/proyectos/{pid}/planos/{plano}/elegir")
    def elegir_variante(pid: str, plano: str, e: EleccionVariante):
        proyecto(pid)
        try:
            imagenes.elegir(cfg, pid, plano, e.indice)
        except ValueError as x:
            raise HTTPException(409, str(x))
        return {"ok": True}

    @app.post("/api/proyectos/{pid}/clips")
    def generar_clips(pid: str):
        return lanzar(pid, "imagenes", lambda llm, a: imagenes.clips(cfg, llm, pid, a))

    @app.put("/api/proyectos/{pid}/planos/{plano}/pantalla")
    def cambiar_pantalla(pid: str, plano: str, t: Texto):
        """Revisión: cambia el texto en pantalla de un plano sin desbloquear el guion (versión «manual»)."""
        from videos.modelos import VersionGuion
        with almacen.editar(cfg, pid) as p:
            v = p.guion_actual
            if v is None or plano not in {x.id for x in v.planos}:
                raise HTTPException(404, "Ese plano no existe")
            nuevos = [x.model_copy(deep=True) for x in v.planos]
            for x in nuevos:
                if x.id == plano:
                    x.pantalla = t.texto.strip()
            p.guion.append(VersionGuion(n=len(p.guion) + 1, concepto=v.concepto, origen="manual", titulo=v.titulo,
                                        planos=nuevos, avisos=[f"Texto en pantalla del plano {plano} cambiado en la revisión"]))
            if p.etapas["montaje"].estado == "hecha":
                p.etapas["montaje"].estado = "desfasada"
        return {"ok": True}

    # ── Música y montaje ──
    @app.post("/api/proyectos/{pid}/musica")
    def generar_musica(pid: str):
        return lanzar(pid, "voz", lambda llm, a: musica.generar(cfg, pid, a))

    @app.put("/api/proyectos/{pid}/musica")
    def activar_musica(pid: str, m: Musica):
        with almacen.editar(cfg, pid) as p:
            p.musica_activa = m.activa and bool(p.musica)
        return {"ok": True}

    @app.post("/api/proyectos/{pid}/montaje")
    def montar(pid: str):
        return lanzar(pid, "montaje", lambda llm, a: montaje.montar(cfg, pid, a).archivo)

    @app.get("/api/proyectos/{pid}/archivo/{ruta:path}")
    def archivo(pid: str, ruta: str):
        base = almacen.carpeta(cfg, pid).resolve()
        destino = (base / ruta).resolve()
        if base not in destino.parents or not destino.is_file():
            raise HTTPException(404, "No existe ese archivo")
        return FileResponse(destino)

    @app.get("/api/trabajos/{tid}")
    def trabajo(tid: str):
        try:
            return trabajos.estado(cfg, tid)
        except FileNotFoundError:
            raise HTTPException(404, "No existe ese trabajo")

    @app.get("/")
    def inicio():
        return FileResponse(WEB / "index.html")

    app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app
