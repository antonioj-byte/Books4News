"""El texto de las diapositivas, listo para las plantillas: HTML seguro, cursivas, ficha de libros,
remate del titular y libro del que habla cada diapositiva."""

from __future__ import annotations

import html
import re
from typing import Callable

from markupsafe import Markup

from folio.guion import libro_verificado
from folio.modelos import LibroVerificado, Pieza

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")
_CURSIVA = re.compile(r"\*([^*\n]+)\*")
# En la imagen no se repite la firma del texto del cierre («— Folio»).
# «Recomienda Folio.» al final del cierre: se va entero, no solo «Folio» (2/11: quedaba «… (Seix Barral). Recomienda»)
FIRMA_FINAL = re.compile(r"\s*(?:[—–-]\s*)?(?:(?:[Ll][oa]s? )?(?:[Rr]ecomienda|[Ff]irma)\s+)?Folio\.?\s*$")


def texto_html(texto: str) -> Markup:
    """Texto del guion → HTML seguro: se escapa todo y *así* pasa a cursiva."""
    return Markup(_CURSIVA.sub(r"<em>\1</em>", html.escape(texto, quote=False)))


def fecha_larga(fecha: str) -> str:
    a, m, d = fecha.split("-")
    return f"{int(d)} de {_MESES[int(m) - 1]} de {a}"


def ficha_libros(pieza: Pieza, cubierta: Callable[[LibroVerificado], str | None] | None = None) -> list[dict]:
    """Libros del guion con sus datos verificados: editorial y traductor españoles, o nada.
    `cubierta`, si se da, devuelve la URL de la cubierta de cada libro verificado (o None)."""
    out = []
    for lg in pieza.guion.libros if pieza.guion else []:
        v = libro_verificado(lg, pieza.libros)
        datos = []
        if v and v.edicion_es == "si":
            d = v.edicion_es_detalle
            ed = ", ".join(x for x in (lg.editorial_espanola, d.anio if d else None) if x)
            if ed:
                datos.append(ed)
            if lg.traductor:
                datos.append(f"Traducción de {lg.traductor}")
        elif v and v.edicion_es == "no":
            datos.append("Sin edición en español")
        out.append({"titulo": texto_html(lg.titulo.replace("*", "")), "autor": lg.autor, "datos": " · ".join(datos),
                    "anio": v.anio_primera_edicion if v else None,
                    "editorial": lg.editorial_espanola if v and v.edicion_es == "si" else None,
                    "edicion_es": v.edicion_es if v else "desconocido",
                    "cubierta": cubierta(v) if cubierta and v else None,
                    "verificado": bool(v and v.fuentes_verificacion)})
    return out


def _sin_marcas(texto: str) -> str:
    return re.sub(r"\W+", " ", texto.replace("*", "")).strip().lower()


def libro_de_diapositiva(libros: list[dict], pieza: Pieza, texto: str) -> dict | None:
    """El libro del que habla una diapositiva: el primero cuyo título (sin subtítulo) aparece en el texto."""
    plano = _sin_marcas(texto)
    for libro, lg in zip(libros, pieza.guion.libros):
        corto = _sin_marcas(lg.titulo.split(":")[0])
        if corto and corto in plano:
            return libro
    return None


def titular_con_remate(texto: str, remate: str | None) -> Markup:
    """El titular con su remate (el final, en cursiva) si el remate es literalmente el final del titular."""
    if remate:
        r = remate.rstrip().rstrip(".")
        corte = texto.rstrip().rstrip(".").rfind(r)
        if corte >= 0 and r != texto.strip().rstrip("."):
            # Al final, el remate se lleva el punto; en medio (destacado desde el chat, 2/11), solo el trozo
            fin = len(texto) if not texto[corte + len(r):].strip(" .") else corte + len(r)
            return Markup(f'{texto_html(texto[:corte])}<span class="remate">{texto_html(texto[corte:fin])}</span>'
                          f'{texto_html(texto[fin:])}')
    return texto_html(texto)


def color_de_pieza(pieza: Pieza, n_colores: int) -> int:
    """Índice estable de color para la pieza (las propuestas que cambian de color por pieza)."""
    return sum(map(ord, pieza.id)) % n_colores if n_colores else 0
