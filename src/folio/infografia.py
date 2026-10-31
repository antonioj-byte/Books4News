"""Infografía de la diapositiva de la idea (31/10, elegidas por el usuario de un catálogo: I1, I3 e I7).

- «linea» (I1): línea de tiempo con la primera edición del libro principal, su edición española si es de
  otro año y la noticia. Los años salen de la ficha verificada y de la fecha de la pieza, nunca del modelo.
- «mapa» (I3): noticia → idea → libro, con dos rótulos copiados del guion.
- «esquema» (I7): la ilustración técnica de Magnific (IL3) hecha a partir de la imagen de la pieza, con tres
  rótulos copiados del guion. La imagen no lleva texto: los rótulos los pone el código.

El título lo propone el director de arte: de 3 a 8 palabras y sin cifras (las cifras solo las pone el
código). Todo se comprueba al validar y otra vez al pintar, porque el guion puede editarse en la web.
"""

from __future__ import annotations

import re

from folio.guion import libro_verificado
from folio.modelos import Infografia, Pieza
from folio.sin_foto import literal

_CIFRA = re.compile(r"\d")
_MEDIDAS = {"mapa": (2, 2, 4), "esquema": (3, 1, 3)}     # rótulos: cuántos, palabras mínimas y máximas


def texto_guion(pieza: Pieza) -> str:
    return " ".join(d.texto for d in pieza.guion.diapositivas) if pieza.guion else ""


def libro_principal(pieza: Pieza):
    """La ficha verificada del primer libro del guion."""
    if not pieza.guion or not pieza.guion.libros:
        return pieza.libros[0] if pieza.libros else None
    return libro_verificado(pieza.guion.libros[0], pieza.libros) or (pieza.libros[0] if pieza.libros else None)


def hitos(pieza: Pieza) -> list[dict]:
    """Hitos de la línea de tiempo, en orden: primera edición, edición española (si es de otro año) y la
    noticia. Vacía si no hay dos años distintos: con el mismo año no hay línea que contar."""
    libro = libro_principal(pieza)
    if not libro or not libro.anio_primera_edicion:
        return []
    titulo = libro.titulo_propuesto
    lista = [{"anio": libro.anio_primera_edicion, "que": titulo,
              "detalle": f"primera edición{' en ' + libro.idioma_original if libro.idioma_original and libro.idioma_original.lower() != 'español' else ''}"}]
    es = libro.edicion_es_detalle
    anio_es = int(es.anio) if libro.edicion_es == "si" and es and es.anio and str(es.anio).isdigit() else None
    if anio_es and anio_es != libro.anio_primera_edicion:
        lista.append({"anio": anio_es, "que": es.titulo or titulo, "detalle": f"en español{', ' + es.editorial if es.editorial else ''}"})
    anio_noticia = int(pieza.fecha[:4])
    if anio_noticia > lista[-1]["anio"]:
        lista.append({"anio": anio_noticia, "que": "la noticia", "detalle": "hoy", "ahora": True})
    return lista if len(lista) >= 2 else []


def _titulo(texto: str | None) -> str | None:
    if not texto:
        return None
    t = " ".join(texto.split()).strip(" .:")
    return t if 3 <= len(t.split()) <= 8 and len(t) <= 60 and not _CIFRA.search(t) else None


def validar(info: Infografia | None, pieza: Pieza, permitidos: list[str], hay_imagen: bool) -> tuple[Infografia | None, list[str]]:
    """La infografía si se puede pintar con datos comprobados; si no, None y el motivo en los avisos."""
    if info is None or info.tipo == "ninguna" or not pieza.guion:
        return None, []
    if info.tipo not in permitidos:
        return None, [f"Infografía: «{info.tipo}» no está permitida en la configuración"]
    info = info.model_copy(deep=True)
    avisos = []
    titulo = _titulo(info.titulo)
    if info.titulo and not titulo:
        avisos.append(f"Infografía: título descartado («{info.titulo}»): de 3 a 8 palabras y sin cifras")
    info.titulo = titulo or ""
    if info.tipo == "linea":
        info.etiquetas = []
        if not hitos(pieza):
            return None, avisos + ["Infografía: la línea de tiempo necesita dos años distintos verificados; sin infografía"]
        return info, avisos
    if info.tipo == "esquema" and not hay_imagen:
        return None, avisos + ["Infografía: el esquema se dibuja a partir de la imagen de la pieza, y no hay; sin infografía"]
    cuantos, minimo, maximo = _MEDIDAS[info.tipo]
    texto = texto_guion(pieza)
    buenas = []
    for e in info.etiquetas:
        e = " ".join(e.split()).strip(" .,;:«»\"'")
        if minimo <= len(e.split()) <= maximo and len(e) <= 34 and literal(e, texto):
            buenas.append(e)
        else:
            avisos.append(f"Infografía: rótulo descartado («{e}»), no sale literalmente del guion o no tiene la medida")
    if len(buenas) < cuantos:
        return None, avisos + [f"Infografía: el {info.tipo} necesita {cuantos} rótulos del guion; sin infografía"]
    info.etiquetas = buenas[:cuantos]
    return info, avisos
