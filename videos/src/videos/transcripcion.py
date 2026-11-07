"""Notas de voz: se transcriben con ElevenLabs (`POST /v1/speech-to-text`, Scribe, tiempos por palabra) y se trocean
en tramos de unos dos minutos. La marca de lugar de cada tramo es el minuto («1:30»), que es como se citan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from videos.config import Config
from videos.libro import Capitulo, Libro

EXTENSIONES = (".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".webm", ".aac", ".flac", ".mp4")
MODELO = "scribe_v2"
TRAMO_S = 120


class ErrorTranscripcion(RuntimeError):
    pass


def _minuto(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def transcribir(cfg: Config, ruta: Path) -> dict:
    if not cfg.elevenlabs_api_key:
        raise ErrorTranscripcion("Para transcribir una nota de voz hace falta ELEVENLABS_API_KEY.")
    h = hashlib.sha256(ruta.read_bytes()).hexdigest()
    cache = cfg.cache / "transcripciones" / f"{h}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    with httpx.Client(timeout=600) as c, ruta.open("rb") as f:
        r = c.post("https://api.elevenlabs.io/v1/speech-to-text", headers={"xi-api-key": cfg.elevenlabs_api_key},
                   data={"model_id": MODELO, "language_code": "es", "timestamps_granularity": "word",
                         "tag_audio_events": "false"},
                   files={"file": (ruta.name, f)})
    if r.status_code in (401, 403, 429):
        raise ErrorTranscripcion(f"ElevenLabs respondió {r.status_code}; se para sin reintentar.")
    if r.status_code >= 400:
        raise ErrorTranscripcion(f"ElevenLabs respondió {r.status_code}: {r.text[:300].replace(cfg.elevenlabs_api_key, '***')}")
    d = r.json()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def a_libro(d: dict, titulo: str, autor: str) -> Libro:
    """La transcripción como fuente: tramos de unos dos minutos, cortados en un final de frase si se puede."""
    palabras = [w for w in d.get("words", []) if w.get("type") in ("word", "spacing")]
    if not palabras:
        texto = (d.get("text") or "").strip()
        if not texto:
            raise ErrorTranscripcion("La transcripción ha salido vacía.")
        return Libro(titulo, autor, "audio", [Capitulo(1, "Nota de voz", texto, [[0, "0:00"]])], tipo="nota_de_voz")
    secciones, texto, marcas, inicio_tramo = [], "", [], palabras[0].get("start", 0.0)
    ultima_marca = -60.0
    for w in palabras:
        t = w.get("start", 0.0)
        if w["type"] == "word" and t - ultima_marca >= 30:          # una marca cada medio minuto
            marcas.append([len(texto), _minuto(t)])
            ultima_marca = t
        texto += w.get("text", "")
        if t - inicio_tramo >= TRAMO_S and texto.rstrip().endswith((".", "?", "!")):
            secciones.append(Capitulo(0, f"Minutos {marcas[0][1]}–{_minuto(t)}", texto.strip(), marcas))
            texto, marcas, inicio_tramo = "", [], t
    if texto.strip():
        fin = palabras[-1].get("end", inicio_tramo)
        secciones.append(Capitulo(0, f"Minutos {marcas[0][1] if marcas else _minuto(inicio_tramo)}–{_minuto(fin)}",
                                  texto.strip(), marcas))
    for i, c in enumerate(secciones, 1):
        c.n = i
    return Libro(titulo, autor, "audio", secciones, tipo="nota_de_voz")
