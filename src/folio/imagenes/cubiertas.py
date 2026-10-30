"""Cubiertas de los libros verificados, para las propuestas de diseño.

Las editoriales ven la cubierta como publicidad, así que se usa la real cuando hay una buena.
Orden de búsqueda: la edición española (por su ISBN, en Google Books y luego en Open Library), y
después el volumen de Google Books con el que se verificó la obra y los ISBN de la ficha.

Se descartan: la imagen «no disponible» de Google Books, las cubiertas generadas (casi todo papel
en blanco con el título) y las de menos de ANCHO_MINIMO px, que en un carrusel se ven pixeladas.
Sin cubierta buena, las plantillas dibujan una tipográfica propia.

Cada cubierta se guarda en data/cache/cubiertas/<isbn o id>.jpg con un .json de su origen; el
registro vacío («no hay») también se guarda para no repetir la búsqueda.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageStat

from folio.modelos import LibroVerificado

ANCHO_MINIMO = 400
GB_VOLUMEN = "https://www.googleapis.com/books/v1/volumes"
GB_PORTADA = "https://books.google.com/books/content?id={id}&printsec=frontcover&img=1&zoom=0&source=gbs_api"
OL_ISBN = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"


def es_buena(datos: bytes) -> tuple[bool, str]:
    try:
        im = Image.open(BytesIO(datos)).convert("RGB")
    except Exception:
        return False, "no es una imagen"
    if im.width < ANCHO_MINIMO:
        return False, f"demasiado pequeña ({im.width} px)"
    if not 1.2 <= im.height / im.width <= 1.8:
        return False, f"proporción rara ({im.width}×{im.height})"
    gris = im.convert("L").resize((60, 90))
    claros = sum(1 for v in gris.getdata() if v > 235) / (60 * 90)
    if claros > 0.85:
        return False, "cubierta genérica (casi toda en blanco)"
    if ImageStat.Stat(gris).stddev[0] < 12:
        return False, "imagen plana («no disponible»)"
    return True, ""


def _candidatas(libro: LibroVerificado, gb: httpx.Client, clave_gb: str | None) -> list[tuple[str, str]]:
    """(origen, url) en orden de preferencia."""
    out = []
    isbn_es = libro.edicion_es_detalle.isbn if libro.edicion_es == "si" and libro.edicion_es_detalle else None
    if isbn_es:
        if clave_gb:
            try:
                r = gb.get(GB_VOLUMEN, params={"q": f"isbn:{isbn_es}", "country": "ES", "key": clave_gb})
                for it in (r.json().get("items") or [])[:2]:
                    out.append((f"Google Books (edición española, {isbn_es})", GB_PORTADA.format(id=it["id"])))
            except (httpx.HTTPError, ValueError):
                pass
        out.append((f"Open Library (edición española, {isbn_es})", OL_ISBN.format(isbn=isbn_es)))
    if libro.google_id:
        out.append(("Google Books (obra verificada)", GB_PORTADA.format(id=libro.google_id)))
    for isbn in libro.isbn13[:4]:
        out.append((f"Open Library ({isbn})", OL_ISBN.format(isbn=isbn)))
    return out


def _nombre(libro: LibroVerificado) -> str:
    return (libro.edicion_es_detalle.isbn if libro.edicion_es_detalle and libro.edicion_es_detalle.isbn
            else libro.olid or libro.google_id or libro.titulo).replace("/", "_")


def en_cache(libro: LibroVerificado, dir_cache: Path) -> Path | None:
    """La cubierta ya buscada, sin ir a la red (None si no hay o no se ha buscado)."""
    carpeta = dir_cache / "cubiertas"
    meta = carpeta / f"{_nombre(libro)}.json"
    if not meta.exists():
        return None
    guardado = json.loads(meta.read_text(encoding="utf-8"))
    return carpeta / guardado["archivo"] if guardado.get("archivo") else None


def buscar(libro: LibroVerificado, dir_cache: Path, clave_gb: str | None = None) -> Path | None:
    """Ruta de una cubierta buena del libro, o None. Usa y rellena la caché."""
    carpeta = dir_cache / "cubiertas"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = _nombre(libro)
    meta = carpeta / f"{nombre}.json"
    if meta.exists():
        return en_cache(libro, dir_cache)
    descartes = []
    with httpx.Client(timeout=30, follow_redirects=True,
                      headers={"User-Agent": "FolioLateral/0.1 (https://github.com/antonioj-byte/Books4News)"}) as c:
        for origen, url in _candidatas(libro, c, clave_gb):
            try:
                r = c.get(url)
            except httpx.HTTPError as e:
                descartes.append(f"{origen}: {type(e).__name__}")
                continue
            if r.status_code != 200:
                descartes.append(f"{origen}: HTTP {r.status_code}")
                continue
            buena, motivo = es_buena(r.content)
            if not buena:
                descartes.append(f"{origen}: {motivo}")
                continue
            archivo = f"{nombre}.jpg"
            Image.open(BytesIO(r.content)).convert("RGB").save(carpeta / archivo, quality=92)
            meta.write_text(json.dumps({"archivo": archivo, "origen": origen, "descartes": descartes},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            return carpeta / archivo
    meta.write_text(json.dumps({"archivo": None, "descartes": descartes}, ensure_ascii=False, indent=2), encoding="utf-8")
    return None
