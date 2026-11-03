"""La foto del autor recortada en collage (3/11, elegidas por el usuario las opciones A y C del Artifact «Foto del
autor en collage»: «usemos delante de la escena y sin fondo generado»).

La cara es la de la foto: el código separa a la persona del fondo (modelo de segmentación ISNet en local, con
onnxruntime, sin servicios de fuera), la pasa a trama de puntos en tinta sobre papel y le pone un borde de papel
rasgado. Ningún modelo generativo toca la cara. Dos variantes:

- «escena» (A): el busto entra en primer plano desde el borde de abajo, delante de una escena en collage que dibuja
  Flux 2 Pro con el estilo de la casa y la mitad de abajo vacía (~25 créditos).
- «papel» (C): sin fondo generado; campo del color de la pieza, un círculo rasgado del otro color detrás de la
  cabeza y suelo de tinta. Sin coste.

Solo con fotos libres (Commons) o subidas por la redacción con permiso para modificarlas; nunca con las de prensa
de las editoriales (la cesión es para publicarlas tal cual). El resultado ocupa el lugar del retrato
(<pieza>-retrato.jpg) y el original queda en <pieza>-retrato-original.*, como con el retrato generado.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy import ndimage

from folio import gastos
from folio.config import Config
from folio.imagenes import editorial, libres
from folio.imagenes import retrato_generado as rg

log = logging.getLogger(__name__)

ANCHO, ALTO = 1080, 1350
PAPEL = (246, 243, 238)
TINTA = (28, 22, 24)
PLUMA = (212, 5, 73)
MARCADOR = (255, 245, 0)
PREFIJO = "recorte:"            # archivo de la imagen compuesta: «recorte:escena» o «recorte:papel»

MODELO_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODELO_MD5 = "fc16ebd8b0c10d971d3513d564d01e29"
_sesion = None
_cerrojo = threading.Lock()

# La escena del fondo: el estilo de la casa con la mitad de abajo vacía para el busto
_REPARTO_FONDO = ("Vertical composition: the scene fills the upper half and the edges of the frame, and the lower half "
                  "is left as a large calm empty area of plain paper and flat color, with nothing in it.")


class SinPersona(ValueError):
    """La segmentación no encontró a nadie en la foto."""


# ---------------------------------------------------------------- recorte de la persona

def _ruta_modelo(cfg: Config) -> Path:
    return cfg.dir_datos / "modelos" / "isnet-general-use.onnx"


def _modelo(cfg: Config) -> Path:
    """El modelo de segmentación (179 MB), descargado una vez al volumen y comprobado por su md5."""
    ruta = _ruta_modelo(cfg)
    if ruta.exists():
        return ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".parcial")
    md5 = hashlib.md5()
    with httpx.stream("GET", MODELO_URL, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for trozo in r.iter_bytes(1 << 20):
                md5.update(trozo)
                f.write(trozo)
    if md5.hexdigest() != MODELO_MD5:
        tmp.unlink(missing_ok=True)
        raise ValueError("El modelo de recorte descargado no casa con su md5")
    tmp.replace(ruta)
    return ruta


def mascara(cfg: Config, im: Image.Image) -> Image.Image:
    """Máscara (L, 0–255) de la persona, del tamaño de la imagen. Mismo preproceso que rembg con ISNet."""
    global _sesion
    import onnxruntime as ort
    with _cerrojo:
        if _sesion is None:
            _sesion = ort.InferenceSession(str(_modelo(cfg)), providers=["CPUExecutionProvider"])
        a = np.asarray(im.convert("RGB").resize((1024, 1024), Image.LANCZOS), dtype=np.float32)
        a = a / max(float(a.max()), 1e-6) - 0.5
        entrada = {_sesion.get_inputs()[0].name: a.transpose(2, 0, 1)[None].astype(np.float32)}
        pred = _sesion.run(None, entrada)[0][0, 0]
    pred = (pred - pred.min()) / max(float(pred.max() - pred.min()), 1e-6)
    return Image.fromarray((pred * 255).astype("uint8"), "L").resize(im.size, Image.LANCZOS)


# ---------------------------------------------------------------- trama y papel rasgado

def trama(gris: Image.Image, paso: int = 7, angulo: int = 45, tinta=TINTA, fondo=PAPEL) -> Image.Image:
    """Trama de puntos: cada celda, un punto de radio según lo oscuro (a doble resolución y reducida)."""
    g = ImageOps.autocontrast(gris, cutoff=1)
    grande = g.rotate(angulo, expand=True, fillcolor=255)
    w, h = grande.size
    lienzo = Image.new("L", (w * 2, h * 2), 255)
    d = ImageDraw.Draw(lienzo)
    a = np.asarray(grande, dtype=float)
    for y in range(0, h, paso):
        for x in range(0, w, paso):
            r = (1 - a[y:y + paso, x:x + paso].mean() / 255) ** 0.9 * paso * 0.78
            if r > 0.3:
                cx, cy = (x + paso / 2) * 2, (y + paso / 2) * 2
                d.ellipse((cx - r * 2, cy - r * 2, cx + r * 2, cy + r * 2), fill=0)
    lienzo = lienzo.resize((w, h), Image.LANCZOS).rotate(-angulo, fillcolor=255)
    W, H = gris.size
    lienzo = lienzo.crop(((w - W) // 2, (h - H) // 2, (w - W) // 2 + W, (h - H) // 2 + H))
    return Image.composite(Image.new("RGB", (W, H), fondo), Image.new("RGB", (W, H), tinta), lienzo)


def rasgado(zona: np.ndarray, margen: int = 22, semilla: int = 3) -> np.ndarray:
    """La zona ampliada con un borde irregular, como papel rasgado a mano."""
    rng = np.random.default_rng(semilla)
    dist = ndimage.distance_transform_edt(~zona)
    grueso = ndimage.gaussian_filter(rng.standard_normal(zona.shape), 6)
    fino = ndimage.gaussian_filter(rng.standard_normal(zona.shape), 1.2)
    grueso /= np.abs(grueso).max() + 1e-9
    fino /= np.abs(fino).max() + 1e-9
    return dist < margen * (1 + 0.55 * grueso + 0.25 * fino)


def busto(foto: Image.Image, masc: Image.Image, alto: int, paso: int = 6, contraste: float = 1.05,
          margen: int = 22) -> Image.Image:
    """La persona recortada, en trama de tinta sobre papel, con su borde rasgado y una sombra suave (RGBA)."""
    im = foto.convert("RGB").copy()
    im.putalpha(masc.point(lambda v: 255 if v > 128 else 0))
    caja = im.getchannel("A").getbbox()
    if not caja or (caja[2] - caja[0]) * (caja[3] - caja[1]) < 0.04 * im.width * im.height:
        raise SinPersona("No se encuentra a la persona en la foto")
    im = im.crop(caja)
    im = im.resize((round(im.width * alto / im.height), alto), Image.LANCZOS)
    pad = margen * 3
    base = Image.new("RGBA", (im.width + 2 * pad, im.height + pad), (0, 0, 0, 0))
    base.paste(im, (pad, pad), im)
    alfa = np.asarray(base.getchannel("A")) > 128
    m_alfa = Image.fromarray((alfa * 255).astype("uint8"))
    gris = ImageOps.grayscale(base.convert("RGB"))
    gris = gris.point(lambda v: max(0, min(255, round((v - 128) * contraste + 128))))
    gris = Image.composite(ImageOps.autocontrast(gris, cutoff=2), Image.new("L", gris.size, 255), m_alfa)
    t = trama(gris, paso=paso)
    borde = rasgado(alfa, margen)
    borde[-2:, :] |= alfa[-2:, :]
    salida = Image.new("RGBA", base.size, (0, 0, 0, 0))
    salida.paste(Image.new("RGB", base.size, PAPEL), (0, 0), Image.fromarray((borde * 255).astype("uint8")))
    salida.paste(t, (0, 0), m_alfa.filter(ImageFilter.GaussianBlur(0.8)))
    sombra = Image.fromarray((borde * 110).astype("uint8")).filter(ImageFilter.GaussianBlur(14))
    capa = Image.new("RGBA", (base.width + 40, base.height + 40), (0, 0, 0, 0))
    capa.paste(Image.new("RGBA", base.size, (0, 0, 0, 255)), (14, 18), sombra)
    capa.alpha_composite(salida, (0, 0))
    return capa


# ---------------------------------------------------------------- las dos composiciones

def sobre_escena(fondo: Image.Image, b: Image.Image) -> Image.Image:
    """A: el busto en primer plano, desde el borde de abajo y algo a la derecha, delante de la escena."""
    f = fondo.convert("RGB")
    esc = max(ANCHO / f.width, ALTO / f.height)
    f = f.resize((round(f.width * esc), round(f.height * esc)), Image.LANCZOS)
    lienzo = f.crop(((f.width - ANCHO) // 2, 0, (f.width - ANCHO) // 2 + ANCHO, ALTO)).convert("RGBA")
    lienzo.alpha_composite(b, (min(ANCHO - b.width + 150, (ANCHO - b.width) // 2 + 160), ALTO - b.height + 40))
    return lienzo.convert("RGB")


def sobre_papel(b: Image.Image, acento: str | None) -> Image.Image:
    """C: campo del color de la pieza, círculo rasgado del otro color detrás de la cabeza y suelo de tinta."""
    campo, circulo = (MARCADOR, PLUMA) if acento == "marcador" else (PLUMA, MARCADOR)
    lienzo = Image.new("RGBA", (ANCHO, ALTO), campo + (255,))
    yy, xx = np.mgrid[0:ALTO, 0:ANCHO]
    zona = (xx - 560) ** 2 + (yy - 470) ** 2 < 360 ** 2
    lienzo.paste(Image.new("RGB", (ANCHO, ALTO), circulo), (0, 0), Image.fromarray((rasgado(zona, 12, 5) * 255).astype("uint8")))
    suelo = yy > 1010 + 0.12 * (xx - 540)
    lienzo.paste(Image.new("RGB", (ANCHO, ALTO), TINTA), (0, 0), Image.fromarray((rasgado(suelo, 16, 11) * 255).astype("uint8")))
    lienzo.alpha_composite(b, ((ANCHO - b.width) // 2, ALTO - b.height + 40))
    return lienzo.convert("RGB")


# ---------------------------------------------------------------- el fondo de la escena (Flux)

def estilo_fondo(cfg: Config) -> str:
    from folio.imagenes import friso
    e = editorial.estilo(cfg)
    if friso._REPARTO_EDITORIAL not in e:
        raise ValueError("El estilo de prompts/ilustracion_editorial.md ya no tiene la frase del reparto que sustituye el recorte")
    return e.replace("One single continuous scene that flows across the full width with no division, " + friso._REPARTO_EDITORIAL,
                     _REPARTO_FONDO).replace(friso._REPARTO_EDITORIAL, _REPARTO_FONDO)


def dibujar_fondo(cfg: Config, pieza_id: str, escena: str, cliente: httpx.Client | None = None) -> Path:
    """La escena vertical (1088×1360) del fondo, en la caché común. ErrorMagnific si no se puede."""
    import time
    if rg.bloqueado():
        raise rg.ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise rg.ErrorMagnific("Falta MAGNIFIC_API_KEY")
    ie = cfg.pipeline.arte.ilustracion_editorial
    texto = f"{escena} {estilo_fondo(cfg)}"
    cache = cfg.dir_cache("x").parent / "ilustraciones" / f"recorte-{hashlib.sha256(texto.encode()).hexdigest()[:20]}.jpg"
    if cache.exists():
        return cache
    ruta = "/v1/ai/text-to-image/flux-2-pro"
    try:
        with cliente or httpx.Client(timeout=60) as c:
            tarea = rg._api(c, cfg.magnific_api_key, "POST", ruta, json={"prompt": texto, "width": 1088, "height": 1360})
            gastos.imagen_magnific(cfg, "recorte", pieza_id, ie.creditos_imagen, "Flux 2 Pro")
            tid, t0 = tarea["task_id"], time.monotonic()
            while tarea.get("status") not in ("COMPLETED", "FAILED"):
                if time.monotonic() - t0 > ie.espera_max_s:
                    raise rg.ErrorMagnific(f"La tarea {tid} no terminó en {ie.espera_max_s:.0f} s")
                time.sleep(3)
                tarea = rg._api(c, cfg.magnific_api_key, "GET", f"{ruta}/{tid}")
            if tarea["status"] == "FAILED" or not tarea.get("generated"):
                raise rg.ErrorMagnific(f"La tarea {tid} falló")
            r = c.get(tarea["generated"][0])
            r.raise_for_status()
    except rg.ErrorMagnific as e:
        if e.bloqueo:
            rg._bloqueo = str(e)
        raise
    with Image.open(BytesIO(r.content)) as im:
        cache.parent.mkdir(parents=True, exist_ok=True)
        im.convert("RGB").save(cache, "JPEG", quality=90)
    return cache


# ---------------------------------------------------------------- aplicar a la pieza

def se_puede(img: libres.ImagenLibre | None) -> str | None:
    """None si la foto admite el recorte; si no, el motivo."""
    from folio import materiales
    if not img or not img.local:
        return "la pieza no tiene foto del autor"
    if img.archivo.startswith("prensa:"):
        return "es una foto de prensa: se cede para publicarla tal cual"
    if materiales.es_material(img) and not img.modificable:
        return "es una foto subida sin permiso para modificarla"
    if img.archivo.startswith(PREFIJO) or img.generado:
        return "la foto ya está tratada"
    return None


def de_dia(dir_fecha: Path, variante: str, sin: str = "") -> int:
    """Recortes de esa variante ya hechos hoy, sin contar la pieza `sin`."""
    n = 0
    for p in libres.dir_imagenes(dir_fecha).glob("*-retrato.json"):
        img = libres.de_pieza(p.stem, dir_fecha)
        n += bool(img and img.archivo == PREFIJO + variante and not p.stem.startswith(sin or "\0"))
    return n


def aplicar(cfg: Config, pieza_id: str, dir_fecha: Path, variante: str, acento: str | None = None,
            fondo: Path | None = None) -> libres.ImagenLibre:
    """Compone el recorte con la foto fijada de la pieza y lo deja en su lugar (<pieza>-retrato.jpg), con el
    original en <pieza>-retrato-original.*. «escena» necesita `fondo`."""
    carpeta = libres.dir_imagenes(dir_fecha)
    original = libres.de_pieza(f"{pieza_id}-retrato-original", dir_fecha) or libres.de_pieza(f"{pieza_id}-retrato", dir_fecha)
    motivo = se_puede(original)
    if motivo:
        raise ValueError(f"Sin recorte para {pieza_id}: {motivo}")
    if variante == "escena" and not fondo:
        raise ValueError("El recorte sobre escena necesita el fondo")
    with Image.open(carpeta / original.local) as foto:
        foto = ImageOps.exif_transpose(foto).convert("RGB")
        b = busto(foto, mascara(cfg, foto), 900 if variante == "escena" else 1050, paso=6 if variante == "escena" else 7)
    if variante == "escena":
        with Image.open(fondo) as f:
            final = sobre_escena(f, b)
    else:
        final = sobre_papel(b, acento)
    if not original.local.startswith(f"{pieza_id}-retrato-original"):
        nombre = f"{pieza_id}-retrato-original{Path(original.local).suffix}"
        (carpeta / original.local).rename(carpeta / nombre)
        original = replace(original, local=nombre)
        libres.guardar_metadatos(original, f"{pieza_id}-retrato-original", dir_fecha)
    for viejo in carpeta.glob(f"{pieza_id}-retrato.*"):
        viejo.unlink()
    final.save(carpeta / f"{pieza_id}-retrato.jpg", "JPEG", quality=90)
    extra = "recortada y en trama por Folio" + (", fondo generado con IA (Magnific)" if variante == "escena" else "")
    img = replace(original, archivo=PREFIJO + variante, local=f"{pieza_id}-retrato.jpg", ancho=ANCHO, alto=ALTO,
                  fuente=" · ".join(x for x in (original.fuente, extra) if x), enfoque=(50, 50), cara=None, generado=None)
    libres.guardar_metadatos(img, f"{pieza_id}-retrato", dir_fecha)
    return img


def restaurar_original(dir_fecha: Path, pieza_id: str) -> libres.ImagenLibre | None:
    """Devuelve la foto original al sitio del retrato (deshace el recorte o el retrato generado). None si no hay."""
    carpeta = libres.dir_imagenes(dir_fecha)
    original = libres.de_pieza(f"{pieza_id}-retrato-original", dir_fecha)
    if not original or not original.local or not (carpeta / original.local).exists():
        return None
    for viejo in carpeta.glob(f"{pieza_id}-retrato.*"):
        viejo.unlink()
    nombre = f"{pieza_id}-retrato{Path(original.local).suffix}"
    (carpeta / original.local).rename(carpeta / nombre)
    (carpeta / f"{pieza_id}-retrato-original.json").unlink(missing_ok=True)
    img = replace(original, local=nombre)
    libres.guardar_metadatos(img, f"{pieza_id}-retrato", dir_fecha)
    return img
