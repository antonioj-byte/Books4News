"""Recurso gráfico de la diapositiva de actualidad cuando no lleva foto ni cifra (31/10).

Cuatro recursos, elegidos por el usuario: «golpe» (la frase final a tamaño de titular), «gigante» (una
palabra a toda la altura), «teletipo» (etiquetas, número grande y letra de máquina) y «collage» (papel
rasgado con la palabra y un sello). El director de arte propone los datos; aquí se comprueba que cada
palabra sale literalmente del texto de la diapositiva (salvo mayúsculas, tildes y signos), en la etapa
de arte y otra vez al pintar, porque el texto puede editarse después en la web.
"""

from __future__ import annotations

import re

from markupsafe import Markup

from folio.modelos import SinFoto
from folio.verificacion_texto import normalizar

_COLA = " \t\n.…!?»\"'*"
_NUMERO = re.compile(r"\d")


def literal(frase: str | None, texto: str) -> bool:
    """La frase está en el texto palabra por palabra, seguidas (sin mirar mayúsculas, tildes ni signos)."""
    f = normalizar(frase or "")
    return bool(f) and f" {f} " in f" {normalizar(texto)} "


def inicio_del_final(frase: str | None, texto: str) -> int | None:
    """Dónde empieza la frase en el texto si es literalmente su final (salvo el punto); si no, None."""
    if not frase or not frase.strip(_COLA):
        return None
    f = frase.strip().rstrip(_COLA)
    i = texto.rstrip().rfind(f)
    if i <= 0 or texto[i + len(f):].strip(_COLA) or not texto[:i].strip():
        return None
    return i


def _palabras(x: str | None) -> int:
    return len(normalizar(x or "").split())


def _limpiar(sf: SinFoto, texto: str, victimas: bool) -> list[str]:
    """Anula los datos que no salen del texto o no tienen la medida. Devuelve los avisos."""
    avisos = []

    def fuera(campo: str, valor) -> None:
        avisos.append(f"Sin foto: {campo} descartado («{valor}»), no sale literalmente del texto o no tiene la medida")

    if sf.golpe and (inicio_del_final(sf.golpe, texto) is None or not 3 <= _palabras(sf.golpe) <= 14):
        fuera("golpe", sf.golpe)
        sf.golpe = None
    if sf.golpe_remate and (not sf.golpe or inicio_del_final(sf.golpe_remate, sf.golpe) is None
                            or not 1 <= _palabras(sf.golpe_remate) <= 4):
        if sf.golpe:
            fuera("remate del golpe", sf.golpe_remate)
        sf.golpe_remate = None
    if sf.palabra:
        p = sf.palabra.strip(_COLA + ",;:()")
        if " " in p or not 4 <= len(p) <= 12 or not literal(p, texto):
            fuera("palabra", sf.palabra)
            sf.palabra = None
        else:
            sf.palabra = p
    etiquetas = []
    for e in sf.etiquetas[:3]:
        if 1 <= _palabras(e) <= 2 and len(e) <= 22 and literal(e, texto):
            etiquetas.append(" ".join(e.split()).strip(_COLA + ",;:()"))
        else:
            fuera("etiqueta", e)
    sf.etiquetas = etiquetas
    if sf.numero and (victimas or not _NUMERO.search(sf.numero) or len(sf.numero) > 12 or not literal(sf.numero, texto)):
        fuera("número", sf.numero)
        sf.numero = None
    if sf.numero_rotulo and (not sf.numero or not 1 <= _palabras(sf.numero_rotulo) <= 5 or not literal(sf.numero_rotulo, texto)):
        if sf.numero:
            fuera("rótulo del número", sf.numero_rotulo)
        sf.numero_rotulo = None
    if sf.sello and (not 1 <= _palabras(sf.sello) <= 3 or len(sf.sello) > 28 or not literal(sf.sello, texto)):
        fuera("sello", sf.sello)
        sf.sello = None
    return avisos


def tiene_datos(sf: SinFoto, recurso: str) -> bool:
    """Lo mínimo que necesita cada recurso para pintarse."""
    return {"golpe": bool(sf.golpe), "gigante": bool(sf.palabra), "teletipo": len(sf.etiquetas) >= 2,
            "collage": bool(sf.sello and sf.palabra)}[recurso]


def validar(sf: SinFoto | None, texto: str, permitidos: list[str], victimas: bool = False) -> tuple[SinFoto | None, list[str]]:
    """Limpia la propuesta y se queda con el recurso pedido si está permitido y tiene datos; si no,
    con el primero de la lista que los tenga. None si ninguno."""
    if sf is None or not texto.strip():
        return None, []
    sf = sf.model_copy(deep=True)
    avisos = _limpiar(sf, texto, victimas)
    candidatos = ([sf.recurso] if sf.recurso in permitidos else []) + [r for r in permitidos if r != sf.recurso]
    for r in candidatos:
        if tiene_datos(sf, r):
            if r != sf.recurso:
                avisos.append(f"Sin foto: «{sf.recurso}» no se puede pintar; se usa «{r}»")
            sf.recurso = r
            return sf, avisos
    avisos.append("Sin foto: ningún recurso tiene datos válidos; la diapositiva sale solo con texto")
    return None, avisos


def marcar(texto: str, frase: str | None, html) -> Markup | None:
    """El texto en HTML con la frase (literal y al final) envuelta en <span class="marca">; None si no
    está o si el corte deja una cursiva (*…*) a medias. `html` convierte texto del guion en HTML."""
    i = inicio_del_final(frase, texto)
    if i is None:
        return None
    antes, final = texto[:i], texto[i:]
    if antes.count("*") % 2 or final.count("*") % 2:
        return None
    return Markup(f'{html(antes)}<span class="marca">{html(final)}</span>')
