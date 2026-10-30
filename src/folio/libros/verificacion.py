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
    """Prefiere idioma confirmado, luego con editorial, de España, con ISBN y más reciente."""
    def orden(par):
        ed, como = par
        isbn = ed.isbn13[0] if ed.isbn13 else None
        return ("idioma" in como, bool(ed.editorial), pais_isbn(isbn) == "España", bool(isbn), ed.anio or "")
    return max(eds, key=orden)


def _ficha_es(ed: Edicion, como: str) -> EdicionEspanola:
    isbn = ed.isbn13[0] if ed.isbn13 else None
    return EdicionEspanola(
        titulo=ed.titulo, editorial=ed.editorial, anio=ed.anio, isbn=isbn,
        traductor=ed.traductor, pais=pais_isbn(isbn),
    ), como


def _codigos_idioma(nombre: str | None) -> set[str]:
    """Códigos (spa, es…) de un idioma dado por su nombre en español («polaco» → {"pol"})."""
    n = (nombre or "").strip().lower()
    return {codigo for codigo, nombre_es in IDIOMAS.items() if nombre_es == n}


def _original_en_su_idioma(obra: Obra, idioma_original: str | None) -> tuple[str, str | None, int] | None:
    """Edición más antigua en la lengua original (la propone el jefe de cultura).

    Open Library tiene fechas erróneas (una traducción de Knopf «de 1900»), así que el año de
    la obra no basta. El idioma del jefe solo filtra; los datos salen de la edición.
    """
    codigos = _codigos_idioma(idioma_original)
    ediciones = [e for e in obra.ediciones if e.anio and not e.es_audiolibro and codigos & set(e.idiomas)]
    if not ediciones:
        return None
    e = min(ediciones, key=lambda e: e.anio)
    return IDIOMAS.get(e.idiomas[0], e.idiomas[0]), e.editorial, int(e.anio)


def _original(obra: Obra, idioma_original: str | None = None) -> tuple[str | None, str | None, int | None]:
    """Idioma, editorial y año de la primera edición.

    Primero, la edición más antigua en la lengua original. Si no hay, el año de la obra y una
    edición con idioma conocido de ese mismo año.
    """
    en_su_idioma = _original_en_su_idioma(obra, idioma_original)
    if en_su_idioma:
        return en_su_idioma
    if not obra.anio_primera_edicion:
        return None, None, None
    candidatas = [e for e in obra.ediciones
                  if e.anio == str(obra.anio_primera_edicion) and e.idiomas and not e.es_audiolibro]
    if not candidatas:
        return None, None, obra.anio_primera_edicion
    e = candidatas[0]
    return IDIOMAS.get(e.idiomas[0], e.idiomas[0]), e.editorial, obra.anio_primera_edicion


