"""API de la beta y la interfaz del asistente (estática, en `videos/web/`). Servicio aparte de Folio:
`uv run videos web` en http://127.0.0.1:8100.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from videos import almacen, conceptos, guion, trabajos
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
    async def crear(archivo: UploadFile = File(...), titulo: str = Form(""), autor: str = Form("")):
        contenido = await archivo.read()
        if len(contenido) > MAX_LIBRO:
            raise HTTPException(413, "El libro pasa de 60 MB.")
        try:
            p = almacen.crear(cfg, archivo.filename or "libro.txt", contenido, titulo, autor)
        except ValueError as e:
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
