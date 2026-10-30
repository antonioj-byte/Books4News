"""Verificación de libros contra Open Library y Google Books.

Un libro se da por verificado solo si una fuente devuelve una obra cuyo autor coincide
(por apellido) y cuyo título, o el de alguna de sus ediciones, coincide con el propuesto.
Los datos de edición salen siempre de la fuente; lo que no está, queda en None.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

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


@dataclass
class _Consulta:
    """Lo que se va sabiendo de un libro mientras se verifica."""
    cand: LibroCandidato
    ol: tuple[Obra, Edicion | None] | None = None      # obra de Open Library y edición que coincide
    gb_todos: list[Obra] = field(default_factory=list)  # Google Books: volúmenes que coinciden
    gb_es: list[Obra] = field(default_factory=list)     # Google Books: volúmenes en español del autor
    errores: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)

    @property
    def obra(self) -> Obra | None:
        return self.ol[0] if self.ol else None

    @property
    def fuentes(self) -> list[str]:
        return (["openlibrary"] if self.ol else []) + (["googlebooks"] if self.gb_todos else [])


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
        """Ficha verificada de un libro propuesto. Flujo:

        1. Buscarlo en Open Library y en Google Books, con el título propuesto y, si hace falta, el
           original. Si ninguna fuente lo encuentra, NoVerificado (y si fallaron, se dice).
        2. Reunir las ediciones en español: Open Library (idioma de la edición, o ISBN hispano y
           título exacto), Google Books (idioma «es») y, si no hay ninguna y el título propuesto es
           una traducción, un título español aproximado en Google Books.
        3. Decidir la edición española: «si» con su ficha (completando la editorial por ISBN), «no»
           solo si las dos fuentes encuentran la obra sin errores y ninguna la tiene, o
           «desconocido».
        4. Con Open Library: separar autores y traductores, y datos de la primera edición (de la
           obra original si la encontrada es una traducción).
        5. Componer la ficha. Las notas explican cada decisión, en ese orden.
        """
        q = self._consultar(cand)
        ediciones_es = self._ediciones_es(q)
        edicion_es, detalle, ed_es = self._edicion_espanola(q, ediciones_es)
        if not q.ol:
            return self._ficha_solo_google_books(q, edicion_es, detalle)
        obra = q.obra
        autores = self._autores(q, detalle, ed_es)
        idioma_orig, editorial_orig, anio_orig = self._primera_edicion(q)
        q.notas.extend(q.errores)
        return LibroVerificado(
            titulo=obra.titulo, titulo_propuesto=cand.titulo, autores=autores,
            anio_primera_edicion=anio_orig,
            idioma_original=idioma_orig, editorial_original=editorial_orig,
            edicion_es=edicion_es, edicion_es_detalle=detalle,
            olid=obra.id, google_id=q.gb_todos[0].id if q.gb_todos else None,
            isbn13=sorted({i for e in obra.ediciones for i in e.isbn13})[:20],
            fuentes_verificacion=q.fuentes, url_ficha=obra.url,
            confianza="alta" if (q.gb_todos or len(obra.ediciones) >= 2) else "media",
            notas=q.notas,
        )

    # --- Pasos de verificar() ---------------------------------------------------

    def _consultar(self, cand: LibroCandidato) -> _Consulta:
        """Paso 1: la obra en las dos fuentes. Un error de una fuente no impide usar la otra."""
        q = _Consulta(cand)
        try:
            q.ol = self._openlibrary(cand)
        except httpx.HTTPError as exc:
            q.errores.append(f"Open Library: {exc}")
        try:
            q.gb_todos, q.gb_es = self._googlebooks(cand)
        except httpx.HTTPError as exc:
            q.errores.append(f"Google Books: {exc}")
        if not q.ol and not q.gb_todos:
            if q.errores:
                raise NoVerificado("no se pudo consultar: " + "; ".join(q.errores))
            raise NoVerificado("ninguna fuente bibliográfica lo encuentra con ese título y autor")
        return q

    def _ediciones_es(self, q: _Consulta) -> list[tuple[Edicion, str]]:
        """Paso 2: ediciones en español, con cómo se sabe que lo son."""
        ediciones_es: list[tuple[Edicion, str]] = []
        if q.ol:
            for ed in q.obra.ediciones:
                ok, como = _es_espanola(ed, q.cand.titulo)
                if ok:
                    ediciones_es.append((ed, f"Open Library ({como})"))
            if not ediciones_es and "spa" in q.obra.idiomas:
                q.notas.append("Open Library indica ediciones en español pero sin datos de ninguna")
        for o in q.gb_es:
            ed = o.ediciones[0]
            if ed.idiomas == ["es"]:
                ediciones_es.append((ed, "Google Books (idioma de la edición)"))
        titulo_obra = q.obra.titulo if q.ol else q.gb_todos[0].titulo
        if not ediciones_es and self.gb and not titulos_coinciden(q.cand.titulo, titulo_obra, umbral=1.0):
            # El título propuesto es una traducción y no aparece tal cual: puede que la edición
            # española exista con un título algo distinto («en el exilio» por «en su exilio»).
            try:
                ediciones_es += self._edicion_es_aproximada(q.cand)
            except httpx.HTTPError as exc:
                q.errores.append(f"Google Books: {exc}")
        return ediciones_es

    def _edicion_espanola(self, q: _Consulta, ediciones_es: list[tuple[Edicion, str]]
                          ) -> tuple[str, EdicionEspanola | None, Edicion | None]:
        """Paso 3: («si» | «no» | «desconocido», ficha de la edición española, edición elegida)."""
        if ediciones_es:
            ed_es, como = _mejor_edicion_es(ediciones_es)
            detalle, _ = _ficha_es(ed_es, como)
            q.notas.append(f"Edición española según {como}")
            if not detalle.editorial and detalle.isbn:
                # Google Books no siempre trae la editorial; Open Library la tiene por ISBN.
                try:
                    detalle.editorial = self.ol.editorial_por_isbn(detalle.isbn)
                except httpx.HTTPError as exc:
                    q.notas.append(f"No se pudo completar la editorial por ISBN: {exc}")
                if detalle.editorial:
                    q.notas.append("Editorial de la edición española completada por ISBN en Open Library")
            return "si", detalle, ed_es
        if q.ol and q.gb_todos and not q.errores and "spa" not in q.obra.idiomas:
            # Ambas fuentes consultadas sin errores, las dos encuentran la obra y ninguna tiene
            # edición española. Si Google Books no encuentra ni la obra, su silencio no prueba
            # nada: sus búsquedas intitle: devuelven 0 resultados de forma errática.
            return "no", None, None
        if not self.gb:
            q.notas.append("Sin clave de Google Books: solo se ha consultado Open Library")
        return "desconocido", None, None

    def _autores(self, q: _Consulta, detalle: EdicionEspanola | None, ed_es: Edicion | None) -> list[str]:
        """Paso 4a: autores sin los traductores que Open Library pone como coautores. Si un traductor
        solo figura en la edición española elegida, pasa a ser su traductor."""
        autores, otros = _separar_autores(q.cand, q.obra)
        if otros:
            traductores_es = [n for n, k in otros.items() if ed_es is not None and k and k in ed_es.autores_claves]
            if detalle and not detalle.traductor and traductores_es:
                detalle.traductor = ", ".join(traductores_es)
                q.notas.append(f"Traductor deducido: {detalle.traductor} figura en Open Library como "
                               "coautor solo de la edición española")
            resto = [n for n in otros if n not in traductores_es]
            if resto:
                q.notas.append(f"Open Library lo da como coautor, pero no es el autor propuesto "
                               f"(probablemente traductor): {', '.join(resto)}")
        return autores

    def _primera_edicion(self, q: _Consulta) -> tuple[str | None, str | None, int | None]:
        """Paso 4b: idioma, editorial y año de la primera edición."""
        cand = q.cand
        datos = _original(q.obra, cand.idioma_original)
        original = self._obra_original(cand, q.obra, q.notas)
        if not original:
            return datos
        # La obra encontrada es una traducción: sus fechas son las de la traducción.
        de_la_original = (_original_en_su_idioma(original, cand.idioma_original) if cand.idioma_original
                          else _original(original))
        if de_la_original and de_la_original[2]:
            q.notas.append(f"Primera edición tomada de la obra original «{original.titulo}» ({original.url}): "
                           "la que encuentra Open Library con el título propuesto es una traducción")
            return de_la_original
        q.notas.append(f"La obra original «{original.titulo}» ({original.url}) no tiene ediciones fechadas "
                       f"en {cand.idioma_original or 'su lengua'}: la primera edición no consta")
        return None, None, None

    def _ficha_solo_google_books(self, q: _Consulta, edicion_es: str, detalle: EdicionEspanola | None) -> LibroVerificado:
        """Paso 5 cuando Open Library no la encuentra: ficha con lo que da Google Books."""
        q.notas.extend(q.errores)
        o = q.gb_todos[0]
        return LibroVerificado(
            titulo=o.titulo, titulo_propuesto=q.cand.titulo, autores=o.autores,
            anio_primera_edicion=None, edicion_es=edicion_es, edicion_es_detalle=detalle,
            google_id=o.id, isbn13=o.ediciones[0].isbn13, fuentes_verificacion=["googlebooks"],
            url_ficha=o.url, confianza="media", notas=q.notas + ["Solo encontrado en Google Books"],
        )
