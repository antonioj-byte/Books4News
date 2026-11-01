"""HTML de cada diapositiva con las plantillas de diseno/ (el design system en uso) o de
diseno/propuestas/<direccion>/ (una propuesta).

El aspecto vive en tokens.yaml (que se convierte en variables CSS) y en plantillas/ (una por tipo
de diapositiva, solo con esas variables). html_diapositiva() es la misma para el PNG y para la
vista previa de la web: solo cambian `base_url` (de dónde salen fuentes y estilos) y `url_medio`
(de dónde salen las imágenes).
"""

from __future__ import annotations

import unicodedata

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

import re

from folio import infografia as infografias
from folio.verificacion_texto import sin_subtitulo
from folio import sin_foto as recursos_sin_foto
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



def misma_persona(a: str | None, b: str | None) -> bool:
    """Mismo autor aunque cambien tildes, mayúsculas o un segundo apellido («Mariana Enriquez» y
    «Mariana Enríquez»): todas las palabras del nombre más corto están en el más largo."""
    if not a or not b:
        return False
    pa, pb = (set(unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower().replace(".", " ").split()) for x in (a, b))
    corto, largo = sorted((pa, pb), key=len)
    return bool(corto) and corto <= largo

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
            **self._base(base_url), **self._texto(pieza, d, n), **self._medios_y_arte(pieza, d, n))

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

    @staticmethod
    def _libro(libros: list[dict], pieza: Pieza, n: int) -> dict | None:
        """El libro de la diapositiva n, o None si ya salió en una diapositiva de libro anterior: la
        cubierta no se repite en el carrusel (la diapositiva sale solo con el texto)."""
        def de(x: Diapositiva) -> dict | None:
            return libro_de_diapositiva(libros, pieza, x.texto) or (libros[:1] or [None])[0]
        libro = de(pieza.guion.diapositivas[n - 1])
        antes = [de(x) for x in pieza.guion.diapositivas[:n - 1] if x.tipo == "libro"]
        return None if libro and any(a and a["titulo"] == libro["titulo"] for a in antes) else libro

    def _infografia(self, pieza: Pieza, d: Diapositiva, n: int) -> dict | None:
        """La infografía de la (primera) diapositiva de la idea, comprobada otra vez contra el guion actual.
        None si no hay, si ya no casa o si es un esquema sin su ilustración: sale como antes."""
        a = pieza.arte
        if not a or not a.infografia or n != next(i for i, x in enumerate(pieza.guion.diapositivas, 1) if x.tipo == "idea"):
            return None
        imagen = self.medios.esquema(pieza) if a.infografia.tipo == "esquema" else None
        info, _ = infografias.validar(a.infografia, pieza, self.cfg.pipeline.arte.infografias, True)
        if not info or (info.tipo == "esquema" and not imagen):
            return None
        out = {"tipo": info.tipo, "titulo": info.titulo, "etiquetas": info.etiquetas, "imagen": imagen}
        if info.tipo == "linea":
            hitos = infografias.hitos(pieza)
            paso = 60 / (len(hitos) - 1)
            out["hitos"] = [{**h, "x": round(20 + i * paso, 2), "que_html": texto_html(f"*{h['que']}*" if h["que"] != "la noticia" else h["que"])}
                            for i, h in enumerate(hitos)]
        return out

    def _sin_foto(self, pieza: Pieza, d: Diapositiva) -> dict | None:
        """El recurso de la diapositiva de actualidad sin foto ni cifra, comprobado otra vez contra el texto
        actual (puede haberse editado en la web). None si no hay o ya no casa: sale solo con el texto."""
        a = pieza.arte
        if not a or not a.sin_foto:
            return None
        sf, _ = recursos_sin_foto.validar(a.sin_foto, d.texto, self.cfg.pipeline.arte.sin_foto)
        if not sf:
            return None
        out = {"recurso": sf.recurso, "etiquetas": [e.upper() for e in sf.etiquetas],
               "numero": sf.numero, "numero_rotulo": sf.numero_rotulo,
               "palabra": sf.palabra.upper() if sf.palabra else None,
               # La palabra gigante va en vertical: cabe a toda la altura con unas 9 letras a 250 px
               "tam_palabra": min(250, int(1420 / (0.64 * len(sf.palabra)))) if sf.palabra else None,
               "texto_marcado": recursos_sin_foto.marcar(d.texto, sf.golpe_remate, texto_html) or texto_html(d.texto)}
        if sf.sello:
            palabras = sf.sello.split()
            out["sello"] = (" ".join(palabras[:-1]).upper(), palabras[-1])
        if sf.recurso == "golpe":
            i = recursos_sin_foto.inicio_del_final(sf.golpe, d.texto)
            antes, golpe = d.texto[:i], d.texto[i:]
            if antes.count("*") % 2:
                return None
            out["golpe_antes"], out["golpe"] = texto_html(antes), titular_con_remate(golpe, sf.golpe_remate)
            palabras = len(golpe.split())     # cuanto más larga la frase, más pequeña: 150 px hasta 6 palabras
            out["tam_golpe"] = 150 if palabras <= 6 else 124 if palabras <= 9 else 104
        return out

    def _medios_y_arte(self, pieza: Pieza, d: Diapositiva, n: int) -> dict:
        a = pieza.arte
        imagen = self.medios.imagen(pieza)
        libros = ficha_libros(pieza, self.medios.cubierta)
        libro = self._libro(libros, pieza, n) if d.tipo == "libro" else None
        retrato = self.medios.retrato(pieza)
        # La cara solo va con su libro: en la portada, si es el autor del libro principal; en una
        # diapositiva de libro, si es el autor de ese libro
        if retrato and not misma_persona(retrato["persona"], (libro or (libros[:1] or [{}])[0]).get("autor")):
            retrato = None
        if d.tipo == "portada" and retrato and not (a and a.portada == "panorama"):
            imagen = retrato        # la cara del autor manda en la portada (salvo en la panorámica, B6)
        estilo, svg = self.medios.portada(pieza, imagen)
        if d.tipo == "portada" and imagen is retrato and retrato and retrato.get("pequena") and estilo != "panorama":
            estilo = "copia"        # foto pequeña (de prensa): una copia en papel sobre la mesa, no a sangre
        panorama = bool(d.tipo == "actualidad" and imagen and a and a.portada == "panorama"
                        and self.medios.portada(pieza, imagen)[0] == "panorama")
        # La cifra destacada solo si sigue literalmente en el texto (puede haberse editado en la web)
        cifra = a.cifra if a and a.cifra and d.tipo == "actualidad" and recursos_sin_foto.literal(a.cifra, d.texto) else None
        cifra_rotulo = a.cifra_rotulo if cifra and a.cifra_rotulo and recursos_sin_foto.literal(a.cifra_rotulo, d.texto) else None
        sin_foto = self._sin_foto(pieza, d) if d.tipo == "actualidad" and not imagen and not cifra else None
        info = self._infografia(pieza, d, n) if d.tipo == "idea" else None
        if info and info["tipo"] == "mapa" and self.cfg.pipeline.arte.mapa_ilustrado and \
                (dir_diseno(self.cfg, self.direccion) / "ilustraciones" / "salas.jpg").exists():
            info["salas"] = "ilustraciones/salas.jpg"          # relativa a <base>: vale en el PNG y en la web
            # Solo el título, sin el subtítulo («La generación ansiosa», no «…: Por qué las redes…»)
            info["libro"] = texto_html("*" + sin_subtitulo(pieza.guion.libros[0].titulo.replace("*", "")).strip() + "*") \
                if pieza.guion.libros else ""
        # El buscador de la portada (B2): la pregunta del director de arte y, de respuesta, el libro
        principal = pieza.guion.libros[0].titulo.replace("*", "") if pieza.guion.libros else None
        buscador = ({"pregunta": a.pregunta, "respuesta": texto_html(f"*{principal}*") if principal else None}
                    if d.tipo == "portada" and a and a.pregunta and self.cfg.pipeline.arte.buscador else None)
        # La cifra que cuenta (M2), la palabra gigante que sube (M7) y la interferencia de la portada (M10)
        contar = bool(cifra and re.search(r"\d", cifra))
        interferencia = bool(d.tipo == "portada" and a and a.tono in self.cfg.pipeline.arte.interferencia and a.tono != "grave")
        campos = self.tokens.get("campos_portada") or {}
        paleta = self.tokens.get("paleta_piezas") or []
        return {
            "imagen": imagen, "retrato": retrato, "portada_estilo": estilo, "ilustracion": svg,
            "libros": libros if d.tipo == "cierre" else [], "libros_pieza": libros,
            "libro": libro, "sin_foto": sin_foto, "infografia": info, "contar": contar, "interferencia": interferencia,
            # Las diapositivas que también salen en vídeo (folio.render.video): la portada con imagen o con
            # interferencia, la noticia con cifra que cuenta o con palabra gigante, la idea con infografía
            "panorama": panorama, "buscador": buscador,
            "video": (d.tipo == "portada" and ((bool(imagen) and estilo != "panorama") or interferencia or bool(buscador)))
                     or (d.tipo == "actualidad" and (contar or bool(sin_foto and sin_foto["recurso"] == "gigante")))
                     or bool(info),
            "tono": a.tono if a else None, "acento": a.acento if a else None, "antetitulo": a.antetitulo if a else None,
            "cifra": cifra, "cifra_rotulo": cifra_rotulo,
            "campo": campos.get(a.tono if a else "", campos.get("sereno")),
            "color": paleta[color_de_pieza(pieza, len(paleta))] if paleta else None,
        }
