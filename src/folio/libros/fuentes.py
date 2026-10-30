"""Clientes de las APIs bibliográficas (Open Library y Google Books).

Devuelven datos crudos normalizados; las decisiones (¿coincide?, ¿hay edición española?)
se toman en verificacion.py.
"""

from __future__ import annotations

import re
import time
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
    formato: str | None = None   # physical_format de Open Library («Paperback», «Audio CD»…)
    autores_claves: list[str] = field(default_factory=list)  # ids de autor de Open Library (OL…A)

    @property
    def es_audiolibro(self) -> bool:
        texto = f"{self.formato or ''} {self.editorial or ''}".lower()
        return any(p in texto for p in ("audio", "mp3", "cassette", "audible"))


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
    autores_claves: list[str] = field(default_factory=list)  # paralelo a `autores` (Open Library)


def _reintentar(peticion, intentos: int, espera_s: float) -> httpx.Response:
    """Repite la petición ante 429, 5xx o un corte de conexión, con espera creciente."""
    for intento in range(intentos):
        ultimo = intento == intentos - 1
        try:
            r = peticion()
        except httpx.TransportError:
            if ultimo:
                raise
        else:
            if r.status_code not in (429, 500, 502, 503) or ultimo:
                return r
        time.sleep(espera_s * 2 ** intento)
    raise AssertionError("inalcanzable")


def _traductores(e: dict) -> str | None:
    nombres = list(e.get("translated_by") or [])
    for c in e.get("contributors") or []:
        if isinstance(c, dict) and (c.get("role") or "").lower() in ("translator", "traductor", "traducción"):
            nombres.append(c.get("name", ""))
    nombres = [n for n in nombres if n]
    return ", ".join(nombres) or None


class OpenLibrary:
    BASE = "https://openlibrary.org"
    INTENTOS = 4  # corta conexiones de vez en cuando («Connection reset by peer»)
    ESPERA_S = 1.5  # se duplica en cada reintento

    def __init__(self, cliente: httpx.Client):
        self.c = cliente

    def _get(self, url: str, params: dict) -> httpx.Response:
        r = _reintentar(lambda: self.c.get(url, params=params), self.INTENTOS, self.ESPERA_S)
        r.raise_for_status()
        return r

    def buscar(self, titulo: str, autor: str, limite: int = 5) -> list[Obra]:
        r = self._get(f"{self.BASE}/search.json", {
            "q": titulo, "author": autor, "limit": limite,
            "fields": "key,title,subtitle,author_name,author_key,first_publish_year,language,edition_count",
        })
        obras = []
        for d in r.json().get("docs", []):
            olid = d["key"].split("/")[-1]
            obras.append(Obra(
                fuente="openlibrary", id=olid, titulo=d.get("title", ""),
                autores=d.get("author_name") or [], anio_primera_edicion=d.get("first_publish_year"),
                idiomas=d.get("language") or [], url=f"{self.BASE}{d['key']}",
                autores_claves=d.get("author_key") or [],
            ))
        return obras

    def ediciones(self, olid: str) -> list[Edicion]:
        r = self._get(f"{self.BASE}/works/{olid}/editions.json", {"limit": 1000})
        eds = []
        for e in r.json().get("entries", []):
            titulo = e.get("title", "")
            if e.get("subtitle"):
                titulo = f"{titulo.rstrip(' :')}: {e['subtitle'].lstrip(' :')}"
            eds.append(Edicion(
                titulo=titulo,
                editorial=(e.get("publishers") or [None])[0],
                anio=anio(e.get("publish_date")),
                isbn13=e.get("isbn_13") or [],
                idiomas=[l["key"].split("/")[-1] for l in e.get("languages", [])],
                traductor=_traductores(e),
                formato=e.get("physical_format"),
                autores_claves=[a["key"].split("/")[-1] for a in e.get("authors") or [] if a.get("key")],
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
    INTENTOS = 4  # da 503 y 429 a menudo
    ESPERA_S = 1.5  # se duplica en cada reintento

    def __init__(self, cliente: httpx.Client, clave: str):
        self.c = cliente
        self.clave = clave

    def _get(self, params: dict) -> httpx.Response:
        r = _reintentar(lambda: self.c.get(self.BASE, params=params), self.INTENTOS, self.ESPERA_S)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # El mensaje de httpx lleva la URL con la clave, y acaba en las notas del informe.
            raise httpx.HTTPStatusError(sin_clave(str(exc)), request=exc.request, response=exc.response) from None
        return r

    def buscar(self, titulo: str, autor: str, solo_espanol: bool = False) -> list[Obra]:
        params = {"maxResults": 20, "printType": "books", "country": self.PAIS, "key": self.clave}
        if solo_espanol:
            params["langRestrict"] = "es"
        # intitle: devuelve 0 resultados de forma errática; si pasa, se repite sin él.
        r = self._get({**params, "q": f'intitle:"{titulo}" inauthor:"{autor}"'})
        if not r.json().get("items"):
            r = self._get({**params, "q": f'{titulo} inauthor:"{autor}"'})
        return self._obras(r)

    def buscar_frase_es(self, titulo: str) -> list[Obra]:
        """Volúmenes en español que se parecen al título, sin filtrar por autor en la consulta.

        Sirve cuando el título español propuesto no es exacto («El viejo rey en su exilio» frente
        a «El viejo rey en el exilio»): Google Books tolera la diferencia y marca el idioma.
        """
        r = self._get({"maxResults": 20, "printType": "books", "country": self.PAIS, "key": self.clave,
                       "langRestrict": "es", "q": f'"{titulo}"'})
        return self._obras(r)

    @staticmethod
    def _obras(r: httpx.Response) -> list[Obra]:
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
