"""Render de las piezas (Fase 2): HTML por diapositiva con las plantillas de diseno/ y PNG
de 1080×1350 con Playwright.

El aspecto vive en diseno/tokens.yaml (colores, fuentes, tamaños, márgenes, logotipo) y en
diseno/plantillas/ (una plantilla por tipo de diapositiva, solo con variables de los tokens).
html_diapositiva() es la misma para el PNG y para la vista previa de la web: solo cambia
`base_url`, la dirección desde la que se sirven las fuentes y las hojas de estilo.
"""

from __future__ import annotations

import html
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from folio.config import Config
from folio.modelos import LibroGuion, LibroVerificado, Pieza
from folio.verificacion_texto import autor_coincide, titulos_coinciden

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")
_CURSIVA = re.compile(r"\*([^*\n]+)\*")
# En la imagen firma el logotipo: la firma del texto del cierre («— Folio») no se repite.
_FIRMA_FINAL = re.compile(r"\s*(?:[—–-]\s*)?Folio\.?\s*$")


def dir_diseno(cfg: Config) -> Path:
    return cfg.raiz / "diseno"


def cargar_tokens(cfg: Config) -> dict:
    return yaml.safe_load((dir_diseno(cfg) / "tokens.yaml").read_text(encoding="utf-8"))


def css_tokens(tokens: dict) -> str:
    """Grupos de valores simples de los tokens → variables CSS (colores.papel → --colores-papel)."""
    lineas = []
    for grupo, valores in tokens.items():
        if not isinstance(valores, dict):
            continue
        for clave, valor in valores.items():
            if isinstance(valor, (str, int, float)):
                lineas.append(f"  --{grupo}-{clave.replace('_', '-')}: {valor};")
    return ":root {\n" + "\n".join(lineas) + "\n}"


def texto_html(texto: str) -> Markup:
    """Texto del guion → HTML seguro: se escapa todo y *así* pasa a cursiva."""
    return Markup(_CURSIVA.sub(r"<em>\1</em>", html.escape(texto, quote=False)))


def fecha_larga(fecha: str) -> str:
    a, m, d = fecha.split("-")
    return f"{int(d)} de {_MESES[int(m) - 1]} de {a}"


def _verificado(lg: LibroGuion, libros: list[LibroVerificado]) -> LibroVerificado | None:
    return next((v for v in libros if autor_coincide(lg.autor, v.autores) and any(
        titulos_coinciden(lg.titulo, t) for t in (v.titulo, v.titulo_propuesto,
                                                  v.edicion_es_detalle.titulo if v.edicion_es_detalle else None) if t
    )), None)


def ficha_libros(pieza: Pieza) -> list[dict]:
    """Libros del cierre con sus datos verificados: editorial y traductor españoles, o nada."""
    out = []
    for lg in pieza.guion.libros if pieza.guion else []:
        v = _verificado(lg, pieza.libros)
        datos = []
        if v and v.edicion_es == "si":
            d = v.edicion_es_detalle
            ed = ", ".join(x for x in (lg.editorial_espanola, d.anio if d else None) if x)
            if ed:
                datos.append(ed)
            if lg.traductor:
                datos.append(f"Traducción de {lg.traductor}")
        elif v and v.edicion_es == "no":
            datos.append("Sin edición en español")
        out.append({"titulo": texto_html(lg.titulo.replace("*", "")), "autor": lg.autor, "datos": " · ".join(datos)})
    return out


@dataclass
class Plantillas:
    cfg: Config

    def __post_init__(self):
        self.tokens = cargar_tokens(self.cfg)
        self.env = Environment(loader=FileSystemLoader(dir_diseno(self.cfg) / "plantillas"),
                               autoescape=select_autoescape(["html"]))

    def html_diapositiva(self, pieza: Pieza, n: int, base_url: str | None = None) -> str:
        """HTML completo de la diapositiva n (1, 2, …) de la pieza."""
        d = pieza.guion.diapositivas[n - 1]
        logo = self.tokens["logotipo"].strip()
        return self.env.get_template(f"{d.tipo}.html").render(
            base_url=base_url or dir_diseno(self.cfg).resolve().as_uri() + "/",
            tokens=self.tokens, css_tokens=Markup(css_tokens(self.tokens)),
            logotipo=Markup(logo), logotipo_grande=Markup(logo.replace('class="logotipo"', 'class="logotipo logotipo--grande"', 1)),
            tipo=d.tipo, rotulo=self.tokens["rotulos"].get(d.tipo, ""),
            texto=texto_html(_FIRMA_FINAL.sub("", d.texto) if d.tipo == "cierre" else d.texto),
            n=n, total=len(pieza.guion.diapositivas), pieza_id=pieza.id, fecha_larga=fecha_larga(pieza.fecha),
            libros=ficha_libros(pieza) if d.tipo == "cierre" else [],
        )


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


def renderizar(cfg: Config, piezas: list[Pieza], destino: Path) -> tuple[list[Path], list[str]]:
    """PNG de cada diapositiva en destino/<pieza>/NN-tipo.png. Devuelve (archivos, avisos)."""
    from playwright.sync_api import sync_playwright

    plantillas = Plantillas(cfg)
    ancho = int(str(plantillas.tokens["lienzo"]["ancho"]).removesuffix("px"))
    alto = int(str(plantillas.tokens["lienzo"]["alto"]).removesuffix("px"))
    archivos, avisos = [], []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        navegador = _lanzar(p)
        pagina = navegador.new_page(viewport={"width": ancho, "height": alto}, device_scale_factor=1)
        for pieza in piezas:
            if not pieza.guion:
                continue
            carpeta = destino / pieza.id
            carpeta.mkdir(parents=True, exist_ok=True)
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
