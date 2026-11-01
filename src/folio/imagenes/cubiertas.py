"""Cubiertas de los libros verificados, para las propuestas de diseño.

Las editoriales ven la cubierta como publicidad, así que se usa la real cuando hay una buena.
Orden de búsqueda: la edición española (por su ISBN, en Google Books y luego en Open Library) y, después, las
otras ediciones en castellano de la obra en Open Library y en Google Books. Con edición española verificada,
nunca una cubierta en otra lengua (2/11, a petición del usuario: salía la inglesa de «Aprender a rezar en la era
de la técnica»): sin cubierta en castellano, las plantillas dibujan una tipográfica. Sin edición española (ya
casi nunca: la mesa solo admite libros con ella), el volumen de Google Books de la obra, sus cubiertas en Open
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
CRITERIO = 3              # sube cuando cambian los filtros: los «no hay» guardados antes se vuelven a buscar
ESPERA_S = 2.0            # antes de repetir un 5xx (los tests la ponen a 0)
AGENTE = "FolioLateral/0.1 (https://github.com/antonioj-byte/Books4News)"
_PASAJERO = re.compile(r"HTTP (5\d\d|429)|Error|Timeout")
GB_VOLUMEN = "https://www.googleapis.com/books/v1/volumes"
GB_PORTADA = "https://books.google.com/books/content?id={id}&printsec=frontcover&img=1&zoom=0&source=gbs_api"
OL_ISBN = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
OL_ID = "https://covers.openlibrary.org/b/id/{id}-L.jpg?default=false"
OL_OBRA = "https://openlibrary.org/works/{olid}.json"
OL_EDICIONES = "https://openlibrary.org/works/{olid}/editions.json"
OL_EDICION_ISBN = "https://openlibrary.org/isbn/{isbn}.json"
EN_CASTELLANO = "en castellano"     # marca los orígenes en castellano en el .json de la caché


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
    claros = sum(1 for v in gris.tobytes() if v > 235) / (60 * 90)
    if claros > 0.85:
        return False, "cubierta genérica (casi toda en blanco)"
    if ImageStat.Stat(gris).stddev[0] < 12:
        return False, "imagen plana («no disponible»)"
    return True, ""


def ediciones_en_castellano(c: httpx.Client, olid: str, descartes: list[str]) -> list[dict]:
    """Las ediciones en castellano de la obra en Open Library: {editorial, anio, isbn, titulo, covers}."""
    try:
        r = c.get(OL_EDICIONES.format(olid=olid), params={"limit": 100})
    except httpx.HTTPError as e:
        descartes.append(f"Open Library (ediciones de {olid}): {type(e).__name__}")
        return []
    if r.status_code != 200:
        descartes.append(f"Open Library (ediciones de {olid}): HTTP {r.status_code}")
        return []
    out = []
    for e in r.json().get("entries") or []:
        if not any(l.get("key") == "/languages/spa" for l in e.get("languages") or []):
            continue
        anio = re.search(r"\b(1[5-9]|20)\d\d\b", e.get("publish_date") or "")
        out.append({"editorial": ", ".join(e.get("publishers") or []) or None, "anio": anio.group(0) if anio else None,
                    "isbn": (e.get("isbn_13") or e.get("isbn_10") or [None])[0], "titulo": e.get("title"),
                    "covers": [i for i in e.get("covers") or [] if i and i > 0]})
    return out


def _gb_en_castellano(c: httpx.Client, libro: LibroVerificado, clave_gb: str | None, descartes: list[str],
                      editorial: str | None = None) -> list[tuple[str, str, dict]]:
    """Volúmenes en castellano de la obra en Google Books (con clave): (origen, url, datos de la edición)."""
    if not clave_gb:
        return []
    titulo = (libro.edicion_es_detalle.titulo if libro.edicion_es_detalle and libro.edicion_es_detalle.titulo
              else libro.titulo_propuesto)
    q = f'intitle:"{titulo}" inauthor:"{(libro.autores or [""])[0].split()[-1]}"' + (f' inpublisher:"{editorial}"' if editorial else "")
    origen = f"Google Books ({EN_CASTELLANO})"
    try:
        r = c.get(GB_VOLUMEN, params={"q": q, "langRestrict": "es", "country": "ES", "maxResults": 5, "key": clave_gb})
    except httpx.HTTPError as e:
        descartes.append(f"{origen}: {type(e).__name__}")
        return []
    if r.status_code != 200:
        descartes.append(f"{origen}: HTTP {r.status_code}")
        return []
    out = []
    for it in r.json().get("items") or []:
        v = it.get("volumeInfo") or {}
        if v.get("language") != "es":
            continue
        isbn = next((i["identifier"] for i in v.get("industryIdentifiers") or [] if i.get("type") == "ISBN_13"), None)
        out.append((f"{origen}, {v.get('publisher') or 'editorial no consta'}", GB_PORTADA.format(id=it["id"]),
                    {"editorial": v.get("publisher"), "anio": (v.get("publishedDate") or "")[:4] or None, "isbn": isbn,
                     "titulo": v.get("title")}))
    return out


def _candidatas(libro: LibroVerificado, c: httpx.Client, clave_gb: str | None,
                descartes: list[str]) -> list[tuple[str, str]]:
    """(origen, url) en orden de preferencia. Los fallos de las consultas previas van a `descartes`."""
    out = []
    isbn_es = libro.edicion_es_detalle.isbn if libro.edicion_es == "si" and libro.edicion_es_detalle else None
    if libro.edicion_es == "si":
        if isbn_es and clave_gb:
            origen = f"Google Books (edición española, {isbn_es})"
            try:
                r = c.get(GB_VOLUMEN, params={"q": f"isbn:{isbn_es}", "country": "ES", "key": clave_gb})
                if r.status_code != 200:
                    descartes.append(f"{origen}: HTTP {r.status_code}")
                for it in (r.json().get("items") or [])[:2] if r.status_code == 200 else []:
                    out.append((origen, GB_PORTADA.format(id=it["id"])))
            except (httpx.HTTPError, ValueError) as e:
                descartes.append(f"{origen}: {type(e).__name__}")
        if isbn_es:
            out.append((f"Open Library (edición española, {isbn_es})", OL_ISBN.format(isbn=isbn_es)))
        # Las otras ediciones en castellano de la obra; nunca las de otra lengua (2/11)
        if libro.olid:
            for e in ediciones_en_castellano(c, libro.olid, descartes):
                for id_ in e["covers"][:1]:
                    out.append((f"Open Library ({EN_CASTELLANO}, {e['editorial'] or 'editorial no consta'}"
                                f"{', ' + e['anio'] if e['anio'] else ''})", OL_ID.format(id=id_)))
        out += [(o, u) for o, u, _ in _gb_en_castellano(c, libro, clave_gb, descartes)]
        return out
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


def _en_castellano(origen: str | None) -> bool:
    return bool(origen) and ("edición española" in origen or EN_CASTELLANO in origen)


def _vale(guardado: dict, libro: LibroVerificado) -> bool:
    """Una cubierta guardada vale si, habiendo edición española, es en castellano (las de antes del 2/11 podían
    ser de otra lengua)."""
    return bool(guardado.get("archivo")) and (libro.edicion_es != "si" or _en_castellano(guardado.get("origen")))


def en_cache(libro: LibroVerificado, dir_cache: Path) -> Path | None:
    """La cubierta ya buscada, sin ir a la red (None si no hay, no se ha buscado o es de otra lengua)."""
    carpeta = dir_cache / "cubiertas"
    meta = carpeta / f"{_nombre(libro)}.json"
    if not meta.exists():
        return None
    guardado = json.loads(meta.read_text(encoding="utf-8"))
    return carpeta / guardado["archivo"] if _vale(guardado, libro) else None


def _buscar_de_nuevo(guardado: dict, libro: LibroVerificado | None = None) -> bool:
    """Un «no hay» guardado se vuelve a buscar si hubo fallos pasajeros o si es de un criterio anterior
    (hasta el 31/10 bastaba un 502 para dar el libro por perdido, y el mínimo era de 400 px). Y una cubierta
    guardada en otra lengua, si hay edición española (2/11)."""
    if guardado.get("archivo"):
        return libro is not None and not _vale(guardado, libro)
    return guardado.get("criterio", 1) < CRITERIO or any(es_pasajero(d) for d in guardado.get("descartes", []))


def buscar(libro: LibroVerificado, dir_cache: Path, clave_gb: str | None = None,
           cliente: httpx.Client | None = None) -> Path | None:
    """Ruta de una cubierta buena del libro, o None. Usa y rellena la caché; el «no hay» solo se
    guarda cuando ninguna fuente falló de forma pasajera."""
    carpeta = dir_cache / "cubiertas"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = _nombre(libro)
    meta = carpeta / f"{nombre}.json"
    if meta.exists() and not _buscar_de_nuevo(json.loads(meta.read_text(encoding="utf-8")), libro):
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


def _guardar(carpeta: Path, nombre: str, datos: bytes, origen: str, descartes: list[str]) -> Path:
    archivo = f"{nombre}.jpg"
    Image.open(BytesIO(datos)).convert("RGB").save(carpeta / archivo, quality=92)
    (carpeta / f"{nombre}.json").write_text(json.dumps({"archivo": archivo, "origen": origen, "descartes": descartes,
                                                         "criterio": CRITERIO}, ensure_ascii=False, indent=2), encoding="utf-8")
    return carpeta / archivo


def _casa_editorial(pedida: str, editorial: str | None) -> bool:
    from folio.verificacion_texto import normalizar
    p, e = normalizar(pedida), normalizar(editorial or "")
    return bool(p and e) and any(w in e for w in p.replace("/", " ").split() if len(w) > 3)


def de_edicion(libro: LibroVerificado, dir_cache: Path, editorial: str = "", isbn: str = "",
               clave_gb: str | None = None, cliente: httpx.Client | None = None):
    """La cubierta de una edición en castellano concreta, por su editorial o su ISBN (2/11, a petición del usuario en
    el chat: «pon la portada de la edición de Random House/Mondadori, en lugar de la extranjera»). Los datos de la
    edición salen de Open Library o Google Books, nunca del modelo. Devuelve (ruta o None, EdicionEspanola o None,
    nota)."""
    from folio.modelos import EdicionEspanola
    carpeta = dir_cache / "cubiertas"
    carpeta.mkdir(parents=True, exist_ok=True)
    descartes: list[str] = []
    isbn = re.sub(r"[^0-9Xx]", "", isbn)
    candidatas: list[tuple[str, str, dict]] = []
    with cliente or httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": AGENTE}) as c:
        if isbn:
            datos = {"isbn": isbn}
            try:
                r = c.get(OL_EDICION_ISBN.format(isbn=isbn))
                if r.status_code == 200:
                    e = r.json()
                    if e.get("languages") and not any(l.get("key") == "/languages/spa" for l in e["languages"]):
                        return None, None, f"El ISBN {isbn} no es de una edición en castellano según Open Library."
                    anio = re.search(r"\b(1[5-9]|20)\d\d\b", e.get("publish_date") or "")
                    datos |= {"editorial": ", ".join(e.get("publishers") or []) or None, "anio": anio.group(0) if anio else None,
                              "titulo": e.get("title")}
                else:
                    descartes.append(f"Open Library ({isbn}): HTTP {r.status_code}")
            except (httpx.HTTPError, ValueError) as e:
                descartes.append(f"Open Library ({isbn}): {type(e).__name__}")
            candidatas.append((f"Open Library ({EN_CASTELLANO}, ISBN {isbn})", OL_ISBN.format(isbn=isbn), datos))
        else:
            if libro.olid:
                for e in ediciones_en_castellano(c, libro.olid, descartes):
                    if _casa_editorial(editorial, e["editorial"]):
                        for id_ in e["covers"][:1]:
                            candidatas.append((f"Open Library ({EN_CASTELLANO}, {e['editorial']})", OL_ID.format(id=id_), e))
                        if e["isbn"]:
                            candidatas.append((f"Open Library ({EN_CASTELLANO}, ISBN {e['isbn']})", OL_ISBN.format(isbn=e["isbn"]), e))
            candidatas += [x for x in _gb_en_castellano(c, libro, clave_gb, descartes, editorial)
                           if _casa_editorial(editorial, x[2].get("editorial"))]
        for origen, url, datos in candidatas:
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
            ed = EdicionEspanola(titulo=datos.get("titulo"), editorial=datos.get("editorial"), anio=datos.get("anio"),
                                 isbn=datos.get("isbn"))
            nombre = (ed.isbn or f"{libro.olid or libro.titulo}-{editorial}").replace("/", "_").replace(" ", "_")
            return _guardar(carpeta, nombre, r.content, f"{origen}, elegida en el chat", descartes), ed, ""
    pista = "; ".join(descartes[:3])
    que = f"el ISBN {isbn}" if isbn else f"la editorial «{editorial}»"
    return None, None, (f"No encuentro una cubierta en castellano buena para {que} en Open Library ni Google Books"
                        + (f" ({pista})" if pista else "") + ". Si la tienes, súbela como material con su crédito.")
