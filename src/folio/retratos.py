"""Retratos de los autores, para poner caras en las piezas.

El autor se busca en Wikidata (servicio SPARQL): personas con ese nombre y una imagen (P18), la
más enlazada primero. La foto está en Wikimedia Commons y su licencia se comprueba allí con el
mismo criterio que el resto de imágenes (folio.imagenes); `permitir_cc_by_sa` amplía el criterio a
CC BY-SA, la licencia de casi todos los retratos de Commons, que obliga a publicar la imagen
derivada con la misma licencia (lo decide la configuración: arte.retratos_cc_by_sa).

El retrato se guarda en data/cache/<fecha>/imagenes/<pieza>-retrato.jpg con su .json.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from urllib.parse import unquote

import httpx

from folio import imagenes

SPARQL = "https://query.wikidata.org/sparql"
IDIOMAS = ("es", "en", "fr", "de", "it", "pt", "ru", "ca")
_CONSULTA = """SELECT ?img ?enlaces WHERE {{
  VALUES ?nombre {{ {nombres} }}
  ?p rdfs:label ?nombre; wdt:P31 wd:Q5; wdt:P18 ?img; wikibase:sitelinks ?enlaces.
}} ORDER BY DESC(?enlaces) LIMIT 1"""


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def variantes(nombre: str) -> list[str]:
    """El nombre tal cual y sin acentos («Politkóvskaya» → «Politkovskaya»), sin repetir."""
    nombre = " ".join(nombre.split())
    return list(dict.fromkeys([nombre, _sin_acentos(nombre)]))


def _literal(texto: str, idioma: str) -> str:
    return '"' + texto.replace("\\", "").replace('"', "") + f'"@{idioma}'


def archivo_en_commons(nombre: str, cliente: httpx.Client) -> str | None:
    """Nombre del archivo de Commons con el retrato del autor, o None."""
    nombres = " ".join(_literal(v, i) for v in variantes(nombre) for i in IDIOMAS)
    r = cliente.get(SPARQL, params={"query": _CONSULTA.format(nombres=nombres)},
                    headers={"Accept": "application/sparql-results+json"})
    r.raise_for_status()
    filas = r.json().get("results", {}).get("bindings", [])
    if not filas:
        return None
    url = filas[0]["img"]["value"]               # …/Special:FilePath/Nombre_del_archivo.jpg
    return unquote(url.rsplit("/", 1)[-1]).replace("_", " ")


def licencia_retrato(img: imagenes.ImagenLibre, permitir_cc_by_sa: bool) -> imagenes.ImagenLibre:
    """Con permitir_cc_by_sa, una foto rechazada solo por ser CC BY-SA (sin NC ni ND) pasa a ser libre."""
    partes = img.licencia.lower().replace("-", " ").split()
    if not img.libre and permitir_cc_by_sa and partes[:2] == ["cc", "by"] and "sa" in partes \
            and not {"nc", "nd"} & set(partes):
        img.libre, img.motivo = True, ""
    return img


def buscar_y_fijar(autor: str, pieza_id: str, dir_cache_fecha: Path, permitir_cc_by_sa: bool = False) -> tuple[imagenes.ImagenLibre | None, str]:
    """Busca el retrato del autor y lo fija para la pieza. Devuelve (imagen o None, motivo)."""
    with httpx.Client(headers={"User-Agent": imagenes.AGENTE}, timeout=30) as c:
        archivo = archivo_en_commons(autor, c)
    if not archivo:
        return None, f"Sin retrato de {autor} en Wikidata"
    img = licencia_retrato(imagenes.ficha(f"commons:File:{archivo}"), permitir_cc_by_sa)
    if not img.libre:
        return None, f"Retrato de {autor} descartado: {img.motivo}"
    img.enfoque = (50, 28)        # en un retrato, la cara suele estar en el tercio de arriba
    imagenes.fijar(img, f"{pieza_id}-retrato", dir_cache_fecha)
    return img, ""


def de_pieza(pieza_id: str, dir_cache_fecha: Path) -> imagenes.ImagenLibre | None:
    return imagenes.de_pieza(f"{pieza_id}-retrato", dir_cache_fecha)
