"""Ingesta del libro: EPUB, PDF o TXT troceado por capítulos, con la página de cada fragmento cuando el formato la
trae (las marcas de página de EPUB 3, las etiquetas de página del PDF). Y la comprobación de que un pasaje es literal.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

MIN_CAPITULO = 200          # caracteres: por debajo, portadillas, créditos y similares
PAGINAS_POR_TRAMO = 15      # PDF sin índice: tramos de este número de páginas


@dataclass
class Capitulo:
    n: int
    titulo: str
    texto: str
    paginas: list[list] = field(default_factory=list)   # [[desplazamiento en `texto`, «64»], …] en orden

    def pagina_en(self, desplazamiento: int) -> str | None:
        actual = None
        for d, p in self.paginas:
            if d > desplazamiento:
                break
            actual = p
        return actual

    @property
    def rango(self) -> str:
        if not self.paginas:
            return ""
        a, b = self.paginas[0][1], self.paginas[-1][1]
        return f"pág. {a}" if a == b else f"págs. {a}–{b}"


@dataclass
class Libro:
    titulo: str
    autor: str
    formato: str
    capitulos: list[Capitulo]

    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta: Path) -> "Libro":
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return cls(d["titulo"], d["autor"], d["formato"], [Capitulo(**c) for c in d["capitulos"]])

    @property
    def caracteres(self) -> int:
        return sum(len(c.texto) for c in self.capitulos)

    def capitulo(self, n: int) -> Capitulo | None:
        return next((c for c in self.capitulos if c.n == n), None)


# ── Lectura ───────────────────────────────────────────────────────────────────────────────────────────────────────

def leer(ruta: Path, titulo: str = "", autor: str = "") -> Libro:
    ext = ruta.suffix.lower()
    if ext == ".epub":
        libro = _epub(ruta)
    elif ext == ".pdf":
        libro = _pdf(ruta)
    elif ext in (".txt", ".md"):
        libro = _txt(ruta)
    else:
        raise ValueError(f"Formato no admitido: {ext}. Sube un EPUB, un PDF o un TXT.")
    libro.titulo = titulo.strip() or libro.titulo or ruta.stem
    libro.autor = autor.strip() or libro.autor
    libro.capitulos = [c for c in libro.capitulos if len(c.texto) >= MIN_CAPITULO]
    for i, c in enumerate(libro.capitulos, 1):
        c.n = i
    if not libro.capitulos:
        raise ValueError("No se ha podido sacar texto del libro (¿un PDF escaneado sin capa de texto?).")
    return libro


def _limpiar(texto: str) -> str:
    texto = texto.replace("\xa0", " ").replace("­", "")
    lineas = [re.sub(r"[ \t]+", " ", l).strip() for l in texto.splitlines()]
    texto = "\n".join(lineas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


_MARCA = "\u0000PAG:{}\u0000"
_RE_MARCA = re.compile("\u0000PAG:([^\u0000]*)\u0000")


def _sacar_marcas(texto: str) -> tuple[str, list[list]]:
    """Quita las marcas de página del texto y devuelve dónde estaba cada una."""
    paginas, partes, pos, quitado = [], [], 0, 0
    for m in _RE_MARCA.finditer(texto):
        partes.append(texto[pos:m.start()])
        paginas.append([m.start() - quitado, m.group(1)])
        quitado += m.end() - m.start()
        pos = m.end()
    partes.append(texto[pos:])
    return "".join(partes), paginas


def _epub(ruta: Path) -> Libro:
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub

    libro = epub.read_epub(str(ruta), options={"ignore_ncx": False})
    meta = lambda k: (libro.get_metadata("DC", k) or [[""]])[0][0] or ""
    titulos_toc: dict[str, str] = {}

    def recorrer(toc):
        for x in toc:
            if isinstance(x, tuple):
                seccion, hijos = x
                if getattr(seccion, "href", None):
                    titulos_toc.setdefault(seccion.href.split("#")[0], seccion.title)
                recorrer(hijos)
            elif getattr(x, "href", None):
                titulos_toc.setdefault(x.href.split("#")[0], x.title)
    recorrer(libro.toc)

    capitulos = []
    for idref, _ in libro.spine:
        item = libro.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        sopa = BeautifulSoup(item.get_content(), "html.parser")
        for t in sopa(["script", "style"]):
            t.decompose()
        for marca in sopa.find_all(lambda t: t.get("epub:type") == "pagebreak" or t.get("role") == "doc-pagebreak"):
            num = marca.get("title") or marca.get("aria-label") or re.sub(r"\D", "", marca.get("id", "")) or marca.get_text(strip=True)
            marca.replace_with(_MARCA.format(str(num).strip()))
        cuerpo = sopa.body or sopa
        texto, paginas = _sacar_marcas(_limpiar(cuerpo.get_text("\n")))
        titulo = titulos_toc.get(item.get_name()) or ""
        if not titulo:
            cab = cuerpo.find(["h1", "h2", "h3"])
            titulo = cab.get_text(" ", strip=True) if cab else ""
        capitulos.append(Capitulo(0, titulo[:120] or f"Sección {len(capitulos) + 1}", texto, paginas))
    return Libro(meta("title"), meta("creator"), "epub", capitulos)


def _pdf(ruta: Path) -> Libro:
    from pypdf import PdfReader

    lector = PdfReader(str(ruta))
    try:
        etiquetas = list(lector.page_labels)
    except Exception:
        etiquetas = []
    paginas = [(_limpiar(p.extract_text() or ""), etiquetas[i] if i < len(etiquetas) else str(i + 1))
               for i, p in enumerate(lector.pages)]
    inicios: list[tuple[int, str]] = []
    try:
        for e in lector.outline:
            if isinstance(e, list):
                continue
            inicios.append((lector.get_destination_page_number(e), e.title))
    except Exception:
        inicios = []
    inicios = sorted({p: t for p, t in inicios}.items())
    info = lector.metadata or {}
    if len(inicios) < 2:
        por_indice = _capitulos_por_indice(paginas)
        if por_indice:
            return Libro(str(info.get("/Title") or ""), str(info.get("/Author") or ""), "pdf", por_indice)
    if len(inicios) < 2:
        inicios = [(i, f"Páginas {paginas[i][1]}–{paginas[min(i + PAGINAS_POR_TRAMO, len(paginas)) - 1][1]}")
                   for i in range(0, len(paginas), PAGINAS_POR_TRAMO)]
    elif inicios[0][0] > 0:
        inicios.insert(0, (0, "Preliminares"))
    capitulos = []
    for k, (ini, titulo) in enumerate(inicios):
        fin = inicios[k + 1][0] if k + 1 < len(inicios) else len(paginas)
        texto, marcas = "", []
        for texto_pag, etiqueta in paginas[ini:fin]:
            marcas.append([len(texto), etiqueta])
            texto += texto_pag + "\n\n"
        capitulos.append(Capitulo(0, str(titulo)[:120], texto.strip(), marcas))
    return Libro(str(info.get("/Title") or ""), str(info.get("/Author") or ""), "pdf", capitulos)


def _titulos_del_indice(paginas: list[tuple[str, str]]) -> tuple[int, dict[str, str]] | None:
    """Si hay una página «Índice» al principio, sus líneas son los títulos de los capítulos."""
    lineas = lambda t: [l.strip() for l in t.splitlines() if l.strip()]
    k = next((i for i, (t, _) in enumerate(paginas[:15]) if lineas(t) and normalizar(lineas(t)[0]) in ("indice", "sumario", "contenido")), None)
    if k is None:
        return None
    titulos = {}
    for l in lineas(paginas[k][0])[1:]:
        n = re.sub(r"\s\d+$", "", normalizar(l)).replace(" ", "")   # sin número de página ni espacios («El V alle»)
        if n and len(l) < 120 and not n.isdigit():
            titulos[n] = re.sub(r"[\s.]+\d+$", "", l)
    return (k, titulos) if len(titulos) >= 2 else None


def _capitulos_por_indice(paginas: list[tuple[str, str]]) -> list[Capitulo]:
    """PDF sin marcadores: los capítulos empiezan donde una línea suelta (o dos seguidas) es un título del índice."""
    r = _titulos_del_indice(paginas)
    if r is None:
        return []
    k, pendientes = r
    capitulos = [Capitulo(0, "Preliminares", "", [])]
    for texto_pag, etiqueta in paginas[k + 1:]:
        ls = texto_pag.splitlines()
        actual = capitulos[-1]
        actual.paginas.append([len(actual.texto), etiqueta])
        i = 0
        while i < len(ls):
            encontrado = None
            for ancho in (1, 2):
                n = normalizar(" ".join(ls[i:i + ancho])).replace(" ", "")
                if n and n in pendientes:
                    encontrado = (ancho, pendientes.pop(n))
                    break
            if encontrado:
                ancho, titulo = encontrado
                actual = Capitulo(0, titulo, "", [[0, etiqueta]])
                capitulos.append(actual)
                i += ancho
                continue
            actual.texto += ls[i] + "\n"
            i += 1
        actual.texto += "\n"
    for c in capitulos:
        c.texto = c.texto.strip()
    return capitulos if len(capitulos) > 2 else []


_RE_CABECERA = re.compile(r"^(cap[ií]tulo\s+\S+.*|parte\s+\S+.*|[IVXLC]{1,6}\.?|\d{1,3}\.?|pr[oó]logo|ep[ií]logo|introducci[oó]n)$",
                          re.IGNORECASE)


def _txt(ruta: Path) -> Libro:
    texto = _limpiar(ruta.read_text(encoding="utf-8", errors="replace"))
    lineas = texto.split("\n")
    capitulos, titulo, actual = [], "Inicio", []
    for i, l in enumerate(lineas):
        aislada = (i == 0 or not lineas[i - 1].strip()) and (i + 1 >= len(lineas) or not lineas[i + 1].strip())
        if l and len(l) < 80 and aislada and _RE_CABECERA.match(l):
            if "\n".join(actual).strip():
                capitulos.append(Capitulo(0, titulo, "\n".join(actual).strip()))
            titulo, actual = l, []
        else:
            actual.append(l)
    if "\n".join(actual).strip():
        capitulos.append(Capitulo(0, titulo, "\n".join(actual).strip()))
    return Libro("", "", "txt", capitulos)


# ── Lo que lee el modelo ──────────────────────────────────────────────────────────────────────────────────────────

def texto_para_modelo(libro: Libro) -> str:
    """El libro entero, con la cabecera de cada capítulo. Las páginas van en la cabecera del capítulo, no dentro del
    texto, para que un pasaje copiado del texto sea literal."""
    partes = [f'<libro titulo="{libro.titulo}" autor="{libro.autor}">']
    for c in libro.capitulos:
        rango = f" · {c.rango}" if c.rango else ""
        partes.append(f'<capitulo n="{c.n}" titulo="{c.titulo}"{rango and f" paginas={chr(34)}{c.rango}{chr(34)}"}>\n{c.texto}\n</capitulo>')
    partes.append("</libro>")
    return "\n\n".join(partes)


# ── Citas literales ───────────────────────────────────────────────────────────────────────────────────────────────

def _normalizar_con_mapa(texto: str) -> tuple[str, list[int]]:
    """Minúsculas, sin tildes ni signos, espacios colapsados; `mapa[i]` es la posición en `texto` del carácter i."""
    salida, mapa = [], []
    for i, ch in enumerate(texto):
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)).lower()
        for b in base:
            if b.isalnum():
                salida.append(b)
                mapa.append(i)
            elif salida and salida[-1] != " ":
                salida.append(" ")
                mapa.append(i)
    return "".join(salida).strip(), mapa


def normalizar(texto: str) -> str:
    return _normalizar_con_mapa(texto)[0]


@dataclass
class Referencia:
    capitulo: int
    titulo: str
    pagina: str | None

    @property
    def texto(self) -> str:
        return f"cap. {self.capitulo}" + (f", pág. {self.pagina}" if self.pagina else "")


def buscar_literal(libro: Libro, pasaje: str) -> Referencia | None:
    """Dónde está `pasaje` letra por letra en el libro (salvo mayúsculas, tildes y signos), o None."""
    # Sin espacios: la extracción de texto de los PDF parte palabras por el interletrado («El V alle»)
    aguja = normalizar(pasaje.replace("…", " ").replace("...", " ")).replace(" ", "")
    if len(aguja) < 8:
        return None
    for c in libro.capitulos:
        norm, mapa = _normalizar_con_mapa(c.texto)
        sin = [(ch, m) for ch, m in zip(norm, mapa) if ch != " "]
        norm, mapa = "".join(ch for ch, _ in sin), [m for _, m in sin]
        pos = norm.find(aguja)
        if pos >= 0:
            return Referencia(c.n, c.titulo, c.pagina_en(mapa[pos] if pos < len(mapa) else 0))
    return None


def palabras(texto: str) -> int:
    return len(re.findall(r"\w+(?:[’'-]\w+)*", texto or ""))