def _separar_autores(cand: LibroCandidato, obra: Obra) -> tuple[list[str], dict[str, str]]:
    """(autores, otros nombres → id OL). Open Library pone a menudo al traductor como coautor."""
    principales = [n for n in obra.autores if autor_coincide(cand.autor, [n])]
    if not principales:
        return obra.autores, {}
    claves = dict(zip(obra.autores, obra.autores_claves)) if len(obra.autores_claves) == len(obra.autores) else {}
    otros = {n: claves.get(n, "") for n in obra.autores if n not in principales}
    return principales, otros


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

    def _edicion_es_aproximada(self, cand: LibroCandidato) -> list[tuple[Edicion, str]]:
        """Ediciones en español con un título parecido al propuesto, según Google Books.

        Solo Google Books: marca el idioma de cada volumen y así no se confunde una edición
        española con una catalana o gallega de título casi igual (Open Library no siempre lo da).
        """
        out = []
        for o in self.gb.buscar_frase_es(cand.titulo):
            ed = o.ediciones[0]
            if (ed.idiomas == ["es"] and autor_coincide(cand.autor, o.autores)
                    and titulos_coinciden(o.titulo, cand.titulo, umbral=0.85)):
                out.append((ed, f"Google Books (idioma de la edición; título aproximado: «{o.titulo}»)"))
        return out

    def _obra_original(self, cand: LibroCandidato, obra: Obra, notas: list[str]) -> Obra | None:
        """Si la obra encontrada es una traducción con ficha propia, busca la obra original."""
        if not cand.titulo_original or titulos_coinciden(cand.titulo_original, obra.titulo):
            return None
        try:
            for o in self.ol.buscar(cand.titulo_original, cand.autor):
                if (o.id != obra.id and autor_coincide(cand.autor, o.autores)
                        and titulos_coinciden(cand.titulo_original, o.titulo)):
                    o.ediciones = self.ol.ediciones(o.id)
                    return o
        except httpx.HTTPError as exc:
            notas.append(f"No se pudo buscar la obra original en Open Library: {exc}")
        return None

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

        titulo_obra = ol[0].titulo if ol else gb_todos[0].titulo
        if not ediciones_es and self.gb and not titulos_coinciden(cand.titulo, titulo_obra, umbral=1.0):
            # El título propuesto es una traducción y no aparece tal cual: puede que la edición
            # española exista con un título algo distinto («en el exilio» por «en su exilio»).
            try:
                ediciones_es += self._edicion_es_aproximada(cand)
            except httpx.HTTPError as exc:
                errores.append(f"Google Books: {exc}")

        detalle = None
        ed_es = None
        if ediciones_es:
            ed_es, como = _mejor_edicion_es(ediciones_es)
            detalle, _ = _ficha_es(ed_es, como)
            edicion_es = "si"
            notas.append(f"Edición española según {como}")
            if not detalle.editorial and detalle.isbn:
                # Google Books no siempre trae la editorial; Open Library la tiene por ISBN.
                try:
                    detalle.editorial = self.ol.editorial_por_isbn(detalle.isbn)
                except httpx.HTTPError as exc:
                    notas.append(f"No se pudo completar la editorial por ISBN: {exc}")
                if detalle.editorial:
                    notas.append(f"Editorial de la edición española completada por ISBN en Open Library")
        elif ol and gb_todos and not errores and "spa" not in ol[0].idiomas:
            # Ambas fuentes consultadas sin errores, las dos encuentran la obra y ninguna tiene
            # edición española. Si Google Books no encuentra ni la obra, su silencio no prueba
            # nada: sus búsquedas intitle: devuelven 0 resultados de forma errática.
            edicion_es = "no"
        else:
            edicion_es = "desconocido"
            if not self.gb:
                notas.append("Sin clave de Google Books: solo se ha consultado Open Library")

        if ol:
            obra, _ = ol
            autores, otros = _separar_autores(cand, obra)
            if otros:
                traductores_es = [n for n, k in otros.items() if ed_es is not None and k and k in ed_es.autores_claves]
                if detalle and not detalle.traductor and traductores_es:
                    detalle.traductor = ", ".join(traductores_es)
                    notas.append(f"Traductor deducido: {detalle.traductor} figura en Open Library como "
                                 "coautor solo de la edición española")
                resto = [n for n in otros if n not in traductores_es]
                if resto:
                    notas.append(f"Open Library lo da como coautor, pero no es el autor propuesto "
                                 f"(probablemente traductor): {', '.join(resto)}")
            idioma_orig, editorial_orig, anio_orig = _original(obra, cand.idioma_original)
            original = self._obra_original(cand, obra, notas)
            if original:
                # La obra encontrada es una traducción: sus fechas son las de la traducción.
                datos = (_original_en_su_idioma(original, cand.idioma_original) if cand.idioma_original
                         else _original(original))
                if datos and datos[2]:
                    idioma_orig, editorial_orig, anio_orig = datos
                    notas.append(f"Primera edición tomada de la obra original «{original.titulo}» ({original.url}): "
                                 "la que encuentra Open Library con el título propuesto es una traducción")
                else:
                    idioma_orig, editorial_orig, anio_orig = None, None, None
                    notas.append(f"La obra original «{original.titulo}» ({original.url}) no tiene ediciones fechadas "
                                 f"en {cand.idioma_original or 'su lengua'}: la primera edición no consta")
            if errores:
                notas.extend(errores)
            isbns = sorted({i for e in obra.ediciones for i in e.isbn13})[:20]
            return LibroVerificado(
                titulo=obra.titulo, titulo_propuesto=cand.titulo, autores=autores,
                anio_primera_edicion=anio_orig,
                idioma_original=idioma_orig, editorial_original=editorial_orig,
                edicion_es=edicion_es, edicion_es_detalle=detalle,
                olid=obra.id, google_id=gb_todos[0].id if gb_todos else None, isbn13=isbns,
                fuentes_verificacion=fuentes, url_ficha=obra.url,
                confianza="alta" if (gb_todos or len(obra.ediciones) >= 2) else "media",
                notas=notas,
            )
        if errores:
            notas.extend(errores)
        # Solo Google Books
        o = gb_todos[0]
        return LibroVerificado(
            titulo=o.titulo, titulo_propuesto=cand.titulo, autores=o.autores,
            anio_primera_edicion=None, edicion_es=edicion_es, edicion_es_detalle=detalle,
            google_id=o.id, isbn13=o.ediciones[0].isbn13, fuentes_verificacion=["googlebooks"],
            url_ficha=o.url, confianza="media", notas=notas + ["Solo encontrado en Google Books"],
        )
