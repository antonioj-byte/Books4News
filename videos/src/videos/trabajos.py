"""Cola de trabajos para las llamadas lentas: un grupo de hilos y un archivo por trabajo en `data/trabajos/`.

Sin Redis ni Celery en la beta. La web sigue cada trabajo por su id (paso actual, reloj, error en una frase) y puede
salir de la página. Un trabajo cortado por un reinicio queda «interrumpido» al volver a leerlo.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from videos import almacen
from videos.config import Config
from videos.modelos import ahora

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="videos")
_vivos: set[str] = set()
_cerrojo = threading.Lock()


class YaEnMarcha(RuntimeError):
    pass


def _ruta(cfg: Config, tid: str):
    return cfg.trabajos / f"{tid}.json"


def _escribir(cfg: Config, d: dict) -> None:
    cfg.trabajos.mkdir(parents=True, exist_ok=True)
    tmp = _ruta(cfg, d["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_ruta(cfg, d["id"]))


def estado(cfg: Config, tid: str) -> dict:
    ruta = _ruta(cfg, tid)
    if not ruta.exists():
        raise FileNotFoundError(tid)
    d = json.loads(ruta.read_text(encoding="utf-8"))
    if d["estado"] == "en_curso" and tid not in _vivos:
        d["estado"], d["error"] = "interrumpido", "El trabajo se cortó (se reinició el servidor). Vuelve a lanzarlo."
    return d


def lanzar(cfg: Config, pid: str, etapa: str, fn: Callable[[Callable[[str], None]], object]) -> str:
    """Lanza `fn(anunciar)` en segundo plano. Un solo trabajo a la vez por proyecto y etapa."""
    tid = f"{pid}-{etapa}-{int(time.time() * 1000)}"
    with _cerrojo:
        if any(t.startswith(f"{pid}-{etapa}-") for t in _vivos):
            raise YaEnMarcha(f"Ya hay un trabajo de {etapa} en marcha para este proyecto.")
        _vivos.add(tid)
    d = {"id": tid, "proyecto": pid, "etapa": etapa, "estado": "en_curso", "paso": "Empezando", "inicio": ahora(),
         "fin": None, "error": None, "resultado": None}
    _escribir(cfg, d)
    with almacen.editar(cfg, pid) as p:
        previo = p.etapas[etapa].estado if p.etapas[etapa].estado not in ("en_curso", "fallida") else "pendiente"
        p.etapas[etapa].estado = "en_curso"
        p.etapas[etapa].trabajo = tid
        p.etapas[etapa].error = None

    def anunciar(paso: str) -> None:
        d["paso"] = paso
        _escribir(cfg, d)

    def correr():
        try:
            r = fn(anunciar)
            d.update(estado="hecho", fin=ahora(), resultado=r if isinstance(r, (str, int, float, dict, list)) or r is None else None)
            with almacen.editar(cfg, pid) as p:          # un chat que solo contesta deja la etapa como estaba
                if p.etapas[etapa].estado == "en_curso":
                    p.etapas[etapa].estado = previo
        except Exception as exc:          # se enseña en una frase; la traza va al registro
            log.error("Trabajo %s falló: %s\n%s", tid, exc, traceback.format_exc())
            d.update(estado="fallido", fin=ahora(), error=str(exc)[:600])
            try:
                with almacen.editar(cfg, pid) as p:
                    # Si la etapa ya tenía algo (conceptos de otra ronda, un guion), se conserva con el error a la vista
                    p.etapas[etapa].estado = previo if previo != "pendiente" else "fallida"
                    p.etapas[etapa].error = str(exc)[:600]
            except Exception:
                pass
        finally:
            _escribir(cfg, d)
            with _cerrojo:
                _vivos.discard(tid)

    _pool.submit(correr)
    return tid
