"""La cama musical: instrumental, de la duración del vídeo, con la API de música de ElevenLabs (`POST /v1/music`,
`force_instrumental`). El ánimo sale de la biblia de estilo. Simulada (sin clave): un acorde suave con FFmpeg.
El montaje la baja bajo la voz (ducking)."""
from __future__ import annotations

import hashlib
import json

import httpx

from videos import almacen
from videos.config import Config
from videos.modelos import Gasto
from videos.montaje import TARJETA_S, _ffmpeg
from videos.voz import BASE, ErrorVoz, _cabeceras, _comprobar


def generar(cfg: Config, pid: str, anunciar=lambda _: None) -> str:
    p = almacen.cargar(cfg, pid)
    if p.voz is None or p.estilo is None:
        raise ValueError("Hacen falta la locución y el estilo")
    segundos = p.voz.duracion + TARJETA_S + 1.0
    carpeta = almacen.carpeta(cfg, pid)
    (carpeta / "musica").mkdir(exist_ok=True)
    nombre = f"musica/cama-{int(segundos)}s.mp3"
    if cfg.elevenlabs_simulado:
        anunciar("Cama musical simulada")
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=220:duration={segundos:.2f}", "-f", "lavfi",
                "-i", f"sine=frequency=330:duration={segundos:.2f}", "-filter_complex",
                "[0][1]amix=inputs=2,tremolo=f=0.5:d=0.4,volume=0.5", "-b:a", "128k", str(carpeta / nombre))
    else:
        anunciar("ElevenLabs compone la cama musical")
        cuerpo = {"prompt": p.estilo.musica, "music_length_ms": max(3000, int(segundos * 1000)),
                  "model_id": "music_v1", "force_instrumental": True}
        h = hashlib.sha256(json.dumps(cuerpo, sort_keys=True).encode()).hexdigest()
        cache = cfg.cache / "musica" / f"{h}.mp3"
        if not cache.exists():
            with httpx.Client(timeout=300) as c:
                r = c.post(f"{BASE}/v1/music", headers=_cabeceras(cfg.elevenlabs_api_key), json=cuerpo)
                _comprobar(r, cfg.elevenlabs_api_key)
            if not r.content:
                raise ErrorVoz("ElevenLabs no devolvió la música")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(r.content)
            with almacen.editar(cfg, pid) as q:
                q.gasto.append(Gasto(etapa="musica", servicio="elevenlabs", modelo="music_v1", usd=0.0,
                                     detalle=f"{int(segundos)} s de música (precio por medir)"))
        (carpeta / nombre).write_bytes(cache.read_bytes())
    with almacen.editar(cfg, pid) as q:
        q.musica = nombre
        q.musica_activa = True
    return nombre
