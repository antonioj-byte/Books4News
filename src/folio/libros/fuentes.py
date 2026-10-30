"""Clientes de las APIs bibliográficas (Open Library y Google Books).

Devuelven datos crudos normalizados; las decisiones (¿coincide?, ¿hay edición española?)
se toman en verificacion.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

# Prefijos ISBN-13 (978-…) de países hispanohablantes. 84 = España.
_GRUPOS_HISPANOS = {
    "97884": "España", "978950": "Argentina", "978987": "Argentina", "978956": "Chile",
    "978958": "Colombia", "978968": "México", "978970": "México", "978607": "México",
    "978959": "Cuba", "978980": "Venezuela", "9789972": "Perú", "978612": "Perú",
    "9789974": "Uruguay", "9789978": "Ecuador", "9789942": "Ecuador", "9789968": "Costa Rica",
    "9789962": "Panamá", "9789945": "República Dominicana",
}

IDIOMAS = {
    "spa": "español", "eng": "inglés", "fre": "francés", "ger": "alemán", "ita": "italiano",
    "por": "portugués", "rus": "ruso", "jpn": "japonés", "chi": "chino", "cat": "catalán",
    "dut": "neerlandés", "swe": "sueco", "nor": "noruego", "dan": "danés", "pol": "polaco",
    "heb": "hebreo", "ara": "árabe", "kor": "coreano", "tur": "turco", "gre": "griego",
    "hun": "húngaro", "cze": "checo", "fin": "finés", "lat": "latín",
    "es": "español", "en": "inglés", "fr": "francés", "de": "alemán", "it": "italiano", "pt": "portugués",
}


def pais_isbn(isbn: str | None) -> str | None:
    if not isbn:
        return None
    isbn = re.sub(r"[^0-9X]", "", isbn)
    for prefijo, pais in sorted(_GRUPOS_HISPANOS.items(), key=lambda kv: -len(kv[0])):
        if isbn.startswith(prefijo):
            return pais
    return None


def anio(fecha: str | None) -> str | None:
    m = re.search(r"(1[5-9]\d\d|20\d\d)", fecha or "")
    return m.group(1) if m else None


@dataclass
class Edicion:
    titulo: str
    editorial: str | None
    anio: str | None
    isbn13: list[str]
    idiomas: list[str]           # códigos (spa, eng…); puede estar vacío
    traductor: str | None = None


@dataclass
class Obra:
    fuente: str                  # openlibrary | googlebooks
    id: str
    titulo: str
    autores: list[str]
    anio_primera_edicion: int | None
    idiomas: list[str] = field(default_factory=list)
    ediciones: list[Edicion] = field(default_factory=list)
    url: str | None = None


class OpenLibrary:
    BASE = "https://openlibrary.org"

    def __init__(self, cliente: httpx.Client):
        self.c = cliente

    def buscar(self, titulo: str, autor: str, limite: int = 5) -> list[Obra]:
        r = self.c.get(f"{self.BASE}/search.json", params={
            "q": titulo, "author": autor, "limit": limite,
            "fields": "key,title,subtitle,author_name,first_publish_year,language,edition_count",
        })
        r.raise_for_status()
        obras = []
        for d in r.json().get("docs", []):
            olid = d["key"].split("/")[-1]
            obras.append(Obra(
                fuente="openlibrary", id=olid, titulo=d.get("title", ""),
                autores=d.get("author_name") or [], anio_primera_edicion=d.get("first_publish_year"),
                idiomas=d.get("language") or [], url=f"{self.BASE}{d['key']}",
            ))
        return obras

    def ediciones(self, olid: str) -> list[Edicion]:
        r = self.c.get(f"{self.BASE}/works/{olid}/editions.json", params={"limit": 1000})
        r.raise_for_status()
        eds = []
        for e in r.json().get("entries", []):
            traductor = None
            if e.get("translated_by"):
                traductor = ", ".join(e["translated_by"])
            titulo = e.get("title", "")
            if e.get("subtitle"):
                titulo = f"{titulo.rstrip(' :')}: {e['subtitle'].lstrip(' :')}"
            eds.append(Edicion(
                titulo=titulo,
                editorial=(e.get("publishers") or [None])[0],
                anio=anio(e.get("publish_date")),
                isbn13=e.get("isbn_13") or [],
                idiomas=[l["key"].split("/")[-1] for l in e.get("languages", [])],
                traductor=traductor,
            ))
        return eds


_CLAVE_EN_URL = re.compile(r"(key=)[^&\s'\"]+")


def sin_clave(texto: str) -> str:
    """Oculta el parámetro key= de una URL o de un mensaje de error."""
    return _CLAVE_EN_URL.sub(r"\1***", texto)


class GoogleBooks:
    BASE = "https://www.googleapis.com/books/v1/volumes"
    # Sin país, Google Books responde 403 «unknownLocation» desde IPs que no sabe geolocalizar.
    PAIS = "ES"
    INTENTOS = 2  # da 503 y 429 esporádicos

    def __init__(self, cliente: httpx.Client, clave: str):
        self.c = cliente
        self.clave = clave

    def buscar(self, titulo: str, autor: str, solo_espanol: bool = False) -> list[Obra]:
        params = {
            "q": f'intitle:"{titulo}" inauthor:"{autor}"',
            "maxResults": 20, "printType": "books", "country": self.PAIS, "key": self.clave,
        }
        if solo_espanol:
            params["langRestrict"] = "es"
        for intento in range(self.INTENTOS):
            r = self.c.get(self.BASE, params=params)
            if r.status_code not in (429, 500, 502, 503) or intento == self.INTENTOS - 1:
                break
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # El mensaje de httpx lleva la URL con la clave, y acaba en las notas del informe.
            raise httpx.HTTPStatusError(sin_clave(str(exc)), request=exc.request, response=exc.response) from None
        obras = []
        for it in r.json().get("items", []):
            v = it.get("volumeInfo", {})
            titulo_v = v.get("title", "")
            isbns = [i["identifier"] for i in v.get("industryIdentifiers", []) if i.get("type") == "ISBN_13"]
            ed = Edicion(
                titulo=f"{titulo_v}: {v['subtitle']}" if v.get("subtitle") else titulo_v,
                editorial=v.get("publisher"), anio=anio(v.get("publishedDate")),
                isbn13=isbns, idiomas=[v["language"]] if v.get("language") else [],
            )
            obras.append(Obra(
                fuente="googlebooks", id=it["id"], titulo=titulo_v, autores=v.get("authors") or [],
                anio_primera_edicion=None, idiomas=ed.idiomas, ediciones=[ed],
                url=v.get("infoLink"),
            ))
        return obras
