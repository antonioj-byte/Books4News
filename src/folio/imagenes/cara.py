"""Encuadre de las fotos de personas en su cara (2/11, regla aceptada en la Memoria: «las fotos de personas se
recortan mal y en la imagen solo queda la frente»; en la pieza de Pinker, el círculo junto a la cubierta enseñaba solo
la frente, y en la de Fitzek, la portada).

Antes, todo retrato se encuadraba a ojo (50 % en horizontal, 28–35 % en vertical) y una foto de cuerpo entero o con la
cara baja quedaba cortada. Ahora Haiku mira la foto (`prompts/detector_cara.md`, ~0,0005 $) y devuelve la caja de la
cara; el código pone el punto de interés (`ImagenLibre.enfoque`) en su centro, que es lo que usan la portada, el círculo
de la diapositiva del libro y la tarjeta del cierre (`object-position`), y guarda la caja en `ImagenLibre.cara`.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

from folio.config import Config
from folio.imagenes import libres


class CaraLLM(BaseModel):
    hay_cara: bool = Field(description="Si hay una cara visible")
    x0: int = Field(description="Borde izquierdo de la cara, 0–100")
    y0: int = Field(description="Borde de arriba (la frente), 0–100")
    x1: int = Field(description="Borde derecho, 0–100")
    y1: int = Field(description="Borde de abajo (la barbilla), 0–100")


def _prompt(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "detector_cara.md").read_text(encoding="utf-8")
    return texto.split("\n---\n", 1)[1].strip()


def detectar(llm, cfg: Config, ruta: Path, paso: str = "cara") -> tuple[int, int, int, int] | None:
    """La caja de la cara principal en % (x0, y0, x1, y1), o None si no hay cara o el modelo falla."""
    from folio.llm import ErrorLLM
    with Image.open(ruta) as im:
        im = im.convert("RGB")
        im.thumbnail((1024, 1024))
        buf = BytesIO()
        im.save(buf, "JPEG", quality=85)
    try:
        r, _ = llm.estructurado(paso, [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": _prompt(cfg)}]}], CaraLLM, etapa_modelo="arte", max_tokens=400)
    except (ErrorLLM, ValueError):
        return None
    caja = tuple(max(0, min(100, v)) for v in (r.x0, r.y0, r.x1, r.y1))
    if not r.hay_cara or caja[2] <= caja[0] or caja[3] <= caja[1]:
        return None
    return caja


def enfoque_de(caja: tuple[int, int, int, int]) -> tuple[int, int]:
    """El centro de la cara: así entran ojos, nariz y boca en cualquier recorte que la quepa."""
    x0, y0, x1, y1 = caja
    return round((x0 + x1) / 2), round((y0 + y1) / 2)


def encuadrar(llm, cfg: Config, clave: str, dir_fecha: Path) -> str | None:
    """Encuadra en la cara la imagen `<clave>` de la caché del día (un retrato). Devuelve un aviso o None. Nunca falla:
    sin cara detectada, se queda el encuadre que tenía."""
    if llm is None:
        return None
    img = libres.de_pieza(clave, dir_fecha)
    if not img or not img.local or not (libres.dir_imagenes(dir_fecha) / img.local).exists():
        return None
    caja = detectar(llm, cfg, libres.dir_imagenes(dir_fecha) / img.local, f"cara:{clave}")
    if not caja:
        return f"Retrato sin cara detectada ({clave}): se deja el encuadre de siempre"
    img.cara = caja
    img.enfoque = enfoque_de(caja)
    libres.guardar_metadatos(img, clave, dir_fecha)
    return None
