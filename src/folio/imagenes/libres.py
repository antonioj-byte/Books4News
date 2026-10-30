"""Imágenes libres de uso para las piezas, de Europeana y Wikimedia Commons, con la licencia
comprobada por API.

Europeana (museos y archivos europeos) declara los derechos de cada objeto con la URL de la
licencia (creativecommons.org/publicdomain/mark/1.0, …/zero/1.0, …). Commons, en los metadatos
del archivo. Commons limita mucho por IP a los clientes sin registrar; Europeana pide clave
(EUROPEANA_API_KEY; sin ella se usa la clave pública de demostración, solo para prototipos).

Criterio (prototipo de la dirección «Archivo»):
- Solo dominio público y CC0: se pueden recortar y virar a duotono sin obligaciones. CC BY se
  acepta con crédito visible. CC BY-SA no: la imagen se modifica y el carrusel tendría que
  publicarse con la misma licencia. Nada con NC/ND ni sin licencia declarada.
- Nada con restricciones declaradas en Commons (derechos de imagen, marcas, insignias).
- Ancho mínimo de 1080 px.
- Ni portadas de libros ni fotos de las personas de la noticia: la imagen acompaña la idea, no
  ilustra el suceso (y un archivo histórico no pone la cara de nadie a una noticia de hoy).

La licencia se lee de los metadatos de Commons (extmetadata), nunca se supone. Cada imagen fijada
para una pieza se guarda en data/cache/<fecha>/imagenes/ con sus metadatos y el crédito.
"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

API_COMMONS = "https://commons.wikimedia.org/w/api.php"
AGENTE = "FolioLateral/0.1 (prototipo editorial; https://github.com/antonioj-byte/Books4News)"
ANCHO_MINIMO = 1080
_ETIQUETAS = re.compile(r"<[^>]+>")


@dataclass
class ImagenLibre:
    archivo: str          # clave para fijarla: «commons:File:…» o «europeana:/id»
    pagina: str           # página del objeto en la fuente
    url: str              # miniatura de 1600 px de ancho
    ancho: int
    alto: int
    licencia: str         # tal como la declara Commons («Public domain», «CC0», «CC BY 4.0»…)
    licencia_url: str | None
    autor: str
    descripcion: str
    libre: bool           # cumple el criterio de arriba
    motivo: str           # por qué no, si no lo cumple
    local: str | None = None   # ruta del archivo descargado
    fuente: str = "Wikimedia Commons"
    institucion: str | None = None
    enfoque: tuple[int, int] = (50, 50)   # punto de interés en %, para recortar sin cortarlo

    @property
    def credito(self) -> str:
        autor = self.autor if self.autor and self.autor.lower() not in ("unknown", "desconocido") else "Autor desconocido"
        return " · ".join(x for x in (autor, self.institucion, self.licencia, self.fuente) if x)


def _texto(valor: str | None) -> str:
    return " ".join(html.unescape(_ETIQUETAS.sub(" ", valor or "")).split())


def licencia_libre(licencia: str) -> tuple[bool, str]:
    l = licencia.lower().replace("-", " ")
    if not l:
        return False, "sin licencia declarada"
    if "nc" in l.split() or "nd" in l.split():
        return False, f"licencia no libre ({licencia})"
    if "sa" in l.split():
        return False, f"compartir igual ({licencia}): la imagen se modifica"
    if l.startswith(("public domain", "pd", "cc0", "no restrictions")) or "dominio público" in l:
        return True, ""
    if l.startswith("cc by"):
        return True, ""
    return False, f"licencia no reconocida ({licencia})"


def _candidato(pagina: dict) -> ImagenLibre | None:
    info = (pagina.get("imageinfo") or [None])[0]
    if not info:
        return None
    meta = {k: (v or {}).get("value") for k, v in (info.get("extmetadata") or {}).items()}
    licencia = _texto(meta.get("LicenseShortName"))
    libre, motivo = licencia_libre(licencia)
    if libre and _texto(meta.get("Restrictions")):
        libre, motivo = False, f"restricciones: {_texto(meta.get('Restrictions'))}"
    if libre and info.get("width", 0) < ANCHO_MINIMO:
        libre, motivo = False, f"demasiado pequeña ({info.get('width')} px)"
    if libre and (meta.get("Copyrighted") or "").lower() == "true" and not licencia.lower().startswith("cc"):
        libre, motivo = False, "marcada con derechos y sin licencia CC"
    return ImagenLibre(
        archivo="commons:" + pagina["title"], pagina=info.get("descriptionurl", ""), url=info.get("thumburl") or info["url"],
        ancho=info.get("width", 0), alto=info.get("height", 0), licencia=licencia,
        licencia_url=_texto(meta.get("LicenseUrl")) or None, autor=_texto(meta.get("Artist"))[:120],
        descripcion=_texto(meta.get("ImageDescription"))[:300], libre=libre, motivo=motivo,
    )


def _consultar(params: dict, cliente: httpx.Client | None = None) -> dict:
    base = {"action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": 1600}
    c = cliente or httpx.Client(headers={"User-Agent": AGENTE}, timeout=30)
    try:
        for espera in (5, 15, 45, None):
            r = c.get(API_COMMONS, params=base | params)
            # Commons limita por IP y a veces responde 403 «robot policy» en vez de 429
            if r.status_code in (429, 403) and espera:
                time.sleep(float(r.headers.get("retry-after") or espera))
                continue
            r.raise_for_status()
            return r.json()
    finally:
        if cliente is None:
            c.close()


def buscar_commons(consulta: str, n: int = 12, cliente: httpx.Client | None = None) -> list[ImagenLibre]:
    """Fotos e ilustraciones de Commons para la consulta, con su licencia comprobada."""
    datos = _consultar({"generator": "search", "gsrsearch": f"filetype:bitmap {consulta}",
                        "gsrnamespace": 6, "gsrlimit": n}, cliente)
    paginas = sorted((datos.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return [c for c in (_candidato(p) for p in paginas) if c]


# --- Europeana -----------------------------------------------------------------------------------

API_EUROPEANA = "https://api.europeana.eu/record/v2/search.json"
_LICENCIAS_EUROPEANA = {
    "creativecommons.org/publicdomain/mark/": "Dominio público",
    "creativecommons.org/publicdomain/zero/": "CC0",
    "creativecommons.org/licenses/by/": "CC BY",
}


def licencia_europeana(url: str) -> tuple[str, bool, str]:
    """URL de derechos de Europeana → (nombre, libre, motivo)."""
    u = url.split("://", 1)[-1]
    for prefijo, nombre in _LICENCIAS_EUROPEANA.items():
        if u.startswith(prefijo):
            version = u[len(prefijo):].strip("/")
            return f"{nombre} {version}".strip() if nombre == "CC BY" else nombre, True, ""
    return url, False, f"licencia no aceptada ({url})"


def _clave_europeana() -> str:
    import os

    return (os.getenv("EUROPEANA_API_KEY") or "").strip() or "api2demo"


_IIIF = re.compile(r"/full/(?:\d+,\d*|,\d+|!\d+,\d+)/0/default\.(jpg|png)$")


def mayor_resolucion(url: str) -> str:
    """Muchas instituciones sirven por IIIF una versión pequeña (…/full/512,/0/default.jpg): se pide
    una de 1600 px de ancho, que es lo que necesita el carrusel."""
    return _IIIF.sub(r"/full/1600,/0/default.\1", url)


def _de_europeana(item: dict) -> ImagenLibre | None:
    url = mayor_resolucion((item.get("edmIsShownBy") or [""])[0])
    rights = (item.get("rights") or [""])[0]
    if not url or not rights:
        return None
    licencia, libre, motivo = licencia_europeana(rights)
    titulo = (item.get("title") or [""])[0]
    return ImagenLibre(
        archivo="europeana:" + item["id"], pagina=item.get("guid", "").split("?")[0], url=url, ancho=0, alto=0,
        licencia=licencia, licencia_url=rights, autor=_texto((item.get("dcCreator") or [""])[0])[:120],
        descripcion=_texto(titulo)[:300], libre=libre, motivo=motivo, fuente="Europeana",
        institucion=(item.get("dataProvider") or [None])[0],
    )


def _consultar_europeana(params: dict) -> list[dict]:
    with httpx.Client(headers={"User-Agent": AGENTE}, timeout=30) as c:
        r = c.get(API_EUROPEANA, params=[("wskey", _clave_europeana()), ("media", "true"),
                                          ("qf", "TYPE:IMAGE"), *params.items()])
        r.raise_for_status()
        return r.json().get("items") or []


def buscar_europeana(consulta: str, n: int = 12) -> list[ImagenLibre]:
    """Imágenes de Europeana en dominio público o CC0 (la licencia se vuelve a comprobar aquí)."""
    items = _consultar_europeana({"query": consulta, "rows": n, "reusability": "open"})
    return [c for c in (_de_europeana(i) for i in items) if c]


def buscar(consulta: str, n: int = 12, fuente: str = "europeana") -> list[ImagenLibre]:
    return buscar_europeana(consulta, n) if fuente == "europeana" else buscar_commons(consulta, n)


def ficha(clave: str, cliente: httpx.Client | None = None) -> ImagenLibre:
    """La imagen por su clave («europeana:/id» o «commons:File:…»), con la licencia recién leída."""
    if clave.startswith("europeana:"):
        ident = clave.removeprefix("europeana:")
        items = _consultar_europeana({"query": f'europeana_id:"{ident}"', "rows": 1})
        if not items:
            raise ValueError(f"No está en Europeana: {ident}")
        return _de_europeana(items[0])
    archivo = clave.removeprefix("commons:")
    titulo = archivo if archivo.startswith("File:") else f"File:{archivo}"
    datos = _consultar({"titles": titulo}, cliente)
    for p in (datos.get("query") or {}).get("pages", {}).values():
        c = _candidato(p)
        if c:
            return c
    raise ValueError(f"No está en Commons: {titulo}")


def dir_imagenes(dir_cache_fecha: Path) -> Path:
    return dir_cache_fecha / "imagenes"


def fijar(imagen: ImagenLibre, pieza_id: str, dir_cache_fecha: Path) -> Path:
    """Descarga la imagen para la pieza y guarda sus metadatos. Rechaza las que no son libres."""
    if not imagen.libre:
        raise ValueError(f"{imagen.archivo}: {imagen.motivo}")
    carpeta = dir_imagenes(dir_cache_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    ext = Path(imagen.url.split("?")[0]).suffix.lower() or ".jpg"
    destino = carpeta / f"{pieza_id}{ext}"
    with httpx.Client(headers={"User-Agent": AGENTE}, timeout=60, follow_redirects=True) as c:
        r = c.get(imagen.url)
        r.raise_for_status()
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(r.content)) as im:
        imagen.ancho, imagen.alto = im.size
        if im.width < ANCHO_MINIMO:
            raise ValueError(f"{imagen.archivo}: demasiado pequeña ({im.width} px)")
        if ext not in (".jpg", ".jpeg", ".png"):
            ext = ".jpg"
            destino = carpeta / f"{pieza_id}{ext}"
            im.convert("RGB").save(destino, quality=92)
        else:
            destino.write_bytes(r.content)
    imagen.local = destino.name
    guardar_metadatos(imagen, pieza_id, dir_cache_fecha)
    return destino


def guardar_metadatos(imagen: ImagenLibre, pieza_id: str, dir_cache_fecha: Path) -> None:
    carpeta = dir_imagenes(dir_cache_fecha)
    (carpeta / f"{pieza_id}.json").write_text(json.dumps(asdict(imagen), ensure_ascii=False, indent=2), encoding="utf-8")


def olvidar(pieza_id: str, dir_cache_fecha: Path) -> None:
    """Quita la imagen fijada de la pieza (antes de que el director de arte elija otra)."""
    for ruta in dir_imagenes(dir_cache_fecha).glob(f"{pieza_id}.*"):
        ruta.unlink()


def de_pieza(pieza_id: str, dir_cache_fecha: Path) -> ImagenLibre | None:
    ruta = dir_imagenes(dir_cache_fecha) / f"{pieza_id}.json"
    if not ruta.exists():
        return None
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["enfoque"] = tuple(datos.get("enfoque") or (50, 50))
    return ImagenLibre(**datos)
