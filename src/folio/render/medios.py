"""Las imágenes de una diapositiva tal como las carga el navegador: la imagen de archivo, el retrato
del autor, las cubiertas y la ilustración, con la URL que corresponda (file:// en el PNG, la API en
la web), y la composición de portada que de verdad se puede pintar con lo que hay."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from markupsafe import Markup

from folio.config import Config
from folio.imagenes import cubiertas, ilustracion, libres
from folio.modelos import LibroVerificado, Pieza

# Composiciones que necesitan una imagen; sin ella, la portada es tipográfica
_CON_IMAGEN = ("sangre", "banda", "caja", "neon")


def como_uri(ruta: Path) -> str:
    return ruta.resolve().as_uri()


@dataclass
class Medios:
    cfg: Config
    url_medio: Callable[[Path], str] = como_uri
    # Buscar en la red las cubiertas que no estén en la caché (el PNG sí; la vista previa de la web
    # solo usa las que dejó la etapa de arte)
    buscar_cubiertas: bool = False
    _cubiertas: dict[str, str | None] = field(default_factory=dict)

    def cubierta(self, libro: LibroVerificado) -> str | None:
        clave = libro.olid or libro.google_id or libro.titulo
        if clave not in self._cubiertas:
            raiz = self.cfg.dir_cache("x").parent
            ruta = (cubiertas.buscar(libro, raiz, self.cfg.google_books_api_key) if self.buscar_cubiertas
                    else cubiertas.en_cache(libro, raiz))
            self._cubiertas[clave] = self.url_medio(ruta) if ruta else None
        return self._cubiertas[clave]

    def imagen(self, pieza: Pieza, sufijo: str = "") -> dict | None:
        """La imagen fijada para la pieza (o su retrato, con sufijo «-retrato»), lista para la plantilla."""
        cache = self.cfg.dir_cache(pieza.fecha)
        img = libres.de_pieza(pieza.id + sufijo, cache)
        if not img or not img.local or not (libres.dir_imagenes(cache) / img.local).exists():
            return None
        return {"src": self.url_medio(libres.dir_imagenes(cache) / img.local), "credito": img.credito,
                "enfoque": img.enfoque, "grabado": bool(pieza.arte and pieza.arte.recurso == "grabado")}

    def retrato(self, pieza: Pieza) -> dict | None:
        r = self.imagen(pieza, "-retrato")
        if r:
            r["grabado"] = False
        return r

    def portada(self, pieza: Pieza, imagen: dict | None) -> tuple[str, Markup | None]:
        """La composición de portada que se puede pintar: sin imagen, tipográfica (o el círculo en las
        propuestas antiguas); con ilustración, su SVG (ya saneado al guardarlo: solo formas)."""
        estilo = pieza.arte.portada if pieza.arte else "sangre"
        if estilo in _CON_IMAGEN and not imagen:
            return "tipografica", None
        if estilo == "ilustracion":
            ruta = ilustracion.ruta(self.cfg.dir_cache(pieza.fecha), pieza.id)
            return ("ilustracion", Markup(ruta.read_text(encoding="utf-8"))) if ruta.exists() else ("circulo", None)
        if estilo == "collage" and not imagen:
            return "circulo", None
        return estilo, None
