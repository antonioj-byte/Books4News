"""Cajón de curiosidades (formato «curiosidad», 1/11, a petición del usuario).

Historias del mundo del libro sin percha de actualidad, de las que se encontrarían en la balda de
historia del libro de una buena librería (config/cajon_curiosidades.yaml). Cada una se convierte en una
`Historia` del carril «cajon» con sus fuentes como artículos: a partir de ahí sigue el mismo camino que
una noticia (textos congelados, guion, comprobación de hechos contra las fuentes, arte y render).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from folio.modelos import Articulo, BaseModel, Historia

PREFIJO = "cajon-"


class FuenteCajon(BaseModel):
    medio: str
    url: str
    titulo: str


class Curiosidad(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    titular: str
    resumen: str
    protagonista: str = ""          # la persona real de la historia, si la hay (su retrato va en la portada)
    fuentes: list[FuenteCajon] = Field(min_length=1)
    añadida: str | None = None      # las de la nevera: el día que se encontraron
    origen: str = "repositorio"     # repositorio (config/) o busqueda (la nevera, folio.nevera)


def ruta(raiz: Path) -> Path:
    return raiz / "config" / "cajon_curiosidades.yaml"


def _leer(r: Path) -> list[Curiosidad]:
    if not r.exists():
        return []
    return [Curiosidad.model_validate(x) for x in yaml.safe_load(r.read_text(encoding="utf-8")) or []]


def cargar(raiz: Path, nevera: Path | None = None) -> list[Curiosidad]:
    """Las historias del cajón: las del repositorio y, detrás, las de la nevera (data/cajon_nevera.yaml), que
    añade cada día folio.nevera. Un id repetido es un error."""
    cajon = _leer(ruta(raiz)) + (_leer(nevera) if nevera else [])
    ids = [c.id for c in cajon]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        raise ValueError(f"cajón de historias editoriales: ids repetidos: {', '.join(sorted(repetidos))}")
    return cajon


def es_del_cajon(historia_id: str) -> bool:
    return historia_id.startswith(PREFIJO)


def historia(c: Curiosidad) -> Historia:
    """La curiosidad como historia: una fuente por artículo, en abierto (se descargan como las noticias)."""
    articulos = [Articulo(id=f"{PREFIJO}{c.id}-{i}", medio=f.medio, url=f.url, titulo=f.titulo, entradilla=c.resumen,
                          idioma="es", acceso="abierto", carril="cajon")
                 for i, f in enumerate(c.fuentes, 1)]
    medios = list(dict.fromkeys(f.medio for f in c.fuentes))
    return Historia(id=PREFIJO + c.id, articulos=articulos, medios=medios, n_medios=len(medios),
                    titular_es=c.titular, resumen_es=c.resumen + (f" (protagonista: {c.protagonista})" if c.protagonista else ""), seccion="cultura", sobre_libros=True, carril="cajon")


def disponibles(raiz: Path, usadas: set[str], nevera: Path | None = None) -> list[Historia]:
    """Las del cajón que no se han usado en los últimos días (`usadas`: ids sin prefijo), en su orden."""
    return [historia(c) for c in cargar(raiz, nevera) if c.id not in usadas]
