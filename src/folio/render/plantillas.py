"""HTML de cada diapositiva con las plantillas de diseno/ (el design system en uso) o de
diseno/propuestas/<direccion>/ (una propuesta).

El aspecto vive en tokens.yaml (que se convierte en variables CSS) y en plantillas/ (una por tipo
de diapositiva, solo con esas variables). html_diapositiva() es la misma para el PNG y para la
vista previa de la web: solo cambian `base_url` (de dónde salen fuentes y estilos) y `url_medio`
(de dónde salen las imágenes).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from folio.config import Config
from folio.modelos import Diapositiva, Pieza
from folio.render.medios import Medios, como_uri
from folio.render.textos import (FIRMA_FINAL, color_de_pieza, fecha_larga, ficha_libros, libro_de_diapositiva,
                                 texto_html, titular_con_remate)


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
    lineas = [f"  --{grupo}-{clave.replace('_', '-')}: {valor};"
              for grupo, valores in tokens.items() if isinstance(valores, dict)
              for clave, valor in valores.items() if isinstance(valor, (str, int, float))]
    return ":root {\n" + "\n".join(lineas) + "\n}"


@dataclass
class Plantillas:
    cfg: Config
    direccion: str | None = None
    buscar_cubiertas: bool = False
    url_medio: Callable[[Path], str] = como_uri

    def __post_init__(self):
        self.tokens = cargar_tokens(self.cfg, self.direccion)
        self.env = Environment(loader=FileSystemLoader(dir_diseno(self.cfg, self.direccion) / "plantillas"),
                               autoescape=select_autoescape(["html"]))
        self.medios = Medios(self.cfg, self.url_medio, self.buscar_cubiertas)

    def html_diapositiva(self, pieza: Pieza, n: int, base_url: str | None = None) -> str:
        """HTML completo de la diapositiva n (1, 2, …) de la pieza."""
        d = pieza.guion.diapositivas[n - 1]
        return self.env.get_template(f"{d.tipo}.html").render(
            **self._base(base_url), **self._texto(pieza, d, n), **self._medios_y_arte(pieza, d))

    def _base(self, base_url: str | None) -> dict:
        logo = self.tokens["logotipo"].strip()
        return {
            "base_url": base_url or dir_diseno(self.cfg, self.direccion).resolve().as_uri() + "/",
            "tokens": self.tokens, "css_tokens": Markup(css_tokens(self.tokens)),
            "logotipo": Markup(logo),
            "logotipo_grande": Markup(logo.replace('class="logotipo"', 'class="logotipo logotipo--grande"', 1)),
        }

    def _texto(self, pieza: Pieza, d: Diapositiva, n: int) -> dict:
        portada = pieza.guion.diapositivas[0]
        remate = pieza.arte.remate if pieza.arte else None
        return {
            "tipo": d.tipo, "rotulo": self.tokens["rotulos"].get(d.tipo, ""),
            "texto": texto_html(FIRMA_FINAL.sub("", d.texto) if d.tipo == "cierre" else d.texto),
            "n": n, "total": len(pieza.guion.diapositivas), "pieza_id": pieza.id,
            "fecha_larga": fecha_larga(pieza.fecha), "anio_hoy": int(pieza.fecha[:4]),
            "titular": texto_html(portada.texto), "titular_remate": titular_con_remate(portada.texto, remate),
            "subtitulo": texto_html(portada.subtitulo) if portada.subtitulo else None,
        }

    def _medios_y_arte(self, pieza: Pieza, d: Diapositiva) -> dict:
        a = pieza.arte
        imagen = self.medios.imagen(pieza)
        retrato = self.medios.retrato(pieza)
        if d.tipo == "portada" and retrato:
            imagen = retrato        # la cara del autor manda en la portada
        estilo, svg = self.medios.portada(pieza, imagen)
        libros = ficha_libros(pieza, self.medios.cubierta)
        campos = self.tokens.get("campos_portada") or {}
        paleta = self.tokens.get("paleta_piezas") or []
        return {
            "imagen": imagen, "retrato": retrato, "portada_estilo": estilo, "ilustracion": svg,
            "libros": libros if d.tipo == "cierre" else [], "libros_pieza": libros,
            "libro": (libro_de_diapositiva(libros, pieza, d.texto) or (libros[:1] or [None])[0]) if d.tipo == "libro" else None,
            "tono": a.tono if a else None, "acento": a.acento if a else None, "antetitulo": a.antetitulo if a else None,
            "cifra": a.cifra if a else None, "cifra_rotulo": a.cifra_rotulo if a else None,
            "campo": campos.get(a.tono if a else "", campos.get("sereno")),
            "color": paleta[color_de_pieza(pieza, len(paleta))] if paleta else None,
        }
