"""Ilustración editorial de la pieza (31/10, B1 del catálogo): una metáfora visual dibujada por Magnific
(Seedream 4.5, desde texto) con el estilo de la casa (prompts/ilustracion_editorial.md), en 16:9 para que
cruce la portada y la noticia como una panorámica (B6).

La escena la propone el director de arte, en inglés; aquí se comprueba que no trae nombres propios (ni
personas reales, ni marcas, ni artistas), comillas ni cifras, y se le añade el estilo. La imagen se guarda
como la imagen de la pieza (<pieza>.jpg, con sus metadatos), así que el render y la web la tratan como
cualquier otra; su crédito dice que es una ilustración generada con IA para Folio. Caché por prompt en
data/cache/ilustraciones/: relanzar no vuelve a pagar. Comparte con los retratos el cliente y el bloqueo
ante 401, 403 o 429 (folio.imagenes.retrato_generado).
"""

from __future__ import annotations

import hashlib
import re
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from folio.config import Config
from folio.imagenes import libres, retrato_generado as rg

RUTA = "/v1/ai/text-to-image/seedream-v4-5"
ASPECTO = "widescreen_16_9"
CLAVE = "magnific:ilustracion"


# Palabras con que puede empezar una frase de la escena; cualquier otra con mayúscula se toma por nombre propio
_INICIOS = {"a", "an", "the", "in", "on", "at", "inside", "above", "below", "under", "behind", "beside", "between",
            "around", "across", "through", "over", "from", "with", "without", "one", "two", "three", "several", "many",
            "each", "every", "some", "tiny", "giant", "huge", "small", "large", "an", "here", "there", "it", "its",
            "they", "this", "these", "seen", "viewed", "half", "all", "no", "only"}


def _nombres_propios(texto: str) -> list[str]:
    """Palabras con mayúscula que no son el inicio corriente de una frase: en una escena en inglés,
    nombres propios (de personas, lugares, marcas o artistas)."""
    propios = []
    for frase in re.split(r"[.!?;:]\s*", texto):
        palabras = re.findall(r"[A-Za-zÀ-ÿ']+", frase)
        propios += [w for i, w in enumerate(palabras) if w[0].isupper() and (i > 0 or w.lower() not in _INICIOS)]
    return propios


def estilo(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "ilustracion_editorial.md").read_text(encoding="utf-8")
    m = re.search(r"^## estilo\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m or not m.group(1).strip():
        raise ValueError("prompts/ilustracion_editorial.md no tiene la sección «## estilo»")
    return m.group(1).strip()


def validar_escena(escena: str | None) -> tuple[str | None, str | None]:
    """La escena si sirve; si no, (None, motivo). Sin nombres propios (palabras con mayúscula que no
    empiezan frase), comillas ni cifras, y de 12 a 70 palabras."""
    if not escena:
        return None, "sin escena"
    e = " ".join(escena.split())
    if not 12 <= len(e.split()) <= 70:
        return None, "la escena tiene que tener de 12 a 70 palabras"
    if re.search(r"[\"“”«»]|\d", e):
        return None, "la escena no puede llevar comillas ni cifras"
    propios = _nombres_propios(e)
    if propios:
        return None, f"la escena no puede llevar nombres propios ({', '.join(propios[:3])})"
    return e, None


def _pedir(texto: str, clave: str, espera_max_s: float, cliente: httpx.Client | None) -> bytes:
    with cliente or httpx.Client(timeout=60) as c:
        t0 = time.monotonic()
        tarea = rg._api(c, clave, "POST", RUTA, json={"prompt": texto, "aspect_ratio": ASPECTO})
        tid = tarea["task_id"]
        while tarea.get("status") not in ("COMPLETED", "FAILED"):
            if time.monotonic() - t0 > espera_max_s:
                raise rg.ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
            time.sleep(rg.ESPERA_S)
            tarea = rg._api(c, clave, "GET", f"{RUTA}/{tid}")
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            raise rg.ErrorMagnific(f"La tarea {tid} falló")
        r = c.get(tarea["generated"][0])
        r.raise_for_status()
        return r.content


def del_dia(dir_fecha: Path, sin: str) -> int:
    """Ilustraciones editoriales ya hechas hoy, sin contar las de la pieza `sin`."""
    n = 0
    for p in libres.dir_imagenes(dir_fecha).glob("*.json"):
        img = libres.de_pieza(p.stem, dir_fecha)
        n += bool(img and img.archivo == CLAVE and p.stem != sin)
    return n


def generar(cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, cliente: httpx.Client | None = None) -> libres.ImagenLibre:
    """Dibuja la escena y la fija como imagen de la pieza. ErrorMagnific si no se puede."""
    if rg.bloqueado():
        raise rg.ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise rg.ErrorMagnific("Falta MAGNIFIC_API_KEY")
    texto = f"{escena} {estilo(cfg)}"
    cache = dir_fecha.parent / "ilustraciones" / f"{hashlib.sha256(texto.encode()).hexdigest()[:20]}.jpg"
    if not cache.exists():
        try:
            datos = _pedir(texto, cfg.magnific_api_key, cfg.pipeline.arte.ilustracion_editorial.espera_max_s, cliente)
        except rg.ErrorMagnific as e:
            if e.bloqueo:
                rg._bloqueo = str(e)
            raise
        with Image.open(BytesIO(datos)) as im:
            cache.parent.mkdir(parents=True, exist_ok=True)
            im.convert("RGB").save(cache, "JPEG", quality=90)
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pieza_id}.jpg").write_bytes(cache.read_bytes())
    with Image.open(cache) as im:
        ancho, alto = im.size
    img = libres.ImagenLibre(archivo=CLAVE, pagina="", url="", ancho=ancho, alto=alto,
                             licencia="ilustración generada con IA (Magnific)", licencia_url=None, autor="Folio",
                             descripcion=escena, libre=True, motivo="", local=f"{pieza_id}.jpg", fuente="")
    libres.guardar_metadatos(img, pieza_id, dir_fecha)
    return img
