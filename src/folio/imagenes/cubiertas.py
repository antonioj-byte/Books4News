"""Cubiertas de los libros verificados, para las propuestas de diseño.

Las editoriales ven la cubierta como publicidad, así que se usa la real cuando hay una buena.
Orden de búsqueda: la edición española (por su ISBN, en Google Books y luego en Open Library), y
después el volumen de Google Books con el que se verificó la obra, las cubiertas de la obra en Open
Library y los ISBN de la ficha.

Se descartan: la imagen «no disponible» de Google Books, las cubiertas generadas (casi todo papel
en blanco con el título) y las de menos de ANCHO_MINIMO px, que en un carrusel se ven pixeladas.
Sin cubierta buena, las plantillas dibujan una tipográfica propia.

Cada cubierta se guarda en data/cache/cubiertas/<isbn o id>.jpg con un .json de su origen y de los
descartes (el informe y la web los muestran). El registro vacío («no hay») también se guarda para no
repetir la búsqueda, salvo que alguna fuente fallara de forma pasajera (5xx, 429, red): entonces se
vuelve a buscar en la siguiente ejecución. Un 5xx se reintenta una vez en el momento.
"""

from __future__ import annotations

import json
import re
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageStat

from folio.modelos import LibroVerificado

# Ancho mínimo. La cubierta se pinta a unos 400 px de ancho en la diapositiva del libro y a unos
# 210 en el cierre; las de Open Library («-L») suelen medir 290–330 px. Con 400 se descartaban casi todas.
ANCHO_MINIMO = 280
CRITERIO = 2              # sube cuando cambian los filtros: los «no hay» guardados antes se vuelven a buscar
ESPERA_S = 2.0            # antes de repetir un 5xx (los tests la ponen a 0)
AGENTE = "FolioLateral/0.1 (https://github.com/antonioj-byte/Books4News)"
_PASAJERO = re.compile(r"HTTP (5\d\d|429)|Error|Timeout")
GB_VOLUMEN = "https://www.googleapis.com/books/v1/volumes"
GB_PORTADA = "https://books.google.com/books/content?id={id}&printsec=frontcover&img=1&zoom=0&source=gbs_api"
OL_ISBN = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
OL_ID = "https://covers.openlibrary.org/b/id/{id}-L.jpg?default=false"
OL_OBRA = "https://openlibrary.org/works/{olid}.json"


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


def _candidatas(libro: LibroVerificado, c: httpx.Client, clave_gb: str | None,
                descartes: list[str]) -> list[tuple[str, str]]:
    """(origen, url) en orden de preferencia. Los fallos de las consultas previas van a `descartes`."""
    out = []
    isbn_es = libro.edicion_es_detalle.isbn if libro.edicion_es == "si" and libro.edicion_es_detalle else None
    if isbn_es:
        if clave_gb:
            origen = f"Google Books (edición española, {isbn_es})"
            try:
                r = c.get(GB_VOLUMEN, params={"q": f"isbn:{isbn_es}", "country": "ES", "key": clave_gb})
                if r.status_code != 200:
                    descartes.append(f"{origen}: HTTP {r.status_code}")
                for it in (r.json().get("items") or [])[:2] if r.status_code == 200 else []:
                    out.append((origen, GB_PORTADA.format(id=it["id"])))
            except (httpx.HTTPError, ValueError) as e:
                descartes.append(f"{origen}: {type(e).__name__}")
        out.append((f"Open Library (edición española, {isbn_es})", OL_ISBN.format(isbn=isbn_es)))
    if libro.google_id:
        out.append(("Google Books (obra verificada)", GB_PORTADA.format(id=libro.google_id)))
    if libro.olid:
        # Las cubiertas que Open Library asocia a la obra (con edición española, suelen ser la suya)
        try:
            r = c.get(OL_OBRA.format(olid=libro.olid))
            if r.status_code != 200:
                descartes.append(f"Open Library (obra {libro.olid}): HTTP {r.status_code}")
            for id_ in [i for i in (r.json().get("covers") or []) if i and i > 0][:2] if r.status_code == 200 else []:
                out.append((f"Open Library (obra {libro.olid}, cubierta {id_})", OL_ID.format(id=id_)))
        except (httpx.HTTPError, ValueError) as e:
            descartes.append(f"Open Library (obra {libro.olid}): {type(e).__name__}")
    for isbn in [i for i in libro.isbn13 if i != isbn_es][:4]:
        out.append((f"Open Library ({isbn})", OL_ISBN.format(isbn=isbn)))
    return out


def es_pasajero(descarte: str) -> bool:
    """Un fallo que puede no repetirse (5xx, 429, red): no prueba que no haya cubierta."""
    return bool(_PASAJERO.search(descarte))


def _get(c: httpx.Client, url: str) -> httpx.Response:
    """GET con un reintento si el servidor da un 5xx (Open Library los da a menudo y de forma pasajera)."""
    r = c.get(url)
    if r.status_code >= 500:
        time.sleep(ESPERA_S)
        r = c.get(url)
    return r


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


def _buscar_de_nuevo(guardado: dict) -> bool:
    """Un «no hay» guardado se vuelve a buscar si hubo fallos pasajeros o si es de un criterio anterior
    (hasta el 31/10 bastaba un 502 para dar el libro por perdido, y el mínimo era de 400 px)."""
    return not guardado.get("archivo") and (guardado.get("criterio", 1) < CRITERIO
                                            or any(es_pasajero(d) for d in guardado.get("descartes", [])))


def buscar(libro: LibroVerificado, dir_cache: Path, clave_gb: str | None = None,
           cliente: httpx.Client | None = None) -> Path | None:
    """Ruta de una cubierta buena del libro, o None. Usa y rellena la caché; el «no hay» solo se
    guarda cuando ninguna fuente falló de forma pasajera."""
    carpeta = dir_cache / "cubiertas"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = _nombre(libro)
    meta = carpeta / f"{nombre}.json"
    if meta.exists() and not _buscar_de_nuevo(json.loads(meta.read_text(encoding="utf-8"))):
        return en_cache(libro, dir_cache)
    descartes: list[str] = []
    with cliente or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": AGENTE}) as c:
        for origen, url in _candidatas(libro, c, clave_gb, descartes):
            try:
                r = _get(c, url)
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
            meta.write_text(json.dumps({"archivo": archivo, "origen": origen, "descartes": descartes, "criterio": CRITERIO},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            return carpeta / archivo
    meta.write_text(json.dumps({"archivo": None, "descartes": descartes, "criterio": CRITERIO},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return None
