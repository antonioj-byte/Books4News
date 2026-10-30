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
from typing import Callable
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from folio.config import Config
from folio.modelos import Pieza
from folio.guion import libro_verificado

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")
_CURSIVA = re.compile(r"\*([^*\n]+)\*")
# En la imagen firma el logotipo: la firma del texto del cierre («— Folio») no se repite.
_FIRMA_FINAL = re.compile(r"\s*(?:[—–-]\s*)?Folio\.?\s*$")


def dir_diseno(cfg: Config, direccion: str | None = None) -> Path:
    """diseno/ (el design system en uso) o diseno/propuestas/<direccion>/ (una propuesta)."""
    return cfg.raiz / "diseno" if not direccion else cfg.raiz / "diseno" / "propuestas" / direccion


def direcciones(cfg: Config) -> list[str]:
    carpeta = cfg.raiz / "diseno" / "propuestas"
    return sorted(d.name for d in carpeta.iterdir() if (d / "tokens.yaml").exists()) if carpeta.exists() else []


def cargar_tokens(cfg: Config, direccion: str | None = None) -> dict:
    return yaml.safe_load((dir_diseno(cfg, direccion) / "tokens.yaml").read_text(encoding="utf-8"))


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


def ficha_libros(pieza: Pieza, cubierta=None) -> list[dict]:
    """Libros del cierre con sus datos verificados: editorial y traductor españoles, o nada.

    `cubierta`, si se da, es una función LibroVerificado → URL de su cubierta (o None)."""
    out = []
    for lg in pieza.guion.libros if pieza.guion else []:
        v = libro_verificado(lg, pieza.libros)
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
        out.append({"titulo": texto_html(lg.titulo.replace("*", "")), "autor": lg.autor, "datos": " · ".join(datos),
                    "anio": v.anio_primera_edicion if v else None,
                    "editorial": lg.editorial_espanola if v and v.edicion_es == "si" else None,
                    "edicion_es": v.edicion_es if v else "desconocido",
                    "cubierta": cubierta(v) if cubierta and v else None})
    return out


def _sin_marcas(texto: str) -> str:
    return re.sub(r"\W+", " ", texto.replace("*", "")).strip().lower()


def libro_de_diapositiva(libros: list[dict], pieza: Pieza, texto: str) -> dict | None:
    """El libro del que habla una diapositiva: el primero cuyo título aparece en el texto."""
    plano = _sin_marcas(texto)
    for libro, lg in zip(libros, pieza.guion.libros):
        corto = _sin_marcas(lg.titulo.split(":")[0])   # sin subtítulo
        if corto and corto in plano:
            return libro
    return None


def titular_con_remate(texto: str, remate: str | None) -> Markup:
    """El titular con su remate (el final, en cursiva) si el remate es literalmente el final del titular."""
    if remate:
        corte = texto.rstrip().rstrip(".").rfind(remate.rstrip().rstrip("."))
        if corte > 0 and texto[:corte].strip():
            return Markup(f'{texto_html(texto[:corte])}<span class="remate">{texto_html(texto[corte:])}</span>')
    return texto_html(texto)


def color_de_pieza(pieza: Pieza, n_colores: int) -> int:
    """Índice estable de color para la pieza (las propuestas que cambian de color por pieza)."""
    return sum(map(ord, pieza.id)) % n_colores if n_colores else 0


def _como_uri(ruta: Path) -> str:
    return ruta.resolve().as_uri()


