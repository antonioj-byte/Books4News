"""Verificación de libros contra Open Library y Google Books.

Un libro se da por verificado solo si una fuente devuelve una obra cuyo autor coincide
(por apellido) y cuyo título, o el de alguna de sus ediciones, coincide con el propuesto.
Los datos de edición salen siempre de la fuente; lo que no está, queda en None.
"""

from __future__ import annotations

import logging

import httpx

from folio.config import Config
from folio.libros.fuentes import IDIOMAS, Edicion, GoogleBooks, Obra, OpenLibrary, pais_isbn
from folio.modelos import EdicionEspanola, LibroCandidato, LibroVerificado
from folio.verificacion_texto import autor_coincide, titulos_coinciden

log = logging.getLogger(__name__)


class NoVerificado(Exception):
    """El libro no se pudo verificar. `motivo` explica por qué."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def _es_espanola(ed: Edicion, titulo_propuesto: str) -> tuple[bool, str]:
    """¿Es una edición en español? Devuelve (sí/no, cómo se sabe)."""
    if ed.idiomas:
        return (any(i in ("spa", "es") for i in ed.idiomas), "idioma de la edición")
    # Sin idioma: ISBN de un país hispanohablante y título igual al propuesto (que el jefe
    # da en español). El título evita confundirla con ediciones en catalán, gallego o euskera.
    # Coincidencia estricta: «Xerusalén» o «La pesta» no valen por «Jerusalén» o «La peste».
    if any(pais_isbn(i) for i in ed.isbn13) and titulos_coinciden(ed.titulo, titulo_propuesto, umbral=1.0):
        return True, "ISBN hispano y título en español"
    return False, ""


def _mejor_edicion_es(eds: list[tuple[Edicion, str]]) -> tuple[Edicion, str]:
    """Prefiere idioma confirmado, luego España, con ISBN y más reciente."""
    def orden(par):
        ed, como = par
        isbn = ed.isbn13[0] if ed.isbn13 else None
        return ("idioma" in como, pais_isbn(isbn) == "España", bool(isbn), ed.anio or "")
    return max(eds, key=orden)


def _ficha_es(ed: Edicion, como: str) -> EdicionEspanola:
    isbn = ed.isbn13[0] if ed.isbn13 else None
    return EdicionEspanola(
        titulo=ed.titulo, editorial=ed.editorial, anio=ed.anio, isbn=isbn,
        traductor=ed.traductor, pais=pais_isbn(isbn),
    ), como


def _original(obra: Obra) -> tuple[str | None, str | None]:
    """Idioma y editorial de la primera edición, solo si una edición con idioma conocido
    es del mismo año que la primera edición de la obra."""
    if not obra.anio_primera_edicion:
        return None, None
    candidatas = [e for e in obra.ediciones
                  if e.anio == str(obra.anio_primera_edicion) and e.idiomas and not e.es_audiolibro]
    if not candidatas:
        return None, None
    e = candidatas[0]
    return IDIOMAS.get(e.idiomas[0], e.idiomas[0]), e.editorial


def _titulos(cand: LibroCandidato) -> list[str]:
    """Título propuesto y, si es distinto, el original: Open Library no siempre tiene el español."""
    t = [cand.titulo]
    if cand.titulo_original and not titulos_coinciden(cand.titulo_original, cand.titulo, umbral=1.0):
        t.append(cand.titulo_original)
    return t


class Verificador:
    def __init__(self, cfg: Config, cliente: httpx.Client | None = None):
        self.cfg = cfg
        self.c = cliente or httpx.Client(
            timeout=30, follow_redirects=True, headers={"User-Agent": cfg.user_agent},
        )
        self.ol = OpenLibrary(self.c)
        self.gb = GoogleBooks(self.c, cfg.google_books_api_key) if cfg.google_books_api_key else None

    def _openlibrary(self, cand: LibroCandidato) -> tuple[Obra, Edicion | None] | None:
        """Busca la obra en Open Library. Devuelve (obra con ediciones, edición que coincide)."""
        titulos = _titulos(cand)
        for titulo in titulos:
            for obra in self.ol.buscar(titulo, cand.autor):
                if not autor_coincide(cand.autor, obra.autores):
                    continue
                obra.ediciones = self.ol.ediciones(obra.id)
                if any(titulos_coinciden(t, obra.titulo) for t in titulos):
                    return obra, None
                for ed in obra.ediciones:
                    if any(titulos_coinciden(t, ed.titulo) for t in titulos):
                        return obra, ed
        return None

    def _googlebooks(self, cand: LibroCandidato) -> tuple[list[Obra], list[Obra]]:
        """(volúmenes que coinciden en cualquier idioma, volúmenes en español del mismo autor)."""
        if not self.gb:
            return [], []
        titulos = _titulos(cand)
        todos: list[Obra] = []
        for titulo in titulos:
            todos = [o for o in self.gb.buscar(titulo, cand.autor)
                     if autor_coincide(cand.autor, o.autores) and any(titulos_coinciden(t, o.titulo) for t in titulos)]
            if todos:
                break
        es = [o for o in self.gb.buscar(cand.titulo, cand.autor, solo_espanol=True)
              if autor_coincide(cand.autor, o.autores)]
        return todos, es

    def verificar(self, cand: LibroCandidato) -> LibroVerificado:
        notas: list[str] = []
        errores: list[str] = []
        ol = gb_todos = gb_es = None
        try:
            ol = self._openlibrary(cand)
        except httpx.HTTPError as exc:
            errores.append(f"Open Library: {exc}")
        try:
            gb_todos, gb_es = self._googlebooks(cand)
        except httpx.HTTPError as exc:
            errores.append(f"Google Books: {exc}")

        if not ol and not gb_todos:
            if errores:
                raise NoVerificado("no se pudo consultar: " + "; ".join(errores))
            raise NoVerificado("ninguna fuente bibliográfica lo encuentra con ese título y autor")

        fuentes: list[str] = []
        ediciones_es: list[tuple[Edicion, str]] = []
        if ol:
            obra, _ = ol
            fuentes.append("openlibrary")
            for ed in obra.ediciones:
                ok, como = _es_espanola(ed, cand.titulo)
                if ok:
                    ediciones_es.append((ed, f"Open Library ({como})"))
            if not ediciones_es and "spa" in obra.idiomas:
                notas.append("Open Library indica ediciones en español pero sin datos de ninguna")
        if gb_todos:
            fuentes.append("googlebooks")
        for o in gb_es or []:
            ed = o.ediciones[0]
            if ed.idiomas == ["es"]:
                ediciones_es.append((ed, "Google Books (idioma de la edición)"))

        detalle = None
        if ediciones_es:
            ed, como = _mejor_edicion_es(ediciones_es)
            detalle, _ = _ficha_es(ed, como)
            edicion_es = "si"
            notas.append(f"Edición española según {como}")
        elif ol and gb_todos and not errores and "spa" not in ol[0].idiomas:
            # Ambas fuentes consultadas sin errores, las dos encuentran la obra y ninguna tiene
            # edición española. Si Google Books no encuentra ni la obra, su silencio no prueba
            # nada: sus búsquedas intitle: devuelven 0 resultados de forma errática.
            edicion_es = "no"
        else:
            edicion_es = "desconocido"
            if not self.gb:
                notas.append("Sin clave de Google Books: solo se ha consultado Open Library")
        if errores:
            notas.extend(errores)

        if ol:
            obra, _ = ol
            idioma_orig, editorial_orig = _original(obra)
            isbns = sorted({i for e in obra.ediciones for i in e.isbn13})[:20]
            return LibroVerificado(
                titulo=obra.titulo, titulo_propuesto=cand.titulo, autores=obra.autores,
                anio_primera_edicion=obra.anio_primera_edicion,
                idioma_original=idioma_orig, editorial_original=editorial_orig,
                edicion_es=edicion_es, edicion_es_detalle=detalle,
                olid=obra.id, google_id=gb_todos[0].id if gb_todos else None, isbn13=isbns,
                fuentes_verificacion=fuentes, url_ficha=obra.url,
                confianza="alta" if (gb_todos or len(obra.ediciones) >= 2) else "media",
                notas=notas,
            )
        # Solo Google Books
        o = gb_todos[0]
        return LibroVerificado(
            titulo=o.titulo, titulo_propuesto=cand.titulo, autores=o.autores,
            anio_primera_edicion=None, edicion_es=edicion_es, edicion_es_detalle=detalle,
            google_id=o.id, isbn13=o.ediciones[0].isbn13, fuentes_verificacion=["googlebooks"],
            url_ficha=o.url, confianza="media", notas=notas + ["Solo encontrado en Google Books"],
        )
