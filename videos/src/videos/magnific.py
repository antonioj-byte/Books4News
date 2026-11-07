"""Cliente de Magnific para la beta: texto a imagen (Flux 2 Pro) e imagen a vídeo (Kling O1). Tareas asíncronas:
se crea la tarea, se consulta hasta que termina y se descarga el resultado de la URL firmada.

401/403/429: para sin reintentar y deja Magnific bloqueado el resto del proceso (preferencia de la casa: ante un
bloqueo, parar y avisar). 503: un reintento. La clave nunca sale en los mensajes.
"""
from __future__ import annotations

import base64
import time

import httpx

BASE = "https://api.magnific.com"
FLUX_2_PRO = "/v1/ai/text-to-image/flux-2-pro"
KLING_O1_STD = "/v1/ai/image-to-video/kling-o1-std"
# La consulta de una tarea no siempre va por la misma ruta que su creación: las de Kling O1 (Pro y Standard) se
# consultan en /kling-o1/{id} (7/11, comprobado: /kling-o1-std/{id} da 404 y no está documentado)
CONSULTA = {KLING_O1_STD: "/v1/ai/image-to-video/kling-o1"}
ANCHO, ALTO = 768, 1360            # 9:16 aproximado, múltiplos de 16; se escala a 1080×1920 al montar
ESPERA_S = 3.0
_bloqueo: str | None = None


class ErrorMagnific(RuntimeError):
    def __init__(self, mensaje: str, bloqueo: bool = False):
        super().__init__(mensaje)
        self.bloqueo = bloqueo


def bloqueado() -> str | None:
    return _bloqueo


def _api(c: httpx.Client, clave: str, metodo: str, ruta: str, **kw) -> dict:
    global _bloqueo
    if _bloqueo:
        raise ErrorMagnific(f"Magnific está bloqueado en este proceso: {_bloqueo}", bloqueo=True)
    for intento in (1, 2):
        r = c.request(metodo, BASE + ruta, headers={"x-magnific-api-key": clave}, **kw)
        if r.status_code != 503 or intento == 2:
            break
        time.sleep(ESPERA_S)
    texto = r.text[:300].replace(clave, "***") if clave else r.text[:300]
    if r.status_code in (401, 403, 429):
        _bloqueo = f"{r.status_code}: {texto}"
        raise ErrorMagnific(f"Magnific respondió {r.status_code}; se para sin reintentar ({texto})", bloqueo=True)
    if r.status_code >= 400:
        raise ErrorMagnific(f"Magnific respondió {r.status_code}: {texto}")
    return r.json()["data"]


def pedir(clave: str, ruta: str, cuerpo: dict, espera_max_s: float = 300) -> tuple[bytes, dict]:
    """Crea la tarea, espera y descarga el primer resultado. Devuelve (bytes, tarea)."""
    with httpx.Client(timeout=120) as c:
        t0 = time.monotonic()
        tarea = _api(c, clave, "POST", ruta, json=cuerpo)
        tid = tarea["task_id"]
        while tarea.get("status") not in ("COMPLETED", "FAILED"):
            if time.monotonic() - t0 > espera_max_s:
                raise ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
            time.sleep(ESPERA_S)
            tarea = _api(c, clave, "GET", f"{CONSULTA.get(ruta, ruta)}/{tid}")
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            raise ErrorMagnific(f"La tarea {tid} falló: {str(tarea.get('error'))[:200]}")
        r = c.get(tarea["generated"][0])
        r.raise_for_status()
        tarea["segundos"] = round(time.monotonic() - t0, 1)
        return r.content, tarea


def esperar(clave: str, ruta: str, tid: str, espera_max_s: float = 600) -> tuple[bytes, dict]:
    """Recupera una tarea ya creada (p. ej. tras un corte) sin volver a pagarla."""
    with httpx.Client(timeout=120) as c:
        t0 = time.monotonic()
        while True:
            tarea = _api(c, clave, "GET", f"{CONSULTA.get(ruta, ruta)}/{tid}")
            if tarea.get("status") in ("COMPLETED", "FAILED"):
                break
            if time.monotonic() - t0 > espera_max_s:
                raise ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
            time.sleep(ESPERA_S)
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            raise ErrorMagnific(f"La tarea {tid} falló: {str(tarea.get('error'))[:200]}")
        r = c.get(tarea["generated"][0])
        r.raise_for_status()
        return r.content, tarea


def imagen(clave: str, prompt: str, semilla: int | None = None) -> tuple[bytes, dict]:
    cuerpo = {"prompt": prompt, "width": ANCHO, "height": ALTO}
    if semilla is not None:
        cuerpo["seed"] = semilla
    return pedir(clave, FLUX_2_PRO, cuerpo, espera_max_s=180)


def clip(clave: str, imagen_jpeg: bytes, prompt: str, segundos: int = 5) -> tuple[bytes, dict]:
    cuerpo = {"first_frame": base64.b64encode(imagen_jpeg).decode(), "prompt": prompt[:2500],
              "aspect_ratio": "9:16", "duration": str(segundos)}
    return pedir(clave, KLING_O1_STD, cuerpo, espera_max_s=600)
