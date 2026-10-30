"""Portada en vídeo: MP4 de 1080×1350 de la diapositiva 1, con las mismas plantillas que el PNG.

La foto se aleja despacio y el texto queda fijo desde el primer fotograma (elegido el 31/10: así la
miniatura del feed se lee). La animación está en base.css detrás de la clase «en-video» y sus valores
en diseno/tokens.yaml (grupo video). El vídeo se hace fotograma a fotograma: se pausa la animación, se
lleva a cada instante y se captura; ffmpeg lo une en H.264. Así no depende de la velocidad de la máquina.

Solo las portadas con imagen tienen vídeo: la tipográfica no se mueve.
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
    """destino/<pieza>/01-portada.mp4 de cada pieza con imagen en la portada. Devuelve (archivos, avisos)."""
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
            html = Path(tmp) / f"{pieza.id}.html"
            html.write_text(plantillas.html_diapositiva(pieza, 1), encoding="utf-8")
            pagina.goto(html.as_uri())
            pagina.wait_for_selector("body[data-listo='1']", timeout=15000)
            if not pagina.query_selector(".imagen img"):
                avisos.append(f"{pieza.id}: portada sin imagen, sin vídeo")
                continue
            pagina.evaluate("document.body.classList.add('en-video');"
                            "document.getAnimations().forEach(a => a.pause())")
            fotogramas = Path(tmp) / pieza.id
            fotogramas.mkdir()
            for i in range(round(fps * segundos)):
                pagina.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {i * 1000 / fps})")
                pagina.screenshot(path=str(fotogramas / f"{i:04d}.png"), clip={"x": 0, "y": 0, "width": ancho, "height": alto})
            salida = destino / pieza.id / "01-portada.mp4"
            salida.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(comando_ffmpeg(fotogramas, fps, salida), capture_output=True, text=True)
            if r.returncode != 0:
                avisos.append(f"{pieza.id}: ffmpeg falló ({r.stderr.strip()[:200]})")
                continue
            archivos.append(salida)
        navegador.close()
    return archivos, avisos
