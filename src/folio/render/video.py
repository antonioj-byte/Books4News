"""Diapositivas en vídeo: MP4 de 1080×1350, con las mismas plantillas que el PNG.

Salen en vídeo las diapositivas que la plantilla marca con data-video (folio.render.plantillas): la
portada con imagen (la foto se aleja; el texto, fijo desde el primer fotograma para que la miniatura del
feed se lea) o con interferencia (M10), la noticia con una cifra que cuenta (M2) o con la palabra gigante
que sube (M7), y la idea con su infografía, que se dibuja. Como mucho, tres por carrusel.

La animación está en base.css detrás de la clase «en-video» y sus valores en diseno/tokens.yaml (grupo
video). El vídeo se hace fotograma a fotograma: se pausan las animaciones, se llevan a cada instante, se
avisa a la página (window.folioFotograma, para la cifra que cuenta) y se captura; ffmpeg lo une en H.264.
Así no depende de la velocidad de la máquina. El último fotograma es igual que el PNG.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from folio.config import Config
from folio.modelos import Pieza
from folio.render.plantillas import Plantillas
from folio.render.png import _lanzar


def comando_ffmpeg(fotogramas: Path, fps: int, salida: Path) -> list[str]:
    # Con una pista de audio muda (AAC): las especificaciones de vídeo de Instagram cuentan con audio AAC,
    # y así no dependemos de cómo trate un vídeo sin pista de audio
    return ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(fotogramas / "%04d.png"),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow", "-c:a", "aac", "-b:a", "64k",
            "-movflags", "+faststart", str(salida)]


def renderizar_video(cfg: Config, piezas: list[Pieza], destino: Path, direccion: str | None = None,
                     fps: int | None = None, segundos: float | None = None) -> tuple[list[Path], list[str]]:
    """destino/<pieza>/NN-tipo.mp4 de cada diapositiva con animación (01-portada.mp4, 02-actualidad.mp4…).
    Devuelve (archivos, avisos)."""
    if not shutil.which("ffmpeg"):
        return [], ["Sin vídeo: ffmpeg no está instalado"]
    from playwright.sync_api import sync_playwright

    plantillas = Plantillas(cfg, direccion, buscar_cubiertas=True)
    tokens = plantillas.tokens
    fps = fps or int(tokens["video"]["fps"])
    segundos = segundos or float(tokens["video"]["segundos"])
    ancho = int(str(tokens["lienzo"]["ancho"]).removesuffix("px"))
    alto = int(str(tokens["lienzo"]["alto"]).removesuffix("px"))
    archivos, avisos = [], []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        navegador = _lanzar(p)
        pagina = navegador.new_page(viewport={"width": ancho, "height": alto}, device_scale_factor=1)
        for pieza in (p for p in piezas if p.guion):
            # Los vídeos de una versión anterior no pueden quedarse: la web y el .zip los servirían
            for viejo in (destino / pieza.id).glob("[0-9][0-9]-*.mp4"):
                viejo.unlink()
            for n, d in enumerate(pieza.guion.diapositivas, 1):
                html = Path(tmp) / f"{pieza.id}-{n}.html"
                html.write_text(plantillas.html_diapositiva(pieza, n), encoding="utf-8")
                pagina.goto(html.as_uri())
                pagina.wait_for_selector("body[data-listo='1']", timeout=15000)
                if not pagina.query_selector("main[data-video]"):
                    continue
                pagina.evaluate("document.body.classList.add('en-video');"
                                "document.getAnimations().forEach(a => a.pause())")
                fotogramas = Path(tmp) / f"{pieza.id}-{n}"
                fotogramas.mkdir()
                for i in range(round(fps * segundos)):
                    ms = i * 1000 / fps
                    pagina.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {ms});"
                                    f"window.folioFotograma && window.folioFotograma({ms})")
                    pagina.screenshot(path=str(fotogramas / f"{i:04d}.png"), clip={"x": 0, "y": 0, "width": ancho, "height": alto})
                salida = destino / pieza.id / f"{n:02d}-{d.tipo}.mp4"
                salida.parent.mkdir(parents=True, exist_ok=True)
                r = subprocess.run(comando_ffmpeg(fotogramas, fps, salida), capture_output=True, text=True)
                if r.returncode != 0:
                    avisos.append(f"{pieza.id}, diapositiva {n}: ffmpeg falló ({r.stderr.strip()[:200]})")
                    continue
                archivos.append(salida)
        navegador.close()
    return archivos, avisos
