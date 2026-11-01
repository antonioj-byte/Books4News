"""El friso de «Tres libros» (2/11, opción B elegida por el usuario: «vamos con la banda superior, me encanta»): una
ilustración apaisada que cruza en banda la parte de arriba de las tres diapositivas de libro, detrás de las cubiertas,
con un motivo de cada libro de izquierda a derecha. Prueba en el Artifact «Tríptico de las fichas».

La escena la escribe el ilustrador (prompts/escena_friso.md); el estilo es el de la ilustración editorial con el
reparto en tres tercios (sin decir «paneles»: con esa palabra el modelo pintaba tres cuadros con márgenes blancos).
Magnific (Flux 2 Pro) dibuja 1440×600, el máximo de ancho que admite; se recorta el borde de papel que a veces pinta
(y, con él, las firmas falsas de la esquina) y el revisor de letras descarta lo que aún las tenga. Se guarda como
<pieza>-friso.jpg con sus metadatos, junto a las demás imágenes de la pieza.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from folio import gastos
from folio.config import Config
from folio.imagenes import editorial, libres
from folio.imagenes import retrato_generado as rg

SUFIJO = "-friso"
CLAVE = "magnific:friso"
ANCHO, ALTO = 1440, 600
MAX_PALABRAS = 95                           # tres motivos piden más que la ilustración editorial (70)
# Recorte del borde: el modelo a veces enmarca la pintura con papel y firma en la esquina de abajo
RECORTE = (0.018, 0.037, 0.018, 0.045)     # izquierda, arriba, derecha, abajo (fracciones)
_REPARTO_EDITORIAL = ("with points of interest on the left and on the right and nothing essential in the exact centre; "
                      "the lower left area calm and uncluttered.")
_REPARTO_FRISO = ("with the same sky, ground and horizon running uninterrupted across the whole width; its three points "
                  "of interest sit at one sixth, one half and five sixths of the width, and the lower part stays calm and dark.")


def estilo(cfg: Config) -> str:
    e = editorial.estilo(cfg)
    if _REPARTO_EDITORIAL not in e:
        raise ValueError("prompts/ilustracion_editorial.md ha cambiado: no encuentro el reparto que el friso sustituye")
    return e.replace(_REPARTO_EDITORIAL, _REPARTO_FRISO)


def recortar(datos: bytes) -> Image.Image:
    with Image.open(BytesIO(datos)) as im:
        im = im.convert("RGB")
        a, b = im.size
        i, s, d, f = RECORTE
        return im.crop((round(a * i), round(b * s), round(a * (1 - d)), round(b * (1 - f))))


def dibujar(cfg: Config, pieza_id: str, escena: str, cliente: httpx.Client | None = None) -> Path:
    """Dibuja el friso y lo guarda en la caché común (la misma escena no se vuelve a pagar). ErrorMagnific si no se puede."""
    if rg.bloqueado():
        raise rg.ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise rg.ErrorMagnific("Falta MAGNIFIC_API_KEY")
    ie = cfg.pipeline.arte.ilustracion_editorial
    texto = f"{escena} {estilo(cfg)}"
    huella = hashlib.sha256(f"friso\n{ANCHO}x{ALTO}\n{texto}".encode()).hexdigest()[:20]
    cache = cfg.dir_cache("x").parent / "ilustraciones" / f"friso-{huella}.jpg"
    if not cache.exists():
        try:
            datos = _pedir(texto, cfg.magnific_api_key, ie.espera_max_s, cliente)
            gastos.imagen_magnific(cfg, "friso", pieza_id, ie.creditos_imagen, "Flux 2 Pro")
        except rg.ErrorMagnific as e:
            if e.bloqueo:
                rg._bloqueo = str(e)
            raise
        cache.parent.mkdir(parents=True, exist_ok=True)
        recortar(datos).save(cache, "JPEG", quality=90)
    return cache


def _pedir(texto: str, clave: str, espera_max_s: float, cliente: httpx.Client | None) -> bytes:
    import time
    ruta = editorial.MODELOS["flux_2_pro"][0]
    with cliente or httpx.Client(timeout=60) as c:
        t0 = time.monotonic()
        tarea = rg._api(c, clave, "POST", ruta, json={"prompt": texto, "width": ANCHO, "height": ALTO})
        tid = tarea["task_id"]
        while tarea.get("status") not in ("COMPLETED", "FAILED"):
            if time.monotonic() - t0 > espera_max_s:
                raise rg.ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
            time.sleep(rg.ESPERA_S)
            tarea = rg._api(c, clave, "GET", f"{ruta}/{tid}")
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            raise rg.ErrorMagnific(f"La tarea {tid} falló")
        r = c.get(tarea["generated"][0])
        r.raise_for_status()
        return r.content


def fijar(dir_fecha: Path, pieza_id: str, escena: str, dibujo: Path) -> libres.ImagenLibre:
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    clave = pieza_id + SUFIJO
    (carpeta / f"{clave}.jpg").write_bytes(dibujo.read_bytes())
    with Image.open(dibujo) as im:
        ancho, alto = im.size
    img = libres.ImagenLibre(archivo=CLAVE, pagina="", url="", ancho=ancho, alto=alto,
                             licencia="ilustración generada con IA (Magnific)", licencia_url=None, autor="Folio",
                             descripcion=escena, libre=True, motivo="", local=f"{clave}.jpg", fuente="")
    libres.guardar_metadatos(img, clave, dir_fecha)
    return img


def de_pieza(pieza_id: str, dir_fecha: Path) -> libres.ImagenLibre | None:
    return libres.de_pieza(pieza_id + SUFIJO, dir_fecha)


def del_dia(dir_fecha: Path, sin: str) -> int:
    """Frisos ya hechos hoy, sin contar el de la pieza `sin`."""
    return sum(1 for p in libres.dir_imagenes(dir_fecha).glob(f"*{SUFIJO}.json") if p.stem != sin + SUFIJO)


def generar_limpio(llm, cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, intentos: int = 2,
                   cliente: httpx.Client | None = None) -> tuple[libres.ImagenLibre | None, list[str]]:
    """Dibuja, revisa las letras y fija el friso (hasta `intentos`). Devuelve (imagen o None, motivos de los descartes).
    Un segundo intento con la misma escena dibuja otra imagen porque el revisor borra de la caché la que descarta."""
    descartes = []
    for _ in range(intentos):
        dibujo = dibujar(cfg, pieza_id, escena, cliente)
        motivo = editorial.revisar(llm, cfg, pieza_id, dibujo)
        if motivo is None:
            return fijar(dir_fecha, pieza_id, escena, dibujo), descartes
        descartes.append(motivo)
    return None, descartes