@dataclass
class Plantillas:
    cfg: Config
    direccion: str | None = None
    # Buscar en la red las cubiertas que no estén en la caché (el render sí; la vista previa de la
    # web solo usa las que dejó la etapa de arte)
    buscar_cubiertas: bool = False
    # Archivo de data/cache → URL desde la que lo carga el navegador (file:// en el PNG, la API en la web)
    url_medio: Callable[[Path], str] = _como_uri

    def __post_init__(self):
        self._cubiertas: dict[str, str | None] = {}
        self.tokens = cargar_tokens(self.cfg, self.direccion)
        self.env = Environment(loader=FileSystemLoader(dir_diseno(self.cfg, self.direccion) / "plantillas"),
                               autoescape=select_autoescape(["html"]))

    def _cubierta(self, libro) -> str | None:
        from folio import cubiertas

        clave = libro.olid or libro.google_id or libro.titulo
        if clave not in self._cubiertas:
            raiz = self.cfg.dir_cache("x").parent
            ruta = (cubiertas.buscar(libro, raiz, self.cfg.google_books_api_key) if self.buscar_cubiertas
                    else cubiertas.en_cache(libro, raiz))
            self._cubiertas[clave] = self.url_medio(ruta) if ruta else None
        return self._cubiertas[clave]

    def _imagen(self, pieza: Pieza, sufijo: str = "") -> dict | None:
        """La imagen fijada para la pieza (o su retrato, con sufijo «-retrato»), lista para la plantilla."""
        from folio import imagenes

        cache = self.cfg.dir_cache(pieza.fecha)
        img = imagenes.de_pieza(pieza.id + sufijo, cache)
        if not img or not img.local or not (imagenes.dir_imagenes(cache) / img.local).exists():
            return None
        return {"src": self.url_medio(imagenes.dir_imagenes(cache) / img.local), "credito": img.credito,
                "enfoque": img.enfoque, "grabado": bool(pieza.arte and pieza.arte.recurso == "grabado")}

    def _portada(self, pieza: Pieza, imagen: dict | None) -> tuple[str, Markup | None]:
        """Estilo de portada que se puede pintar de verdad: sin SVG o sin imagen, se cae al círculo."""
        from folio import ilustracion

        estilo = pieza.arte.portada if pieza.arte else "sangre"
        if estilo in ("sangre", "banda", "caja", "neon") and not imagen:
            return "tipografica", None
        if estilo == "ilustracion":
            ruta = ilustracion.ruta(self.cfg.dir_cache(pieza.fecha), pieza.id)
            if ruta.exists():
                # El SVG se guardó ya saneado (folio.ilustracion.sanear): solo formas, sin texto ni scripts
                return estilo, Markup(ruta.read_text(encoding="utf-8"))
            return "circulo", None
        if estilo == "collage" and not imagen:
            return "circulo", None
        return estilo, None

    def html_diapositiva(self, pieza: Pieza, n: int, base_url: str | None = None) -> str:
        """HTML completo de la diapositiva n (1, 2, …) de la pieza."""
        d = pieza.guion.diapositivas[n - 1]
        logo = self.tokens["logotipo"].strip()
        imagen = self._imagen(pieza)
        retrato = self._imagen(pieza, "-retrato")
        if retrato:
            retrato["grabado"] = False
        if d.tipo == "portada" and retrato:
            imagen = retrato        # la cara del autor manda en la portada
        estilo, svg = self._portada(pieza, imagen)
        campos = self.tokens.get("campos_portada") or {}
        campo = campos.get(pieza.arte.tono if pieza.arte else "", campos.get("sereno"))
        paleta = self.tokens.get("paleta_piezas") or []
        portada = pieza.guion.diapositivas[0]
        libros = ficha_libros(pieza, self._cubierta)
        return self.env.get_template(f"{d.tipo}.html").render(
            base_url=base_url or dir_diseno(self.cfg, self.direccion).resolve().as_uri() + "/",
            tokens=self.tokens, css_tokens=Markup(css_tokens(self.tokens)),
            logotipo=Markup(logo), logotipo_grande=Markup(logo.replace('class="logotipo"', 'class="logotipo logotipo--grande"', 1)),
            tipo=d.tipo, rotulo=self.tokens["rotulos"].get(d.tipo, ""),
            texto=texto_html(_FIRMA_FINAL.sub("", d.texto) if d.tipo == "cierre" else d.texto),
            n=n, total=len(pieza.guion.diapositivas), pieza_id=pieza.id, fecha_larga=fecha_larga(pieza.fecha),
            libros=libros if d.tipo == "cierre" else [], libros_pieza=libros, retrato=retrato,
            libro=(libro_de_diapositiva(libros, pieza, d.texto) or (libros[:1] or [None])[0]) if d.tipo == "libro" else None,
            titular=texto_html(portada.texto), imagen=imagen, anio_hoy=int(pieza.fecha[:4]),
            titular_remate=titular_con_remate(portada.texto, pieza.arte.remate if pieza.arte else None),
            subtitulo=texto_html(portada.subtitulo) if portada.subtitulo else None,
            acento=pieza.arte.acento if pieza.arte else None,
            tono=pieza.arte.tono if pieza.arte else None, antetitulo=pieza.arte.antetitulo if pieza.arte else None, portada_estilo=estilo, ilustracion=svg, campo=campo, cifra=pieza.arte.cifra if pieza.arte else None, cifra_rotulo=pieza.arte.cifra_rotulo if pieza.arte else None,
            color=paleta[color_de_pieza(pieza, len(paleta))] if paleta else None,
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
