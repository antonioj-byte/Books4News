"""Lanzar la ejecución del día y seguir su progreso."""

import re
import sys

from fastapi import APIRouter, Depends, HTTPException

from folio_api.dependencias import Contexto, contexto
from folio_api.ejecutor import YA_EN_MARCHA, EstadoEjecucion, Trabajo
from folio_api.programador import EstadoProgramada

router = APIRouter()


@router.post("/api/ejecuciones/lanzar", response_model=EstadoEjecucion, status_code=202)
def lanzar(ctx: Contexto = Depends(contexto)):
    """Lanza la ejecución del día, igual que la diaria: `folio run` (~1 $) y después el render (PNG y
    vídeos de las diapositivas animadas). La ejecución aparece en la portada del día en cuanto termina el pipeline (la
    guarda en la base de datos); el vídeo, cuando termina el render."""
    if not ctx.ejecutor.lanzar(ctx.ejecutor.diaria):
        raise HTTPException(409, ctx.ejecutor.motivo_ocupado() or "Ya hay una ejecución en marcha")
    return ctx.ejecutor.estado()


@router.get("/api/ejecuciones/en-marcha", response_model=EstadoEjecucion)
def en_marcha(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado()


@router.get("/api/ejecuciones/programada", response_model=EstadoProgramada)
def programada(ctx: Contexto = Depends(contexto)):
    """La ejecución diaria automática (FOLIO_EJECUCION_DIARIA): si está activa, a qué hora y cuándo toca."""
    return ctx.programador.estado() if ctx.programador else EstadoProgramada(activa=False)


@router.get("/api/trabajos", response_model=list[Trabajo])
def trabajos(ctx: Contexto = Depends(contexto)):
    """Los trabajos en segundo plano de esta sesión de la API (la web avisa cuando acaba cada uno)."""
    return ctx.ejecutor.trabajos()


# «Cinco del libro» a mano (3/11, a petición del usuario: «se me olvidó mergear y son las 6 a.m.»): solo esa pieza, sobre
# las noticias que ya leyó la ejecución del día, sin rehacer la mesa (~0,15 $ y ~125 créditos)
TRABAJO_CINCO = "cinco-del-libro"


@router.post("/api/cinco/{fecha}", response_model=EstadoEjecucion, status_code=202)
def lanzar_cinco(fecha: str, ctx: Contexto = Depends(contexto)):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise HTTPException(422, "Fecha no válida")
    motivo = ctx.ejecutor.desarrollar(TRABAJO_CINCO, [[sys.executable, "-m", "folio.cli", "cinco", "--fecha", fecha, "--quiet"]])
    if motivo:
        raise HTTPException(409, "Ya se está escribiendo «Cinco del libro»" if motivo == YA_EN_MARCHA else motivo)
    return ctx.ejecutor.estado_desarrollo(TRABAJO_CINCO) or EstadoEjecucion(en_marcha=True)


@router.get("/api/cinco", response_model=EstadoEjecucion)
def estado_cinco(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado_desarrollo(TRABAJO_CINCO) or EstadoEjecucion(en_marcha=False)
