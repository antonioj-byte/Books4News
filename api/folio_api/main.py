"""App FastAPI de la web (Fase 3). Las rutas están en rutas/, una por área."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from folio import config as config_folio
from folio import memoria as memoria_folio
from folio.almacen import Almacen
from folio.config import Config
from folio.render import Plantillas, dir_diseno
from folio_api.dependencias import Contexto
from folio_api.ejecutor import Ejecutor
from folio_api.programador import Lector, Programador, hora_de_entorno, lectura_de_entorno
from folio_api.rutas import dias, diseno, ejecuciones, evaluaciones, gastos, memoria, notas, piezas, publico, temas
from folio_api.servicio import hechos_ligados  # noqa: F401  (se importa desde aquí en los tests)


def crear_app(cfg: Config | None = None, almacen: Almacen | None = None, importar: bool = True,
              ejecutor: Ejecutor | None = None, programador: Programador | None = None) -> FastAPI:
    cfg = cfg or config_folio.cargar()
    almacen = almacen or Almacen(cfg.ruta_db)
    if importar:
        almacen.importar_informes(cfg.dir_informes)
        almacen.importar_gastos_historicos()     # el gasto de las ejecuciones de antes del registro, una vez
        try:                                    # lo decidido en las conversaciones, como reglas aplicadas (2/11)
            almacen.importar_conversacion(memoria_folio.cargar_conversacion(cfg.raiz))
        except Exception:                       # noqa: BLE001 — un archivo mal escrito no impide arrancar la web
            logging.getLogger(__name__).exception("No se pudo cargar config/memoria_conversacion.yaml")
    app = FastAPI(title="Folio · web local", version="0.1.0")
    if ejecutor is None:
        ejecutor = Ejecutor(cfg.dir_datos)
        if lectura_de_entorno():
            # Con lectura periódica, la nevera y la Memoria van de día con ella (2/11): la madrugada solo hace la mesa
            ejecutor.diaria = ejecutor.diaria[:2]
    if programador is None:                     # FOLIO_EJECUCION_DIARIA; sin ella, no se programa nada
        programador = Programador(ejecutor, *hora_de_entorno(), cfg.dir_datos)
        programador.arrancar()
        Lector(ejecutor, lectura_de_entorno()).arrancar()   # FOLIO_LECTURA_CADA; sin ella, no se lee
    app.state.folio = Contexto(cfg=cfg, almacen=almacen, ejecutor=ejecutor, programador=programador,
                               plantillas=Plantillas(cfg, url_medio=diseno.url_medio(cfg.dir_cache("x").parent)))
    app.mount("/diseno", StaticFiles(directory=dir_diseno(cfg)), name="diseno")

    @app.exception_handler(Exception)
    async def error_interno(request: Request, exc: Exception):
        # La web es interna y con contraseña: el motivo del error va en la respuesta (sin claves),
        # para que se vea en pantalla sin tener que entrar en los logs del servidor.
        from folio.libros.fuentes import sin_clave
        logging.getLogger("folio_api").exception("Error en %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": sin_clave(f"{type(exc).__name__}: {exc}")[:600]})

    for modulo in (dias, piezas, diseno, evaluaciones, ejecuciones, gastos, memoria, notas, publico, temas):
        app.include_router(modulo.router)
    return app


def app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn (`folio web`)."""
    return crear_app()
