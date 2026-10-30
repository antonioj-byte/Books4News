"""App FastAPI de la web (Fase 3). Las rutas están en rutas/, una por área."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from folio import config as config_folio
from folio.almacen import Almacen
from folio.config import Config
from folio.render import Plantillas, dir_diseno
from folio_api.dependencias import Contexto
from folio_api.ejecutor import Ejecutor
from folio_api.rutas import dias, diseno, ejecuciones, evaluaciones, piezas
from folio_api.servicio import hechos_ligados  # noqa: F401  (se importa desde aquí en los tests)


def crear_app(cfg: Config | None = None, almacen: Almacen | None = None, importar: bool = True,
              ejecutor: Ejecutor | None = None) -> FastAPI:
    cfg = cfg or config_folio.cargar()
    almacen = almacen or Almacen(cfg.ruta_db)
    if importar:
        almacen.importar_informes(cfg.dir_informes)
    app = FastAPI(title="Folio · web local", version="0.1.0")
    app.state.folio = Contexto(cfg=cfg, almacen=almacen, ejecutor=ejecutor or Ejecutor(cfg.dir_datos),
                               plantillas=Plantillas(cfg))
    app.mount("/diseno", StaticFiles(directory=dir_diseno(cfg)), name="diseno")
    for modulo in (dias, piezas, diseno, evaluaciones, ejecuciones):
        app.include_router(modulo.router)
    return app


def app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn (`folio web`)."""
    return crear_app()
