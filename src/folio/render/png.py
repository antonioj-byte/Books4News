"""PNG de 1080×1350 de cada diapositiva, con Playwright."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from folio.config import Config
from folio.modelos import Pieza
from folio.render.plantillas import Plantillas


def _lanzar(p):
    """Chromium de Playwright; si la versión instalada no coincide, el del entorno."""
    ruta = os.getenv("FOLIO_CHROMIUM")
    if ruta:
        return p.chromium.launch(executable_path=ruta)
    try:
        return p.chromium.launch()
    except Exception:
        for candidato in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")):
            return p.chromium.launch(executable_path=str(candidato))
        raise


def renderizar(cfg: Config, piezas: list[Pieza], destino: Path,
               direccion: str | None = None) -> tuple[list[Path], list[str]]:
    """PNG de cada diapositiva en destino/<pieza>/NN-tipo.png. Devuelve (archivos, avisos)."""
    from playwright.sync_api import sync_playwright

    plantillas = Plantillas(cfg, direccion, buscar_cubiertas=True)
    ancho = int(str(plantillas.tokens["lienzo"]["ancho"]).removesuffix("px"))
    alto = int(str(plantillas.tokens["lienzo"]["alto"]).removesuffix("px"))
    archivos, avisos = [], []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        navegador = _lanzar(p)
        pagina = navegador.new_page(viewport={"width": ancho, "height": alto}, device_scale_factor=1)
        for pieza in (p for p in piezas if p.guion):
            carpeta = destino / pieza.id
            carpeta.mkdir(parents=True, exist_ok=True)
            for viejo in carpeta.glob("[0-9][0-9]-*.png"):        # si el guion tenía más diapositivas
                viejo.unlink()
            for n, d in enumerate(pieza.guion.diapositivas, 1):
                html_path = Path(tmp) / f"{pieza.id}-{n}.html"
                html_path.write_text(plantillas.html_diapositiva(pieza, n), encoding="utf-8")
                pagina.goto(html_path.as_uri())
                pagina.wait_for_selector("body[data-listo='1']", timeout=15000)
                if pagina.evaluate("document.body.dataset.desborda === '1'"):
                    avisos.append(f"{pieza.id}, diapositiva {n}: el texto no cabe ni al tamaño mínimo")
                ruta = carpeta / f"{n:02d}-{d.tipo}.png"
                pagina.screenshot(path=str(ruta), clip={"x": 0, "y": 0, "width": ancho, "height": alto})
                archivos.append(ruta)
        navegador.close()
    return archivos, avisos
