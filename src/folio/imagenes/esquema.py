"""Ilustración técnica de la infografía «esquema» (31/10): la imagen libre de la pieza pasada a un esquema
de línea fina con rellenos magenta (Magnific, Seedream 4.5 Edit), sobre el que el render pone tres rótulos
del guion. Es el IL3 del catálogo.

Nunca se parte de cero: siempre de la imagen fijada para la pieza, con su licencia comprobada. El resultado
es una obra derivada y su crédito lo dice («generada con IA (Magnific) a partir de …»). Se guarda como
<pieza>-esquema.jpg junto a las imágenes del día, con caché por imagen y prompt en
data/cache/esquemas/: relanzar no vuelve a pagar. Comparte con los retratos el cliente y el bloqueo ante
401, 403 o 429 (folio.imagenes.retrato_generado).
"""

from __future__ import annotations

import base64
import hashlib
import re
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from folio.config import Config
from folio.imagenes import libres, retrato_generado

SUFIJO = "-esquema"


def prompt(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "ilustracion_esquema.md").read_text(encoding="utf-8")
    m = re.search(r"^## prompt\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m or not m.group(1).strip():
        raise ValueError("prompts/ilustracion_esquema.md no tiene la sección «## prompt»")
    return m.group(1).strip()


def ruta(dir_fecha: Path, pieza_id: str) -> Path:
    return libres.dir_imagenes(dir_fecha) / f"{pieza_id}{SUFIJO}.jpg"


def del_dia(dir_fecha: Path, sin: str) -> int:
    """Esquemas ya hechos hoy, sin contar los de la pieza `sin`."""
    return sum(1 for p in libres.dir_imagenes(dir_fecha).glob(f"*{SUFIJO}.jpg") if not p.name.startswith(f"{sin}{SUFIJO}"))


def generar(cfg: Config, pieza_id: str, dir_fecha: Path, cliente: httpx.Client | None = None) -> str:
    """Hace el esquema de la imagen fijada de la pieza y devuelve su crédito. ErrorMagnific si no se puede."""
    img = libres.de_pieza(pieza_id, dir_fecha)
    origen = libres.dir_imagenes(dir_fecha) / img.local if img and img.local else None
    if not origen or not origen.exists():
        raise retrato_generado.ErrorMagnific(f"La pieza {pieza_id} no tiene imagen de la que partir")
    with Image.open(origen) as im:
        im = im.convert("RGB")
        im.thumbnail((1400, 1400))
        b = BytesIO()
        im.save(b, "JPEG", quality=90)
    foto, texto = b.getvalue(), prompt(cfg)
    ec = cfg.pipeline.arte.esquema
    cache = cfg.dir_cache("x").parent / "esquemas" / f"{hashlib.sha256(foto + texto.encode() + ec.aspecto.encode()).hexdigest()[:20]}.jpg"
    from folio.imagenes import magnific
    magnific.comprobar(cfg)            # antes de mirar la caché, como siempre: sin clave o bloqueado, no hay esquema
    magnific.imagen(cfg, ruta=retrato_generado.RUTA, cuerpo={"prompt": texto, "reference_images": [base64.b64encode(foto).decode()],
                                                             "aspect_ratio": ec.aspecto},
                    cache=cache, pieza_id=pieza_id, concepto="esquema", modelo="Seedream 4.5",
                    espera_max_s=ec.espera_max_s, cliente=cliente, procesar=magnific.rgb)
    destino = ruta(dir_fecha, pieza_id)
    destino.write_bytes(cache.read_bytes())
    return f"esquema generado con IA (Magnific) a partir de: {img.credito}"
