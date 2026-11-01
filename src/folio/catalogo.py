"""Catálogo de las editoriales independientes (formato «recomendado», 1/11, a petición del usuario).

Las editoriales están en config/editoriales_independientes.yaml (las del Back to the Book 2026 y algunas
independientes de referencia). Sus novedades se leen en todostuslibros.com, el portal de las librerías de
CEGAL: una página de novedades por editorial (título, autor, mes) y una ficha por libro con la sinopsis,
la fecha de publicación, el ISBN, la traducción y, a menudo, un apartado «CRÍTICA» con citas de prensa.

Cortesía con el portal: una petición cada `pausa_s` segundos (su robots.txt pide 1 s), las novedades de cada
editorial se refrescan cada `refresco_dias` y unas pocas editoriales al día, las fichas se guardan para
siempre y ante 403 o 429 se para la lectura del día (regla de la casa: no se esquivan bloqueos).

Cada libro candidato se convierte en una `Historia` del carril «catalogo» (`catalogo-<isbn>`) cuyos textos
son la sinopsis y, aparte, la crítica: el guionista puede citar la crítica solo si la frase está allí letra
por letra (`FuenteNoticia.critica`).
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import yaml
from pydantic import Field

from folio.modelos import Articulo, BaseModel, EdicionEspanola, FuenteNoticia, Historia, LibroVerificado

log = logging.getLogger(__name__)

PREFIJO = "catalogo-"
BASE = "https://www.todostuslibros.com"
MEDIO = "Todos tus libros"
_MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9,
          "oct": 10, "nov": 11, "dic": 12}


class BloqueoCatalogo(Exception):
    """El portal respondió 403 o 429: se para la lectura del catálogo en esta ejecución."""


class Editorial(BaseModel):
    nombre: str
    web: str | None = None
    origen: str = ""
    todostuslibros: str | None = None
    excluir: str | None = None
    referencia: bool = False         # una de las 75 de referencia (2/11): se intercalan con las demás cada día


class Novedad(BaseModel):
    titulo: str
    autor: str
    editorial: str
    mes: str                          # «2026-10»
    url: str
    isbn: str


class Ficha(BaseModel):
    url: str
    titulo: str
    autores: list[str]
    traductores: list[str] = Field(default_factory=list)
    editorial: str
    isbn: str
    fecha: str | None = None          # «2026-10-19»
    sinopsis: str = ""
    critica: str = ""


# --- Lectura del HTML ------------------------------------------------------------

def _texto(fragmento: str) -> str:
    t = re.sub(r"<br\s*/?>|</p>", "\n", fragmento)
    t = html_mod.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(" ".join(l.split()) for l in t.splitlines() if l.strip())


def _mes(badge: str) -> str | None:
    """«oct. 2026» → «2026-10»."""
    m = re.match(r"\s*([a-z]+)\.?\s+(\d{4})", unicodedata.normalize("NFKD", badge.lower()).encode("ascii", "ignore").decode())
    mes = (_MESES.get(m.group(1)) or _MESES.get(m.group(1)[:3])) if m else None
    return f"{m.group(2)}-{mes:02d}" if mes else None


def leer_novedades(html: str) -> list[Novedad]:
    """Los libros de una página de novedades de una editorial."""
    salida = []
    for art in re.findall(r'<article class="book[^"]*">(.*?)</article>', html, re.S):
        url = re.search(r'<p class="title">\s*<a href="([^"]+)"', art)
        titulo = re.search(r'<p class="title">\s*<a[^>]*>(.*?)</a>', art, re.S)
        autor = re.search(r'<p class="author">(.*?)</p>', art, re.S)
        editorial = re.search(r'<p class="data">\s*<a[^>]*>(.*?)</a>', art, re.S)
        badge = re.search(r'publication-date">(.*?)</span>', art, re.S)
        isbn = re.search(r'name="isbn" value="([\d-]+)"', art)
        mes = _mes(_texto(badge.group(1))) if badge else None
        if not (url and titulo and isbn and mes):
            continue
        salida.append(Novedad(titulo=_texto(titulo.group(1)), autor=_texto(autor.group(1)) if autor else "",
                              editorial=_texto(editorial.group(1)) if editorial else "", mes=mes,
                              url=url.group(1), isbn=isbn.group(1).replace("-", "")))
    return salida


def _dato(html: str, etiqueta: str) -> str | None:
    m = re.search(rf"<dt>\s*{etiqueta}\s*:?\s*</dt>\s*<dd>(.*?)</dd>", html, re.S)
    return _texto(m.group(1)) if m else None


def _creadores(html: str, etiqueta: str) -> list[str]:
    m = re.search(rf"<dt>\s*{etiqueta}:\s*</dt>\s*<dd>(.*?)</dd>", html, re.S)
    return [_texto(s) for s in re.findall(r"<span>(.*?)</span>", m.group(1), re.S)] if m else []


def leer_ficha(html: str, url: str) -> Ficha | None:
    """La ficha de un libro: datos técnicos, sinopsis y, separada, la crítica (lo que sigue a «CRÍTICA»)."""
    titulo = re.search(r'<h1 class="title">(.*?)</h1>', html, re.S)
    isbn = _dato(html, "ISBN")
    if not titulo or not isbn:
        return None
    m = re.search(r'id="collapseSynopsis"[^>]*>(.*?)</div>', html, re.S)
    descripcion = _texto(m.group(1)) if m else ""
    partes = re.split(r"^\s*CR[IÍ]TICA\s*:?\s*$", descripcion, maxsplit=1, flags=re.M)
    fecha = _dato(html, "Fecha publicación")
    if fecha and re.fullmatch(r"\d{2}-\d{2}-\d{4}", fecha):
        d, mth, y = fecha.split("-")
        fecha = f"{y}-{mth}-{d}"
    return Ficha(url=url, titulo=_texto(titulo.group(1)), autores=_creadores(html, "Autoría"),
                 traductores=_creadores(html, "Traducción"), editorial=_dato(html, "Editorial") or "",
                 isbn=isbn.replace("-", ""), fecha=fecha, sinopsis=partes[0].strip(),
                 critica=partes[1].strip() if len(partes) > 1 else "")


# --- Acceso al portal, con caché --------------------------------------------------

def _slug(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t.replace("&", " ")).strip("-")


_GENERICAS = {"editorial", "editoriales", "ediciones", "edicions", "editores", "editora", "libros", "s", "l", "sl", "sa", "u",
              "sll", "slu", "de", "del", "la", "el", "los", "las", "y", "e"}


def ruta_que_casa(nombre: str, rutas: list[str]) -> str | None:
    """De los enlaces a editoriales de una página, el que corresponde a `nombre`: todas las palabras con contenido
    del nombre están en la ruta. Si el portal no encuentra la editorial enseña otras (el 2/11 «Pre-Textos»
    acababa en «plaza-janes»), y entonces no hay ninguna."""
    clave = {w for w in _slug(nombre).split("-") if w and w not in _GENERICAS}
    for r in dict.fromkeys(rutas):
        palabras = set(r.rsplit("_", 1)[0].split("-"))
        if clave and clave <= palabras:
            return r
    return None


class Catalogo:
    def __init__(self, cfg, cliente: httpx.Client | None = None, hoy: date | None = None):
        self.cfg = cfg
        self.p = cfg.pipeline.catalogo
        self.dir = cfg.dir_datos / "cache" / "catalogo"
        self.cliente = cliente or httpx.Client(timeout=20, follow_redirects=True,
                                               headers={"User-Agent": "Mozilla/5.0 (compatible; FolioLateral/0.1)"})
        self.hoy = hoy or date.today()
        self._ultima = 0.0
        self.peticiones = 0
        self.avisos: list[str] = []

    def _get(self, url: str) -> str | None:
        espera = self.p.pausa_s - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()
        self.peticiones += 1
        r = self.cliente.get(url)
        if r.status_code in (403, 429):
            raise BloqueoCatalogo(f"todostuslibros respondió {r.status_code} en {url}")
        return r.text if r.status_code == 200 else None

    def _leer_json(self, ruta: Path):
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _guardar_json(self, ruta: Path, datos) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def ruta_editorial(self, e: Editorial) -> str | None:
        """«impedimenta_79803»: de la configuración o, una vez, de la página /editorial/<nombre> (se guarda)."""
        if e.todostuslibros:
            return e.todostuslibros
        # v2 (2/11): la v1 guardaba rutas de otras editoriales cuando el portal no encontraba el nombre
        rutas_f = self.dir / "editoriales-v2.json"
        rutas = self._leer_json(rutas_f) or {}
        if e.nombre in rutas:
            return rutas[e.nombre]
        html = self._get(f"{BASE}/editorial/{_slug(e.nombre)}")
        rutas[e.nombre] = ruta_que_casa(e.nombre, re.findall(r"/editoriales/([a-z0-9-]+_\d+)", html or ""))
        self._guardar_json(rutas_f, rutas)
        return rutas[e.nombre]

    def novedades(self, e: Editorial, refrescar: bool) -> list[Novedad]:
        ruta = self.ruta_editorial(e)
        if not ruta:
            return []
        f = self.dir / "novedades" / f"{ruta}.json"
        guardado = self._leer_json(f)
        if guardado and not refrescar:
            return [Novedad.model_validate(x) for x in guardado["libros"]]
        html = self._get(f"{BASE}/editoriales/{ruta}/novedades")
        libros = leer_novedades(html or "")
        self._guardar_json(f, {"leido": self.hoy.isoformat(), "libros": [l.model_dump() for l in libros]})
        return libros

    def caducada(self, e: Editorial) -> bool:
        ruta = (self._leer_json(self.dir / "editoriales-v2.json") or {}).get(e.nombre, e.todostuslibros)
        if not ruta:
            return True
        g = self._leer_json(self.dir / "novedades" / f"{ruta}.json")
        return not g or (self.hoy - date.fromisoformat(g["leido"])).days >= self.p.refresco_dias

    def ficha(self, url: str, isbn: str) -> Ficha | None:
        f = self.dir / "fichas" / f"{isbn}.json"
        guardada = self._leer_json(f)
        if guardada:
            return Ficha.model_validate(guardada)
        html = self._get(url)
        ficha = leer_ficha(html or "", url)
        if ficha:
            self._guardar_json(f, ficha.model_dump())
        return ficha


def editoriales(raiz: Path) -> list[Editorial]:
    r = raiz / "config" / "editoriales_independientes.yaml"
    if not r.exists():
        return []
    return [e for e in (Editorial.model_validate(x) for x in yaml.safe_load(r.read_text(encoding="utf-8")) or [])
            if not e.excluir]


def meses_atras(hoy: date, mes: str) -> int:
    y, m = map(int, mes.split("-"))
    return (hoy.year - y) * 12 + hoy.month - m


def _orden_del_dia(nombres: list[str], hoy: date) -> list[str]:
    """Las editoriales en un orden que cambia cada día: así todas se leen y se proponen por turnos."""
    return sorted(nombres, key=lambda n: hashlib.sha1(f"{hoy.isoformat()}:{n}".encode()).hexdigest())


def candidatos(cfg, hoy: date, ya_usado=lambda titulo, autor: False, cat: Catalogo | None = None) -> tuple[list[Historia], list[str]]:
    """Los libros del catálogo que pasan al jefe de cultura: novedades de los últimos `meses` meses, como mucho
    `max_por_editorial` de cada editorial, por turnos entre editoriales, con su ficha leída. Devuelve también
    los avisos (bloqueos, editoriales que no se encuentran)."""
    p = cfg.pipeline.catalogo
    cat = cat or Catalogo(cfg, hoy=hoy)
    eds = {e.nombre: e for e in editoriales(cfg.raiz)}
    # Una de referencia, una de las demás, y así: las 75 de referencia salen más, sin dejar fuera al resto
    ref = _orden_del_dia([n for n, e in eds.items() if e.referencia], hoy)
    resto = _orden_del_dia([n for n, e in eds.items() if not e.referencia], hoy)
    orden = [n for par in zip(ref, resto) for n in par] + ref[len(resto):] + resto[len(ref):]
    salida: list[Historia] = []
    refrescadas = 0
    try:
        for nombre in orden:
            if len(salida) >= p.candidatos:
                break
            e = eds[nombre]
            refrescar = cat.caducada(e) and refrescadas < p.editoriales_por_dia
            refrescadas += refrescar
            recientes = [n for n in cat.novedades(e, refrescar) if 0 <= meses_atras(hoy, n.mes) <= p.meses]
            elegidos = 0
            for n in recientes:
                if elegidos >= p.max_por_editorial:
                    break
                if ya_usado(n.titulo, n.autor):
                    continue
                ficha = cat.ficha(n.url, n.isbn)
                if not ficha or not ficha.autores or len(ficha.sinopsis) < 200:
                    continue
                salida.append(historia(ficha, e))
                elegidos += 1
    except BloqueoCatalogo as exc:
        cat.avisos.append(f"Catálogo: {exc}; se sigue con {len(salida)} candidatos")
    except httpx.HTTPError as exc:
        cat.avisos.append(f"Catálogo: error de red ({type(exc).__name__}); se sigue con {len(salida)} candidatos")
    return salida, cat.avisos


def historia(f: Ficha, e: Editorial | None = None) -> Historia:
    """El libro como historia del carril «catalogo». El resumen lleva si tiene crítica: el jefe lo tiene en cuenta."""
    resumen = f.sinopsis[:420] + ("…" if len(f.sinopsis) > 420 else "")
    art = Articulo(id=f"{PREFIJO}{f.isbn}", medio=MEDIO, url=f.url, titulo=f"{f.titulo}, de {', '.join(f.autores)}",
                   entradilla=resumen, idioma="es", acceso="abierto", carril="catalogo",
                   publicado_en=datetime.fromisoformat(f.fecha).replace(tzinfo=timezone.utc) if f.fecha else None)
    return Historia(id=PREFIJO + f.isbn, articulos=[art], medios=[f.editorial or (e.nombre if e else "")], n_medios=1,
                    titular_es=f"{f.titulo}, de {', '.join(f.autores)} ({f.editorial}, {f.fecha or 's. f.'})",
                    resumen_es=resumen + (" [Con crítica de prensa en la ficha]" if f.critica else " [Sin crítica en la ficha]"),
                    seccion="cultura", sobre_libros=True, carril="catalogo")


def es_del_catalogo(historia_id: str) -> bool:
    return historia_id.startswith(PREFIJO)


def ficha_guardada(cfg, historia_id: str) -> Ficha | None:
    f = cfg.dir_datos / "cache" / "catalogo" / "fichas" / f"{historia_id.removeprefix(PREFIJO)}.json"
    try:
        return Ficha.model_validate_json(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def textos(f: Ficha) -> list[tuple[FuenteNoticia, str]]:
    """Los textos del guion: la ficha (sinopsis y datos) y, aparte, la crítica, que es lo único citable."""
    datos = (f"{f.titulo}, de {', '.join(f.autores)}. {f.editorial}, {f.fecha or 'fecha no consta'}."
             + (f" Traducción de {', '.join(f.traductores)}." if f.traductores else "") + f"\n\n{f.sinopsis}")
    salida = [(FuenteNoticia(medio=MEDIO, titulo=f.titulo, url=f.url, acceso="abierto", texto_completo=True), datos)]
    if f.critica:
        salida.append((FuenteNoticia(medio=f"{MEDIO} · crítica", titulo=f"Crítica de {f.titulo}", url=f.url + "#critica",
                                     acceso="abierto", texto_completo=True, critica=True), f.critica))
    return salida


def libro_de_ficha(f: Ficha) -> LibroVerificado:
    """La ficha como libro verificado cuando Open Library y Google Books no lo tienen todavía (novedad reciente):
    es el catálogo de las librerías, con su ISBN y la edición española que está a la venta."""
    return LibroVerificado(
        titulo=f.titulo, titulo_propuesto=f.titulo, autores=f.autores, edicion_es="si",
        edicion_es_detalle=EdicionEspanola(titulo=f.titulo, editorial=f.editorial, anio=(f.fecha or "")[:4] or None,
                                           isbn=f.isbn, traductor=", ".join(f.traductores) or None, pais="España"),
        isbn13=[f.isbn], fuentes_verificacion=["todostuslibros"], url_ficha=f.url, confianza="media",
        notas=["Verificado en el catálogo de las librerías (todostuslibros.com): novedad aún sin ficha en Open Library"],
    )
