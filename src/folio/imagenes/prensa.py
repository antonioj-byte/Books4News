"""Fotos de autor de las páginas de las editoriales (31/10, a petición del usuario: «normalmente ceden»).

Las editoriales publican en la ficha de cada autor una foto para la prensa, con el crédito del
fotógrafo. Se usa tal cual, con su crédito («Sebastián Freire · cortesía de Anagrama»), solo en piezas
sobre un libro de esa editorial, y nunca se transforma: no se pasa a un estilo generado con IA (la
cesión es para publicarla, no para hacer obras derivadas).

Son fotos pequeñas (unos 500 px), así que la portada las pone como una copia en papel sobre la mesa
(composición «copia»), no a sangre. Una editorial por adaptador; de momento, Anagrama (la ficha de autor
trae la foto y el crédito). Planeta publica la foto a 300 px y sin crédito en la página, y el buscador de
Penguin Random House España no responde: quedan fuera hasta que haya una vía mejor.

Ante 403 o 429 se para y se avisa, sin reintentar ni esquivar el bloqueo.

La etapa de arte la usa cuando Commons no tiene retrato (folio.arte._retrato).
"""

from __future__ import annotations

import html
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image

from folio.imagenes import libres

LADO_MINIMO = 400          # por debajo, la foto no aguanta ni como copia en la portada
AGENTE = libres.AGENTE


class BloqueoEditorial(Exception):
    """La web de la editorial respondió 403 o 429: se para y se avisa."""


def _llano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _get(c: httpx.Client, url: str) -> httpx.Response:
    r = c.get(url)
    if r.status_code in (403, 429):
        raise BloqueoEditorial(f"{url} respondió {r.status_code}")
    return r


# --- Anagrama -----------------------------------------------------------------------

_ANAGRAMA = "https://www.anagrama-ed.es"


def anagrama(autor: str, c: httpx.Client) -> dict | None:
    """La foto de la ficha de autor de Anagrama: {url, pagina, fotografo} o None. Las listas de autores van
    por la inicial del apellido (/autores/e) y las fichas son /autor/<apellidos>-<nombre>-<id>."""
    palabras = _llano(autor).split("-")
    if len(palabras) < 2:
        return None
    for apellido in palabras[1:][::-1]:
        lista = _get(c, f"{_ANAGRAMA}/autores/{apellido[0]}")
        if lista.status_code != 200:
            continue
        for slug in dict.fromkeys(re.findall(r'href="/autor/([a-z0-9-]+)"', lista.text)):
            partes = slug.rsplit("-", 1)[0].split("-")
            if set(palabras) <= set(partes):
                ficha = _get(c, f"{_ANAGRAMA}/autor/{slug}")
                if ficha.status_code != 200:
                    return None
                foto = re.search(r'<img[^>]+src="(https://cms\.anagrama-ed\.es/uploads/media/autores/[^"]+)"[^>]*alt="([^"]*)"', ficha.text) \
                    or re.search(r'<img[^>]+alt="([^"]*)"[^>]*src="(https://cms\.anagrama-ed\.es/uploads/media/autores/[^"]+)"', ficha.text)
                if not foto:
                    return None
                url = foto.group(1) if foto.group(1).startswith("http") else foto.group(2)
                credito = re.search(r"Fotograf[ií]a\s*(?:©|&copy;)\s*([^<\\\"]{2,80})", ficha.text)
                return {"url": url, "pagina": f"{_ANAGRAMA}/autor/{slug}",
                        "fotografo": html.unescape(credito.group(1)).strip(" .") if credito else ""}
    return None


ADAPTADORES: dict[str, tuple[str, Callable[[str, httpx.Client], dict | None]]] = {
    "anagrama": ("Anagrama", anagrama),
}


def adaptador(editorial: str | None) -> tuple[str, Callable] | None:
    """El adaptador de la editorial, sin mirar «Editorial», «Ediciones» ni el grupo («Editorial Anagrama»,
    «Anagrama Editorial»)."""
    palabras = [w for w in _llano(editorial or "").split("-") if w not in ("editorial", "ediciones", "ed", "edit")]
    return next((v for k, v in ADAPTADORES.items() if palabras[:1] == [k]), None)


def buscar_y_fijar(autor: str, editorial: str | None, pieza_id: str, dir_fecha: Path,
                   cliente: httpx.Client | None = None) -> tuple[libres.ImagenLibre | None, str]:
    """Busca la foto del autor en la web de su editorial y la fija como retrato de la pieza
    (<pieza>-retrato.jpg). Devuelve (imagen o None, motivo). BloqueoEditorial ante 403 o 429."""
    ad = adaptador(editorial)
    if not ad:
        return None, f"Sin fotos de prensa de {editorial or 'esta editorial'} (no hay adaptador)"
    nombre, buscar = ad
    with cliente or httpx.Client(headers={"User-Agent": AGENTE}, timeout=30, follow_redirects=True) as c:
        encontrada = buscar(autor, c)
        if not encontrada:
            return None, f"Sin foto de {autor} en la web de {nombre}"
        r = _get(c, encontrada["url"])
        r.raise_for_status()
    with Image.open(BytesIO(r.content)) as im:
        ancho, alto = im.size
        if max(ancho, alto) < LADO_MINIMO:
            return None, f"La foto de {autor} en la web de {nombre} es demasiado pequeña ({ancho}×{alto})"
        carpeta = libres.dir_imagenes(dir_fecha)
        carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in carpeta.glob(f"{pieza_id}-retrato.*"):
            viejo.unlink()
        im.convert("RGB").save(carpeta / f"{pieza_id}-retrato.jpg", quality=92)
    img = libres.ImagenLibre(
        archivo=f"prensa:{_llano(nombre)}:{encontrada['pagina'].rsplit('/', 1)[-1]}", pagina=encontrada["pagina"],
        url=encontrada["url"], ancho=ancho, alto=alto, licencia=f"cortesía de {nombre}", licencia_url=None,
        autor=encontrada["fotografo"] or "Fotógrafo sin acreditar", descripcion=f"Retrato de {autor}", libre=True, motivo="",
        local=f"{pieza_id}-retrato.jpg", fuente="", enfoque=(50, 35), persona=autor)
    libres.guardar_metadatos(img, f"{pieza_id}-retrato", dir_fecha)
    return img, ""


def es_de_prensa(img: libres.ImagenLibre | None) -> bool:
    return bool(img and img.archivo.startswith("prensa:"))
