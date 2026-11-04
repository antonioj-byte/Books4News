"""Banda panorámica a sangre sobre tres diapositivas seguidas (2/11, opción B elegida por el usuario en el Artifact
«Banda ilustrada en las diapositivas de texto»: «vamos con la B»). La pide quien edita desde el chat: una ilustración
que cruza las tres, oscurecida abajo, con el texto en blanco encima.

Sin persona, Flux 2 Pro la dibuja desde el texto (1440×600). Con una persona real («Pavel. Foto con licencia a estilo
gouache»), Seedream 4.5 Edit la pasa al estilo de la casa (collage desde el 3/11) a partir de su foto libre, que va como referencia: nunca se dibuja una cara
desde cero, y el resultado es una obra derivada con el crédito de la foto. En los dos casos se recorta a 12:5 (tres
diapositivas de 4:5), pasa el revisor de letras y se guarda como <pieza>-banda.jpg. Estilo en
prompts/ilustracion_editorial.md, con el reparto y la persona de prompts/ilustracion_banda.md.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx
from PIL import Image

from folio.config import Config
from folio.imagenes import editorial, friso, libres
from folio.imagenes import retrato_generado as rg

SUFIJO = "-banda"
CLAVE = "magnific:banda"
PROPORCION = 12 / 5                    # tres diapositivas de 1080×1350
ASPECTO_EDIT = "widescreen_16_9"       # Seedream 4.5 Edit: el más ancho que se ha probado; se recorta a 12:5
# La foto de la persona solo es la referencia del pintor, no se publica: basta con que se le vea bien la cara
# (la de Durov en Commons tiene 438 px)
ANCHO_REFERENCIA = 400
_ANONIMAS = "No real or recognisable people; any human figures are anonymous."


def _secciones(cfg: Config) -> dict[str, str]:
    texto = (cfg.dir_prompts / "ilustracion_banda.md").read_text(encoding="utf-8")
    s = {m.group(1): m.group(2).strip() for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", texto, re.M | re.S)}
    for falta in ("reparto", "persona"):
        if not s.get(falta):
            raise ValueError(f"prompts/ilustracion_banda.md no tiene la sección «## {falta}»")
    return s


def estilo(cfg: Config, con_persona: bool) -> str:
    e = editorial.estilo(cfg)
    s = _secciones(cfg)
    if friso._REPARTO_EDITORIAL not in e or _ANONIMAS not in e:
        raise ValueError("prompts/ilustracion_editorial.md ha cambiado: no encuentro las frases que la banda sustituye")
    e = e.replace(friso._REPARTO_EDITORIAL, s["reparto"])
    return e.replace(_ANONIMAS, s["persona"]) if con_persona else e


def a_proporcion(im: Image.Image, alto_relativo: float = 0.4) -> Image.Image:
    """Recorta a 12:5. Si sobra alto, quita más de abajo que de arriba (`alto_relativo`: la parte de arriba que se
    quita, de lo que sobra); si sobra ancho, por igual a los dos lados."""
    a, b = im.size
    if a / b < PROPORCION:
        nuevo = round(a / PROPORCION)
        arriba = round((b - nuevo) * alto_relativo)
        return im.crop((0, arriba, a, arriba + nuevo))
    nuevo = round(b * PROPORCION)
    izq = (a - nuevo) // 2
    return im.crop((izq, 0, izq + nuevo, b))


def dibujar(cfg: Config, pieza_id: str, escena: str, foto: bytes | None = None,
            cliente: httpx.Client | None = None) -> Path:
    """Dibuja la banda (con la foto de referencia, si la hay) y la guarda en la caché común. ErrorMagnific si no se puede."""
    import base64

    from folio.imagenes import magnific
    ie = cfg.pipeline.arte.ilustracion_editorial
    texto = editorial.con_estilo(escena, estilo(cfg, foto is not None))
    huella = hashlib.sha256(b"banda\n" + texto.encode() + (foto or b"")).hexdigest()[:20]
    cache = cfg.dir_cache("x").parent / "ilustraciones" / f"banda-{huella}.jpg"
    if foto is None:
        return magnific.imagen(cfg, ruta=magnific.FLUX_2_PRO, cuerpo={"prompt": texto, "width": friso.ANCHO, "height": friso.ALTO},
                               cache=cache, pieza_id=pieza_id, concepto="banda", modelo="Flux 2 Pro",
                               creditos=ie.creditos_imagen, cliente=cliente,
                               procesar=lambda datos: a_proporcion(friso.recortar(datos)))
    # Con la foto libre de la persona como referencia (Seedream 4.5 Edit): obra derivada
    return magnific.imagen(cfg, ruta=rg.RUTA, cuerpo={"prompt": texto, "reference_images": [base64.b64encode(foto).decode()],
                                                      "aspect_ratio": ASPECTO_EDIT},
                           cache=cache, pieza_id=pieza_id, concepto="banda", modelo=rg.MODELO, creditos=ie.creditos_imagen,
                           cliente=cliente, procesar=lambda datos: a_proporcion(magnific.rgb(datos)))


def fijar(dir_fecha: Path, pieza_id: str, escena: str, dibujo: Path, credito: str) -> libres.ImagenLibre:
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    clave = pieza_id + SUFIJO
    (carpeta / f"{clave}.jpg").write_bytes(dibujo.read_bytes())
    with Image.open(dibujo) as im:
        ancho, alto = im.size
    img = libres.ImagenLibre(archivo=CLAVE, pagina="", url="", ancho=ancho, alto=alto, licencia=credito,
                             licencia_url=None, autor="Folio", descripcion=escena, libre=True, motivo="",
                             local=f"{clave}.jpg", fuente="")
    libres.guardar_metadatos(img, clave, dir_fecha)
    return img


def de_pieza(pieza_id: str, dir_fecha: Path) -> libres.ImagenLibre | None:
    return libres.de_pieza(pieza_id + SUFIJO, dir_fecha)


def generar_limpio(llm, cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, credito: str,
                   foto: bytes | None = None, intentos: int = 2,
                   cliente: httpx.Client | None = None) -> tuple[libres.ImagenLibre | None, list[str]]:
    """Dibuja, revisa las letras y fija la banda (hasta `intentos`). Devuelve (imagen o None, motivos de los descartes)."""
    descartes = []
    for _ in range(intentos):
        dibujo = dibujar(cfg, pieza_id, escena, foto, cliente)
        motivo = editorial.revisar(llm, cfg, pieza_id, dibujo)
        if motivo is None:
            return fijar(dir_fecha, pieza_id, escena, dibujo, credito), descartes
        descartes.append(motivo)
    return None, descartes


def diapositivas_validas(tipos: list[str], desde: int) -> str | None:
    """None si la banda puede ir de la diapositiva `desde` a la `desde + 2`; si no, el motivo. Ni en la portada (tiene su
    imagen) ni en el cierre (lleva las fichas), ni pasada la última."""
    if desde < 2 or desde + 2 > len(tipos):
        return f"la banda cubre tres diapositivas seguidas entre la 2 y la {len(tipos)}"
    malas = [f"la {i} es {tipos[i - 1]}" for i in range(desde, desde + 3) if tipos[i - 1] in ("portada", "cierre")]
    return f"no puede ir sobre la portada ni el cierre ({', '.join(malas)})" if malas else None
