"""Lanzar la ejecución del día y seguir su progreso."""

import re
import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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


class EstadoTrabajo(EstadoEjecucion):
    resultado: dict | None = None      # lo que devolvió un trabajo en hilo que acabó bien (p. ej. el tema con su pieza)


@router.get("/api/trabajos/{clave}", response_model=EstadoTrabajo)
def un_trabajo(clave: str, ctx: Contexto = Depends(contexto)):
    """Cómo va un trabajo aparte por su clave (4/11, usabilidad: los temas, las réplicas y lo del fondo se siguen así
    aunque se salga de la página y se vuelva)."""
    import json
    e = ctx.ejecutor.estado_desarrollo(clave)
    if e is None:
        raise HTTPException(404, "No hay ningún trabajo con esa clave")
    r = ctx.ejecutor.resultado(clave) if not e.en_marcha and e.codigo == 0 else None
    return EstadoTrabajo(**e.model_dump(), resultado=json.loads(r) if r else None)


@router.get("/api/trabajos", response_model=list[Trabajo])
def trabajos(ctx: Contexto = Depends(contexto)):
    """Los trabajos en segundo plano de esta sesión de la API (la web avisa cuando acaba cada uno)."""
    return ctx.ejecutor.trabajos()


# «Cinco del libro» a mano (3/11, a petición del usuario: «se me olvidó mergear y son las 6 a.m.»): solo esa pieza, sobre
# las noticias que ya leyó la ejecución del día, sin rehacer la mesa (~0,15 $ y ~125 créditos)
TRABAJO_CINCO = "cinco-del-libro"


TRABAJO_LISTA = "cinco-lista"


class MontarCinco(BaseModel):
    elegidas: list[str] | None = Field(default=None, description="Las cinco historias elegidas, en orden (5/11)")


def _fecha(fecha: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise HTTPException(422, "Fecha no válida")


@router.post("/api/cinco/{fecha}", response_model=EstadoEjecucion, status_code=202)
def lanzar_cinco(fecha: str, cuerpo: MontarCinco | None = None, ctx: Contexto = Depends(contexto)):
    """Escribe y monta el post. Con `elegidas`, con esas (de 3 a 5) y en ese orden (5/11: la redacción elige de la lista)."""
    _fecha(fecha)
    orden = [sys.executable, "-m", "folio.cli", "cinco", "--fecha", fecha, "--quiet"]
    if cuerpo and cuerpo.elegidas is not None:
        from folio import cinco
        minimo, maximo = cinco.cuantas(ctx.cfg)
        if not minimo <= len(cuerpo.elegidas) <= maximo or len(set(cuerpo.elegidas)) != len(cuerpo.elegidas):
            raise HTTPException(422, f"Hay que elegir de {minimo} a {maximo} noticias distintas")
        if any(not re.fullmatch(r"[\w.:-]{1,80}", i) for i in cuerpo.elegidas):
            raise HTTPException(422, "Id de noticia no válido")
        orden += ["--elegidas", ",".join(cuerpo.elegidas)]
    motivo = ctx.ejecutor.desarrollar(TRABAJO_CINCO, [orden])
    if motivo:
        raise HTTPException(409, "Ya se está escribiendo «Cinco del libro»" if motivo == YA_EN_MARCHA else motivo)
    return ctx.ejecutor.estado_desarrollo(TRABAJO_CINCO) or EstadoEjecucion(en_marcha=True)


@router.get("/api/cinco", response_model=EstadoEjecucion)
def estado_cinco(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado_desarrollo(TRABAJO_CINCO) or EstadoEjecucion(en_marcha=False)


# La lista para elegir (5/11, a petición del usuario: «me haga una propuesta de noticias; yo elijo las más importantes y
# finalmente monta el post»). La hace la madrugada; si falta (un día anterior, o falló), se prepara aquí (~30 s, Haiku).
class ListaCinco(BaseModel):
    modo: str                                  # «propuesta» o «automatico» (cinco.modo)
    propuesta: dict | None = None              # cinco.PropuestaCinco


@router.get("/api/cinco/{fecha}/lista", response_model=ListaCinco)
def lista_cinco(fecha: str, ctx: Contexto = Depends(contexto)):
    from folio import cinco
    _fecha(fecha)
    p = cinco.cargar_propuesta(ctx.cfg, fecha)
    return ListaCinco(modo=ctx.cfg.pipeline.cinco.modo, propuesta=p.model_dump() if p else None)


@router.post("/api/cinco/{fecha}/lista", response_model=EstadoEjecucion, status_code=202)
def preparar_lista(fecha: str, ctx: Contexto = Depends(contexto)):
    _fecha(fecha)
    motivo = ctx.ejecutor.desarrollar(TRABAJO_LISTA, [[sys.executable, "-m", "folio.cli", "cinco", "--fecha", fecha,
                                                       "--proponer", "--quiet"]])
    if motivo:
        raise HTTPException(409, "Ya se está preparando la lista" if motivo == YA_EN_MARCHA else motivo)
    return ctx.ejecutor.estado_desarrollo(TRABAJO_LISTA) or EstadoEjecucion(en_marcha=True)


@router.get("/api/cinco-lista", response_model=EstadoEjecucion)
def estado_lista(ctx: Contexto = Depends(contexto)):
    return ctx.ejecutor.estado_desarrollo(TRABAJO_LISTA) or EstadoEjecucion(en_marcha=False)
