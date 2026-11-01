"""Registro del gasto en servicios de pago (1/11, a petición del usuario: un panel en la web).

Cada llamada a Anthropic (con su coste por tokens, el mismo que va al informe) y cada imagen nueva de
Magnific (los créditos que cuesta, del panel de Magnific: la API no lo devuelve) deja un apunte en la
tabla `gastos` de la base de datos de la web. Lo servido desde una caché no se apunta: no se paga.
Apuntar nunca para el pipeline: si la base de datos no está o falla, se sigue.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from folio.config import Config

log = logging.getLogger(__name__)
_almacenes: dict[str, object] = {}
_cerrojo = threading.Lock()


def _almacen(cfg: Config):
    from folio.almacen import Almacen
    clave = str(cfg.ruta_db)
    with _cerrojo:
        if clave not in _almacenes:
            cfg.ruta_db.parent.mkdir(parents=True, exist_ok=True)
            _almacenes[clave] = Almacen(cfg.ruta_db)
        return _almacenes[clave]


def hoy() -> str:
    return datetime.now(ZoneInfo(os.getenv("FOLIO_ZONA") or "Europe/Madrid")).date().isoformat()


def apuntar(cfg: Config, servicio: str, concepto: str, coste: float, moneda: str, unidades: float = 0,
            modelo: str | None = None, detalle: str | None = None) -> None:
    from folio.almacen import Gasto
    try:
        _almacen(cfg).apuntar_gasto(Gasto(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), fecha=hoy(),
                                          servicio=servicio, concepto=concepto, modelo=modelo, unidades=unidades,
                                          coste=round(coste, 6), moneda=moneda, detalle=detalle))
    except Exception as exc:                 # el registro nunca para una pieza
        log.warning("No se pudo apuntar el gasto (%s: %s)", type(exc).__name__, exc)


def imagen_magnific(cfg: Config, concepto: str, detalle: str | None = None) -> None:
    """Una imagen nueva de Magnific (retrato, ilustración o esquema)."""
    g = cfg.pipeline.gasto
    apuntar(cfg, "magnific", concepto, g.magnific_creditos_imagen * g.magnific_euros_credito, "EUR",
            unidades=g.magnific_creditos_imagen, modelo="Seedream 4.5", detalle=detalle)
