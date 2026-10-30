"""Enlaces públicos firmados para los archivos que se publican (informes/<fecha>/publicar/<pieza>/).

Instagram descarga cada imagen de una URL pública en el momento de crear la publicación; la web, en
cambio, pide contraseña. Por eso la API sirve /api/publico/<caduca>/<firma>/<fecha>/<pieza>/<archivo>
sin contraseña, pero solo si la firma (HMAC-SHA256 con FOLIO_CLAVE_ENLACES) es buena y no ha caducado.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time

ARCHIVO = re.compile(r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}-[\w-]+/\d{2}\.(jpg|mp4)$")


def _firma(clave: str, caduca: int, ruta: str) -> str:
    return hmac.new(clave.encode(), f"{caduca}/{ruta}".encode(), hashlib.sha256).hexdigest()[:32]


def firmar(base: str, clave: str, ruta: str, segundos: int = 3600, ahora: float | None = None) -> str:
    """URL pública de `ruta` («<fecha>/<pieza>/<nn>.jpg») que vale `segundos`."""
    if not ARCHIVO.match(ruta):
        raise ValueError(f"Ruta no publicable: {ruta}")
    caduca = int((ahora or time.time()) + segundos)
    return f"{base.rstrip('/')}/api/publico/{caduca}/{_firma(clave, caduca, ruta)}/{ruta}"


def valida(clave: str, caduca: int, firma: str, ruta: str, ahora: float | None = None) -> bool:
    return (bool(clave) and bool(ARCHIVO.match(ruta)) and caduca > (ahora or time.time())
            and hmac.compare_digest(firma, _firma(clave, caduca, ruta)))
