"""La pieza lista para publicar: JPEG de cada diapositiva, portada en vídeo si tiene imagen, y el pie.

Se pinta la versión actual de la pieza (la de la web, con las ediciones), no la del informe del día.
Instagram solo acepta JPEG, así que los PNG del render se convierten. Todo queda en
informes/<fecha>/publicar/<pieza>/: 01.mp4 (o 01.jpg), 02.jpg… y pie.txt.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from folio.config import Config
from folio.informe import creditos_pie
from folio.modelos import Pieza
from folio.render import renderizar, renderizar_video


@dataclass
class Preparada:
    carpeta: Path
    medios: list[tuple[str, str]]      # («imagen» o «video», archivo dentro de la carpeta), en orden
    pie: str
    avisos: list[str]


def pie_publicacion(pieza: Pieza) -> str:
    """El pie del guion y, debajo, los créditos de las imágenes."""
    creditos = creditos_pie(pieza.arte) if pieza.arte else []
    return pieza.guion.pie_instagram.strip() + (f"\n\n{'. '.join(creditos)}." if creditos else "")


def preparar(cfg: Config, pieza: Pieza, con_video: bool = True) -> Preparada:
    carpeta = cfg.dir_informes / pieza.fecha / "publicar" / pieza.id
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    avisos: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        pngs, av = renderizar(cfg, [pieza], Path(tmp))
        avisos += av
        for n, png in enumerate(sorted(pngs), 1):
            Image.open(png).convert("RGB").save(carpeta / f"{n:02d}.jpg", quality=92, optimize=True)
        if con_video:
            videos, av = renderizar_video(cfg, [pieza], Path(tmp))
            avisos += [a for a in av if "sin vídeo" not in a]
            if videos:
                shutil.copy(videos[0], carpeta / "01.mp4")
    medios = [("video", "01.mp4") if n == 1 and (carpeta / "01.mp4").exists() else ("imagen", f"{n:02d}.jpg")
              for n in range(1, len(pngs) + 1)]
    pie = pie_publicacion(pieza)
    (carpeta / "pie.txt").write_text(pie, encoding="utf-8")
    return Preparada(carpeta, medios, pie, avisos)
