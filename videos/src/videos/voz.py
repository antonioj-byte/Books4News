"""Paso 5: la locución con ElevenLabs (`/v1/text-to-speech/{voz}/with-timestamps`). Los tiempos por carácter que
devuelve son la fuente de verdad del montaje: se agrupan en palabras y cada plano empieza en el primer carácter de su
locución y acaba donde empieza el siguiente. No se estiman duraciones ni se detectan pausas.

Rehacer la voz de un plano: se genera solo ese texto (con el anterior y el siguiente como contexto, para que la
entonación case), se empalma en su sitio y los tiempos de los planos siguientes se desplazan.

Simulada (sin clave): un tono suave y tiempos sintéticos de 15 caracteres por segundo con pausas en los signos, con el
mismo formato que devuelve ElevenLabs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import subprocess
import wave
from pathlib import Path

import httpx

from videos import almacen
from videos.config import Config
from videos.modelos import Gasto, Palabra, TiempoPlano, Voz, ahora

BASE = "https://api.elevenlabs.io"
TASA = 44100
COLA_S = 0.6                     # silencio al final de la voz
PAUSA_ENTRE_PLANOS = " "
USD_POR_1000 = 0.08              # Multilingual v2, v3 y v4 (página de precios de la API, 7/11)
_RE_SIGNOS = {".": 0.35, "?": 0.35, "!": 0.35, ",": 0.15, ";": 0.2, ":": 0.2, "…": 0.35}


class ErrorVoz(RuntimeError):
    pass


def huella(locuciones: list[str]) -> str:
    return hashlib.sha256(json.dumps(locuciones, ensure_ascii=False).encode()).hexdigest()[:16]


# ── ElevenLabs ────────────────────────────────────────────────────────────────────────────────────────────────────

def _cabeceras(clave: str) -> dict:
    return {"xi-api-key": clave, "Content-Type": "application/json"}


def _comprobar(r: httpx.Response, clave: str) -> None:
    if r.status_code in (401, 403, 429):
        raise ErrorVoz(f"ElevenLabs respondió {r.status_code}; se para sin reintentar ({r.text[:200].replace(clave, '***')})")
    if r.status_code >= 400:
        raise ErrorVoz(f"ElevenLabs respondió {r.status_code}: {r.text[:300].replace(clave, '***')}")


def voz_al_azar(cfg: Config, pid: str) -> tuple[str, str]:
    """Una voz de la cuenta (las prediseñadas primero), al azar pero estable por proyecto."""
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{BASE}/v1/voices", headers=_cabeceras(cfg.elevenlabs_api_key))
        _comprobar(r, cfg.elevenlabs_api_key)
    voces = r.json().get("voices", [])
    if not voces:
        raise ErrorVoz("La cuenta de ElevenLabs no tiene voces")
    hispanas = [v for v in voces if "spanish" in json.dumps(v.get("labels", {})).lower() or "español" in json.dumps(v.get("labels", {})).lower()]
    prediseñadas = [v for v in voces if v.get("category") == "premade"]
    grupo = hispanas or prediseñadas or voces
    v = random.Random(pid).choice(sorted(grupo, key=lambda x: x["voice_id"]))
    return v["voice_id"], v.get("name", v["voice_id"])


def sintetizar(cfg: Config, voz_id: str, texto: str, previo: str = "", siguiente: str = "") -> tuple[bytes, dict]:
    """Audio MP3 y alineación por carácter. Caché por huella de la petición."""
    cuerpo = {"text": texto, "model_id": cfg.voz_modelo,
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True},
              "seed": 7}
    if previo:
        cuerpo["previous_text"] = previo
    if siguiente:
        cuerpo["next_text"] = siguiente
    h = hashlib.sha256(json.dumps([voz_id, cuerpo], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    cache = cfg.cache / "elevenlabs" / f"{h}.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        return base64.b64decode(d["audio_base64"]), d["alignment"]
    with httpx.Client(timeout=120) as c:
        r = c.post(f"{BASE}/v1/text-to-speech/{voz_id}/with-timestamps", params={"output_format": "mp3_44100_128"},
                   headers=_cabeceras(cfg.elevenlabs_api_key), json=cuerpo)
        _comprobar(r, cfg.elevenlabs_api_key)
    d = r.json()
    alin = d.get("alignment") or d.get("normalized_alignment")
    if not alin or not d.get("audio_base64"):
        raise ErrorVoz("ElevenLabs no devolvió el audio o los tiempos")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"audio_base64": d["audio_base64"], "alignment": alin}), encoding="utf-8")
    return base64.b64decode(d["audio_base64"]), alin


def alineacion_simulada(texto: str) -> dict:
    t, ini, fin = 0.0, [], []
    for ch in texto:
        dur = 1 / 15 + _RE_SIGNOS.get(ch, 0.0)
        ini.append(round(t, 3))
        t += dur
        fin.append(round(t, 3))
    return {"characters": list(texto), "character_start_times_seconds": ini, "character_end_times_seconds": fin}


# ── Audio ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def _ffmpeg(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorVoz(f"ffmpeg: {r.stderr[-400:]}")


def a_wav(mp3: bytes, destino: Path) -> None:
    tmp = destino.with_suffix(".tmp.mp3")
    tmp.write_bytes(mp3)
    _ffmpeg("-i", str(tmp), "-ac", "1", "-ar", str(TASA), "-sample_fmt", "s16", str(destino))
    tmp.unlink()


def tono_simulado(segundos: float, destino: Path) -> None:
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=196:duration={segundos:.3f}:sample_rate={TASA}",
            "-af", "volume=0.06,afade=t=in:d=0.05", "-ac", "1", "-sample_fmt", "s16", str(destino))


def _leer(ruta: Path) -> bytes:
    with wave.open(str(ruta)) as w:
        return w.readframes(w.getnframes())


def _escribir(ruta: Path, frames: bytes) -> None:
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TASA)
        w.writeframes(frames)


def _muestra(t: float) -> int:
    return int(round(t * TASA)) * 2


def _silencio(s: float) -> bytes:
    return b"\x00\x00" * int(round(s * TASA))


# ── Tiempos ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _caracteres(alin: dict, texto: str) -> list[tuple[float, float]]:
    """Los tiempos de cada carácter de `texto`. ElevenLabs devuelve un carácter por posición del texto original; si
    algo no casa (normalización), se alinea avanzando por coincidencias."""
    chars, ini, fin = alin["characters"], alin["character_start_times_seconds"], alin["character_end_times_seconds"]
    if "".join(chars) == texto:
        return list(zip(ini, fin))
    salida, j = [], 0
    for ch in texto:
        k = j
        while k < len(chars) and chars[k] != ch and k - j < 8:
            k += 1
        if k < len(chars) and chars[k] == ch:
            j = k
        idx = min(j, len(chars) - 1)
        salida.append((ini[idx], fin[idx]))
        if k < len(chars) and chars[k] == ch:
            j += 1
    return salida


def tiempos(textos: list[tuple[str, str]], alin: dict, duracion: float) -> tuple[list[Palabra], dict[str, TiempoPlano], str]:
    """De la alineación por carácter del guion entero (planos unidos por un espacio) a palabras y planos."""
    texto = PAUSA_ENTRE_PLANOS.join(t for _, t in textos)
    tc = _caracteres(alin, texto)
    palabras, inicios, pos = [], [], 0
    for pid, t in textos:
        inicios.append((pid, tc[pos][0] if pos < len(tc) else duracion))
        i = 0
        while i < len(t):
            if t[i].isspace():
                i += 1
                continue
            j = i
            while j < len(t) and not t[j].isspace():
                j += 1
            a, b = tc[pos + i][0], tc[pos + j - 1][1]
            palabras.append(Palabra(t=t[i:j], i=round(a, 3), f=round(b, 3), plano=pid))
            i = j
        pos += len(t) + len(PAUSA_ENTRE_PLANOS)
    planos = {}
    for k, (pid, ini) in enumerate(inicios):
        fin = inicios[k + 1][1] if k + 1 < len(inicios) else duracion
        planos[pid] = TiempoPlano(inicio=0.0 if k == 0 else round(ini, 3), fin=round(fin, 3))
    return palabras, planos, texto


# ── Etapa ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def generar(cfg: Config, pid: str, anunciar=lambda _: None) -> Voz:
    p = almacen.cargar(cfg, pid)
    v = p.guion_actual
    if v is None or p.etapas["guion"].estado != "bloqueado":
        raise ValueError("Aprueba antes el guion")
    textos = [(x.id, x.locucion.strip()) for x in v.planos]
    texto = PAUSA_ENTRE_PLANOS.join(t for _, t in textos)
    dir_voz = almacen.carpeta(cfg, pid) / "voz"
    dir_voz.mkdir(parents=True, exist_ok=True)
    version = (p.voz.version + 1) if p.voz else 1
    wav = dir_voz / f"voz-{version}.wav"
    simulada = cfg.elevenlabs_simulado
    if simulada:
        anunciar("Voz simulada (sin clave de ElevenLabs)")
        alin = alineacion_simulada(texto)
        dur_voz = alin["character_end_times_seconds"][-1]
        tono_simulado(dur_voz, wav)
        voz_id, nombre = "simulada", "Voz simulada"
    else:
        voz_id, nombre = (p.voz.voz_id, p.voz.voz_nombre) if p.voz and not p.voz.simulada else (
            (cfg.voz_id, cfg.voz_id) if cfg.voz_id else voz_al_azar(cfg, pid))
        anunciar(f"ElevenLabs pone la voz ({nombre})")
        mp3, alin = sintetizar(cfg, voz_id, texto)
        a_wav(mp3, wav)
        with almacen.editar(cfg, pid) as q:
            q.gasto.append(Gasto(etapa="voz", servicio="elevenlabs", modelo=cfg.voz_modelo,
                                 usd=round(len(texto) / 1000 * USD_POR_1000, 4), detalle=f"{len(texto)} caracteres"))
    frames = _leer(wav) + _silencio(COLA_S)
    _escribir(wav, frames)
    duracion = round(len(frames) / 2 / TASA, 3)
    palabras, planos, _ = tiempos(textos, alin, duracion)
    return _guardar(cfg, pid, Voz(modelo="simulada" if simulada else cfg.voz_modelo, voz_id=voz_id, voz_nombre=nombre,
                                  simulada=simulada, audio=f"voz/voz-{version}.wav", audio_mp3=f"voz/voz-{version}.mp3",
                                  duracion=duracion, palabras=palabras, planos=planos,
                                  huella=huella([t for _, t in textos]), version=version))


def _guardar(cfg: Config, pid: str, voz: Voz) -> Voz:
    carpeta = almacen.carpeta(cfg, pid)
    _ffmpeg("-i", str(carpeta / voz.audio), "-b:a", "128k", str(carpeta / voz.audio_mp3))
    with almacen.editar(cfg, pid) as q:
        q.voz = voz
        q.etapas["voz"].estado = "hecha"
        q.etapas["voz"].actualizado = ahora()
        if q.etapas["montaje"].estado == "hecha":
            q.etapas["montaje"].estado = "desfasada"
    return voz


def rehacer_plano(cfg: Config, pid: str, plano: str, locucion: str, anunciar=lambda _: None) -> Voz:
    """Nueva locución para un plano: se sintetiza solo ese texto, se empalma y se desplazan los siguientes. El guion
    guarda el texto nuevo como una versión «manual» (sigue bloqueado)."""
    from videos.modelos import VersionGuion
    p = almacen.cargar(cfg, pid)
    if p.voz is None:
        raise ValueError("Genera antes la locución")
    v = p.guion_actual
    ids = [x.id for x in v.planos]
    if plano not in ids:
        raise ValueError("Ese plano no existe")
    k = ids.index(plano)
    locucion = locucion.strip()
    previo = v.planos[k - 1].locucion if k > 0 else ""
    siguiente = v.planos[k + 1].locucion if k + 1 < len(ids) else ""
    carpeta = almacen.carpeta(cfg, pid)
    tmp = carpeta / "voz" / f"plano-{plano}.wav"
    if p.voz.simulada or cfg.elevenlabs_simulado:
        alin = alineacion_simulada(locucion)
        tono_simulado(alin["character_end_times_seconds"][-1], tmp)
    else:
        anunciar(f"ElevenLabs rehace la voz del plano {plano}")
        mp3, alin = sintetizar(cfg, p.voz.voz_id, locucion, previo, siguiente)
        a_wav(mp3, tmp)
        with almacen.editar(cfg, pid) as q:
            q.gasto.append(Gasto(etapa="voz", servicio="elevenlabs", modelo=cfg.voz_modelo,
                                 usd=round(len(locucion) / 1000 * USD_POR_1000, 4), detalle=f"{plano}: {len(locucion)} caracteres"))
    nuevo = _leer(tmp) + _silencio(0.25)
    tmp.unlink(missing_ok=True)
    t = p.voz.planos[plano]
    fin_voz = t.fin if k + 1 < len(ids) else p.voz.duracion - COLA_S
    original = _leer(carpeta / p.voz.audio)
    frames = original[:_muestra(t.inicio)] + nuevo + original[_muestra(fin_voz):]
    delta = len(nuevo) / 2 / TASA - (fin_voz - t.inicio)
    version = p.voz.version + 1
    wav = f"voz/voz-{version}.wav"
    _escribir(carpeta / wav, frames)
    # Palabras: las del plano, de la alineación nueva; las de después, desplazadas
    tc = _caracteres(alin, locucion)
    propias, i = [], 0
    while i < len(locucion):
        if locucion[i].isspace():
            i += 1
            continue
        j = i
        while j < len(locucion) and not locucion[j].isspace():
            j += 1
        propias.append(Palabra(t=locucion[i:j], i=round(t.inicio + tc[i][0], 3), f=round(t.inicio + tc[j - 1][1], 3), plano=plano))
        i = j
    palabras = []
    for w in p.voz.palabras:
        if ids.index(w.plano) < k:
            palabras.append(w)
        elif ids.index(w.plano) > k:
            palabras.append(Palabra(t=w.t, i=round(w.i + delta, 3), f=round(w.f + delta, 3), plano=w.plano))
    palabras = [w for w in palabras if ids.index(w.plano) < k] + propias + [w for w in palabras if ids.index(w.plano) > k]
    planos = {}
    for pid_, tp in p.voz.planos.items():
        n = ids.index(pid_)
        if n < k:
            planos[pid_] = tp
        elif n == k:
            planos[pid_] = TiempoPlano(inicio=tp.inicio, fin=round(tp.fin + delta, 3))
        else:
            planos[pid_] = TiempoPlano(inicio=round(tp.inicio + delta, 3), fin=round(tp.fin + delta, 3))
    duracion = round(len(frames) / 2 / TASA, 3)
    planos[ids[-1]].fin = duracion
    with almacen.editar(cfg, pid) as q:          # el texto nuevo queda en el guion, que sigue bloqueado
        actual = q.guion_actual
        nuevos = [x.model_copy(deep=True) for x in actual.planos]
        nuevos[k].locucion = locucion
        q.guion.append(VersionGuion(n=len(q.guion) + 1, concepto=actual.concepto, origen="manual", titulo=actual.titulo,
                                    planos=nuevos, avisos=[f"Locución del plano {plano} cambiada en la revisión"]))
    voz = p.voz.model_copy(update=dict(audio=wav, audio_mp3=f"voz/voz-{version}.mp3", duracion=duracion,
                                       palabras=palabras, planos=planos, version=version, creado=ahora(),
                                       huella=huella([x.locucion if x.id != plano else locucion for x in v.planos])))
    return _guardar(cfg, pid, voz)
