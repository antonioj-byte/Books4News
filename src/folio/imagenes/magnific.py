"""El cliente único de Magnific (4/11, refactorización «A» de la revisión general: un solo camino para los servicios
externos). Antes, la ilustración editorial, el friso, la banda, el fondo del recorte, «Cinco del libro», el esquema y
los retratos tenían cada uno su copia de la misma llamada: crear la tarea, esperar a que termine, descargar, apuntar el
gasto, guardar en la caché y frenar ante un bloqueo. Si algo cambiaba en Magnific había que arreglarlo en siete sitios.

Aquí está una vez:
- `pedir`: POST de la tarea → consultas cada `ESPERA_S` hasta COMPLETED o FAILED (con un tope de espera) → descarga de
  la URL firmada. Un 503 se reintenta una vez; 401, 403 y 429 no se reintentan y desactivan Magnific el resto de la
  ejecución (preferencia del usuario: ante un bloqueo, parar). La clave va solo en la cabecera y se limpia de los mensajes.
- `imagen`: lo anterior más la caché común (la misma petición no se vuelve a pagar), el apunte del gasto y el guardado.

Las primitivas (la llamada a la API, la espera entre consultas y el estado del bloqueo) siguen en
`folio.imagenes.retrato_generado`, que fue el primero en usar Magnific; los tests las controlan desde ahí.
"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image

from folio import gastos
from folio.config import Config
from folio.imagenes import retrato_generado as rg

ErrorMagnific = rg.ErrorMagnific
FLUX_2_PRO = "/v1/ai/text-to-image/flux-2-pro"


def comprobar(cfg: Config) -> None:
    """ErrorMagnific si no se puede llamar: Magnific bloqueado en esta ejecución o sin clave."""
    if rg.bloqueado():
        raise ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise ErrorMagnific("Falta MAGNIFIC_API_KEY")


def pedir(clave: str, ruta: str, cuerpo: dict, espera_max_s: float, cliente: httpx.Client | None = None) -> tuple[bytes, str, float]:
    """Crea la tarea, espera a que termine y descarga la imagen. Devuelve (bytes, task_id, segundos). ErrorMagnific si
    no se puede; si es un bloqueo (401/403/429), Magnific queda desactivado el resto de la ejecución."""
    try:
        with cliente or httpx.Client(timeout=60) as c:
            t0 = time.monotonic()
            tarea = rg._api(c, clave, "POST", ruta, json=cuerpo)
            tid = tarea["task_id"]
            while tarea.get("status") not in ("COMPLETED", "FAILED"):
                if time.monotonic() - t0 > espera_max_s:
                    raise ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
                time.sleep(rg.ESPERA_S)
                tarea = rg._api(c, clave, "GET", f"{ruta}/{tid}")
            if tarea["status"] == "FAILED" or not tarea.get("generated"):
                raise ErrorMagnific(f"La tarea {tid} falló: {rg._limpiar(str(tarea.get('error'))[:200], clave)}")
            r = c.get(tarea["generated"][0])          # URL firmada del CDN: sin la clave
            r.raise_for_status()
            return r.content, tid, round(time.monotonic() - t0, 1)
    except ErrorMagnific as e:
        if e.bloqueo:
            rg._bloqueo = str(e)
        raise


def imagen(cfg: Config, *, ruta: str, cuerpo: dict, cache: Path, pieza_id: str, concepto: str, modelo: str,
           creditos: int | None = None, espera_max_s: float | None = None, cliente: httpx.Client | None = None,
           procesar: Callable[[bytes], Image.Image] | None = None) -> Path:
    """La imagen de esta petición, de la caché común si ya se pagó; si no, se pide, se apunta el gasto y se guarda en
    `cache` (JPEG, pasada por `procesar` si se da; sin `procesar`, los bytes tal cual). ErrorMagnific si no se puede."""
    if cache.exists():
        return cache
    comprobar(cfg)
    espera = cfg.pipeline.arte.ilustracion_editorial.espera_max_s if espera_max_s is None else espera_max_s
    datos, _, _ = pedir(cfg.magnific_api_key, ruta, cuerpo, espera, cliente)
    gastos.imagen_magnific(cfg, concepto, pieza_id, creditos, modelo)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(cache.name + ".tmp")
    if procesar is None:
        tmp.write_bytes(datos)
    else:
        procesar(datos).save(tmp, "JPEG", quality=90)
    tmp.replace(cache)
    return cache


def rgb(datos: bytes) -> Image.Image:
    """La imagen descargada, en RGB (para guardarla en JPEG)."""
    with Image.open(BytesIO(datos)) as im:
        return im.convert("RGB")
