"""Retrato del autor generado con IA a partir de su foto libre (Magnific, Seedream 4.5 Edit).

Cuatro estilos de la casa, con referencias a la cultura digital: low-poly, vóxel, dithering de 1 bit y
render de videojuego de los 2000 (elegidos el 31/10 tras la prueba de docs/estilo-retratos.md). Los prompts viven en
prompts/retrato_generado.md: una sección por estilo y una común (parecido, sin texto).

Nunca se genera una cara desde cero: se parte siempre de la foto que fijó folio.imagenes.retratos, con
su licencia comprobada, y el resultado hereda su autor y su licencia como obra derivada. El original
queda al lado (<pieza>-retrato-original.*). En el dithering, el código fuerza el 1 bit al final, porque
el modelo a veces deja color.

La API es asíncrona: POST con la foto en base64 → task_id → GET hasta COMPLETED o FAILED → descarga
de la URL firmada. Cada resultado se guarda en data/cache/retratos_generados/ por foto, estilo y prompt:
relanzar no vuelve a pagar. Ante 401, 403 o 429 no se reintenta y la generación se desactiva el resto
de la ejecución; un 503 se reintenta una vez. La clave va solo en la cabecera, nunca en los mensajes.
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from folio import gastos
from folio.config import Config
from folio.imagenes import libres

BASE = "https://api.magnific.com"
RUTA = "/v1/ai/text-to-image/seedream-v4-5-edit"
MODELO = "Seedream 4.5 Edit"
ESTILOS = {"low_poly": "low-poly", "voxel": "vóxel", "dithering": "dithering de 1 bit",
           "render_2000": "render de videojuego de los 2000"}
ESPERA_S = 4.0            # entre consultas de la tarea (los tests la ponen a 0)

# Motivo del bloqueo (401/403/429) en esta ejecución: no se vuelve a llamar hasta la siguiente
_bloqueo: str | None = None


class ErrorMagnific(Exception):
    def __init__(self, mensaje: str, bloqueo: bool = False):
        super().__init__(mensaje)
        self.bloqueo = bloqueo


def bloqueado() -> str | None:
    return _bloqueo


def reiniciar() -> None:
    global _bloqueo
    _bloqueo = None


# --- Prompts -------------------------------------------------------------------

def prompt(cfg: Config, estilo: str) -> str:
    """La sección del estilo más la común, de prompts/retrato_generado.md."""
    texto = (cfg.dir_prompts / "retrato_generado.md").read_text(encoding="utf-8")
    secciones = {m.group(1): m.group(2).strip()
                 for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", texto, re.M | re.S)}
    for falta in (estilo, "comun"):
        if not secciones.get(falta):
            raise ValueError(f"prompts/retrato_generado.md no tiene la sección «## {falta}»")
    return f"{secciones[estilo]} {secciones['comun']}"


# --- Cliente -----------------------------------------------------------------------

def _limpiar(texto: str, clave: str) -> str:
    return texto.replace(clave, "***") if clave else texto


def _api(c: httpx.Client, clave: str, metodo: str, ruta: str, **kw) -> dict:
    """Una llamada a la API. 503: un reintento. 401/403/429: ErrorMagnific de bloqueo, sin reintentar."""
    for intento in (1, 2):
        r = c.request(metodo, BASE + ruta, headers={"x-magnific-api-key": clave}, **kw)
        if r.status_code != 503 or intento == 2:
            break
        time.sleep(ESPERA_S)
    if r.status_code in (401, 403, 429):
        raise ErrorMagnific(f"Magnific respondió {r.status_code}: {_limpiar(r.text[:200], clave)}", bloqueo=True)
    if r.status_code >= 400:
        raise ErrorMagnific(f"Magnific respondió {r.status_code}: {_limpiar(r.text[:200], clave)}")
    return r.json()["data"]


def generar(foto: bytes, texto_prompt: str, clave: str, aspecto: str, espera_max_s: float,
            cliente: httpx.Client | None = None) -> tuple[bytes, str, float]:
    """Pide la imagen y espera a que esté. Devuelve (bytes, task_id, segundos)."""
    with cliente or httpx.Client(timeout=60) as c:
        t0 = time.monotonic()
        tarea = _api(c, clave, "POST", RUTA, json={
            "prompt": texto_prompt, "reference_images": [base64.b64encode(foto).decode()], "aspect_ratio": aspecto})
        tid = tarea["task_id"]
        while tarea.get("status") not in ("COMPLETED", "FAILED"):
            if time.monotonic() - t0 > espera_max_s:
                raise ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
            time.sleep(ESPERA_S)
            tarea = _api(c, clave, "GET", f"{RUTA}/{tid}")
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            raise ErrorMagnific(f"La tarea {tid} falló: {_limpiar(str(tarea.get('error'))[:200], clave)}")
        r = c.get(tarea["generated"][0])          # URL firmada del CDN: sin la clave
        r.raise_for_status()
        return r.content, tid, round(time.monotonic() - t0, 1)


def posproceso(estilo: str, datos: bytes) -> tuple[bytes, str]:
    """El dithering se fuerza a 1 bit (blanco y negro puro, tramado) y se guarda en PNG; el resto, tal cual."""
    with Image.open(BytesIO(datos)) as im:
        if estilo != "dithering":
            im.verify()
            return datos, ".jpg" if im.format == "JPEG" else ".png"
        # Los casi blancos y casi negros del JPEG, a puro: si no, el tramado los llena de puntos sueltos
        gris = im.convert("L").point(lambda v: 255 if v > 225 else 0 if v < 30 else v)
        salida = BytesIO()
        gris.convert("1").save(salida, format="PNG", optimize=True)
        return salida.getvalue(), ".png"


# --- Para la pieza ---------------------------------------------------------------------

def estilo_del_dia(cfg: Config, pieza_id: str, dir_fecha: Path, tono: str | None = None) -> tuple[str | None, int]:
    """El siguiente estilo, alternando con los retratos ya generados hoy (sin contar esta pieza), y cuántos
    hay. None si ya se llegó al máximo del día o si el tono no lleva retrato generado. Si el tono tiene
    estilos en `por_tono`, se rota solo entre esos. El punto de partida cambia cada día: con la mesa del
    día solo se escribe sola la primera pieza, y si la rotación empezara siempre por el primer estilo, el
    retrato de la mañana saldría siempre en el mismo."""
    rg = cfg.pipeline.arte.retrato_generado
    hechos = [p for p in libres.dir_imagenes(dir_fecha).glob("*-retrato.json")
              if not p.name.startswith(f"{pieza_id}-") and (img := libres.de_pieza(p.stem, dir_fecha)) and img.generado]
    if len(hechos) >= rg.max_por_dia:
        return None, len(hechos)
    estilos = [e for e in rg.por_tono[tono] if e in rg.estilos] if tono in rg.por_tono else rg.estilos
    if not estilos:
        return None, len(hechos)
    return estilos[(_dia(dir_fecha) + len(hechos)) % len(estilos)], len(hechos)


def _dia(dir_fecha: Path) -> int:
    """Número del día de la carpeta de caché (data/cache/<fecha>), para rotar el estilo inicial; 0 si no es
    una fecha."""
    try:
        return date.fromisoformat(dir_fecha.name).toordinal()
    except ValueError:
        return 0


def aplicar(cfg: Config, pieza_id: str, dir_fecha: Path, estilo: str,
            cliente: httpx.Client | None = None) -> libres.ImagenLibre:
    """Convierte el retrato fijado de la pieza al estilo y lo deja en su lugar (<pieza>-retrato.*), con el
    original en <pieza>-retrato-original.*. Si el retrato ya era generado, parte del original."""
    global _bloqueo
    if estilo not in ESTILOS:
        raise ValueError(f"Estilo desconocido: {estilo} (hay {', '.join(ESTILOS)})")
    carpeta = libres.dir_imagenes(dir_fecha)
    original = libres.de_pieza(f"{pieza_id}-retrato-original", dir_fecha) or libres.de_pieza(f"{pieza_id}-retrato", dir_fecha)
    if not original or not original.local or not (carpeta / original.local).exists():
        raise ValueError(f"La pieza {pieza_id} no tiene retrato fijado del que partir")
    if original.archivo.startswith("prensa:"):
        raise ValueError(f"El retrato de {pieza_id} es una foto de prensa: se cede para publicarla tal cual, "
                         "no para hacer obras derivadas")
    foto = (carpeta / original.local).read_bytes()
    texto_prompt = prompt(cfg, estilo)
    clave_cache = hashlib.sha256(foto + estilo.encode() + texto_prompt.encode()).hexdigest()[:20]
    cache = dir_fecha.parent / "retratos_generados"
    en_cache = next(iter(sorted(cache.glob(f"{clave_cache}.*"))), None) if cache.exists() else None
    tid, segundos = None, 0.0
    if en_cache:
        datos, ext = en_cache.read_bytes(), en_cache.suffix
    else:
        if _bloqueo:
            raise ErrorMagnific(f"Generación desactivada en esta ejecución ({_bloqueo})", bloqueo=True)
        if not cfg.magnific_api_key:
            raise ErrorMagnific("Falta MAGNIFIC_API_KEY")
        rg = cfg.pipeline.arte.retrato_generado
        try:
            bruto, tid, segundos = generar(foto, texto_prompt, cfg.magnific_api_key, rg.aspecto, rg.espera_max_s, cliente)
            gastos.imagen_magnific(cfg, "retrato", f"{pieza_id} · {estilo}")
        except ErrorMagnific as exc:
            if exc.bloqueo:
                _bloqueo = str(exc)
            raise
        datos, ext = posproceso(estilo, bruto)
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{clave_cache}{ext}").write_bytes(datos)

    # El original pasa a <pieza>-retrato-original.* (si no estaba ya) y el generado ocupa su sitio
    if not original.local.startswith(f"{pieza_id}-retrato-original"):
        nombre = f"{pieza_id}-retrato-original{Path(original.local).suffix}"
        (carpeta / original.local).rename(carpeta / nombre)
        original = replace(original, local=nombre)
        libres.guardar_metadatos(original, f"{pieza_id}-retrato-original", dir_fecha)
    for viejo in carpeta.glob(f"{pieza_id}-retrato.*"):
        if viejo.suffix != ".json":
            viejo.unlink()
    with Image.open(BytesIO(datos)) as im:
        ancho, alto = im.size
    destino = carpeta / f"{pieza_id}-retrato{ext}"
    destino.write_bytes(datos)
    generado = replace(
        original, local=destino.name, ancho=ancho, alto=alto, enfoque=(50, 35),
        licencia=f"{original.licencia} (obra derivada)",
        fuente=f"{original.fuente}; retrato {ESTILOS[estilo]} generado con IA (Magnific)",
        generado={"estilo": estilo, "modelo": MODELO, "task_id": tid, "segundos": segundos,
                  "desde_cache": en_cache is not None, "original": original.local})
    libres.guardar_metadatos(generado, f"{pieza_id}-retrato", dir_fecha)
    return generado
