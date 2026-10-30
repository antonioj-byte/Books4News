"""Ilustración vectorial de portada (prototipo; prompts/ilustrador.md).

Un modelo dibuja en SVG una metáfora visual de la idea de la pieza, con la paleta cerrada de Folio
y el color de campo que corresponde al tono (diseno/tokens.yaml, `campos_portada`). El SVG es
salida de un modelo: antes de guardarlo se reconstruye con una lista cerrada de elementos y
atributos (nada de texto, imágenes, estilos, scripts ni enlaces) y se rechaza si queda vacío.
Se guarda en data/cache/<fecha>/imagenes/<pieza>-ilustracion.svg.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from folio.config import Config
from folio.llm import LLM, bloque_reenviable, cargar_prompt, con_cache
from folio.modelos import IlustracionLLM, Pieza

SVG_NS = "http://www.w3.org/2000/svg"
ELEMENTOS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
ATRIBUTOS = {"d", "x", "y", "width", "height", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "points",
             "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "transform", "opacity",
             "fill-rule", "viewBox"}
MAX_ELEMENTOS = 120
_VALOR_SEGURO = re.compile(r"^[\w\s.,#%()+-]*$")


class SVGInvalido(ValueError):
    pass


def sanear(svg: str) -> str:
    """SVG reconstruido solo con elementos y atributos permitidos; lanza SVGInvalido si no sirve."""
    try:
        raiz = ET.fromstring(svg.strip())
    except ET.ParseError as e:
        raise SVGInvalido(f"no es XML válido: {e}") from None
    n = 0

    def copiar(nodo: ET.Element) -> ET.Element | None:
        nonlocal n
        nombre = nodo.tag.split("}")[-1]
        if nombre not in ELEMENTOS:
            return None
        n += 1
        if n > MAX_ELEMENTOS:
            raise SVGInvalido(f"más de {MAX_ELEMENTOS} elementos")
        nuevo = ET.Element(nombre)
        for k, v in nodo.attrib.items():
            k = k.split("}")[-1]
            if k in ATRIBUTOS and _VALOR_SEGURO.match(v) and "url" not in v.lower():
                nuevo.set(k, v)
        for hijo in nodo:
            h = copiar(hijo)
            if h is not None:
                nuevo.append(h)
        return nuevo

    if raiz.tag.split("}")[-1] != "svg":
        raise SVGInvalido("el elemento raíz no es <svg>")
    limpio = copiar(raiz)
    if n < 3:
        raise SVGInvalido("la ilustración está vacía")
    limpio.set("xmlns", SVG_NS)
    limpio.set("viewBox", "0 0 1080 600")
    limpio.set("preserveAspectRatio", "xMidYMid meet")
    for k in ("width", "height", "x", "y"):
        limpio.attrib.pop(k, None)
    return ET.tostring(limpio, encoding="unicode")


def ruta(dir_cache_fecha: Path, pieza_id: str) -> Path:
    return dir_cache_fecha / "imagenes" / f"{pieza_id}-ilustracion.svg"


def dibujar(llm: LLM, cfg: Config, pieza: Pieza, campo: dict) -> tuple[str, Path]:
    """Pide la ilustración, la sanea y la guarda. Devuelve (concepto, ruta)."""
    g = pieza.guion
    datos = (f"<pieza>\ntitular de portada: {g.diapositivas[0].texto}\nidea: {g.idea_elegida}\n"
             f"por qué: {g.por_que}\nlibros: {', '.join(f'{l.titulo} ({l.autor})' for l in g.libros)}\n"
             f"tono: {pieza.arte.tono if pieza.arte else 'sereno'}\n</pieza>")
    prompt = cargar_prompt(cfg, "ilustrador", {"[pegar fondo]": campo["fondo"], "[pegar color]": campo["color"],
                                               "[pegar pieza]": datos})
    mensajes = [{"role": "user", "content": con_cache(cfg, "ilustrador", prompt)}]
    res, contenido = llm.estructurado(f"ilustracion:{pieza.id}", mensajes, IlustracionLLM,
                                      etapa_modelo="ilustracion", max_tokens=16000)
    try:
        svg = sanear(res.svg)
    except SVGInvalido as exc:     # un reintento, diciéndole qué falló
        mensajes += [{"role": "assistant", "content": [bloque_reenviable(b) for b in contenido]},
                     {"role": "user", "content": f"El SVG no es válido ({exc}). Devuélvelo completo y bien formado."}]
        res, _ = llm.estructurado(f"ilustracion:{pieza.id}:reintento", mensajes, IlustracionLLM,
                                  etapa_modelo="ilustracion", max_tokens=16000)
        svg = sanear(res.svg)
    destino = ruta(cfg.dir_cache(pieza.fecha), pieza.id)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(svg, encoding="utf-8")
    return res.concepto, destino
