"""Normalización y comparación de títulos y autores."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_ARTICULOS = {"el", "la", "los", "las", "un", "una", "the", "a", "an", "le", "les", "l", "der", "die", "das"}
_NO_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = _NO_ALNUM.sub(" ", t)
    return " ".join(t.split())


def sin_subtitulo(titulo: str) -> str:
    return re.split(r"[:.;(\[]", titulo, maxsplit=1)[0]


def _nucleo(titulo: str) -> str:
    palabras = normalizar(sin_subtitulo(titulo)).split()
    while palabras and palabras[0] in _ARTICULOS and len(palabras) > 1:
        palabras = palabras[1:]
    return " ".join(palabras)


def titulos_coinciden(a: str, b: str, umbral: float = 0.88) -> bool:
    na, nb = _nucleo(a), _nucleo(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Título con subtítulo frente a título corto: basta que uno empiece por el otro
    # si el corto tiene cierta longitud.
    corto, largo = sorted((na, nb), key=len)
    if len(corto) >= 8 and largo.startswith(corto):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= umbral


def apellido(autor: str) -> str:
    partes = normalizar(autor).split()
    return partes[-1] if partes else ""


def autor_coincide(propuesto: str, autores: list[str]) -> bool:
    """El apellido del autor propuesto aparece como palabra en alguno de los autores."""
    ap = apellido(propuesto)
    if len(ap) < 2:
        return False
    return any(ap in normalizar(a).split() for a in autores)


def clave_libro(titulo: str, autor: str) -> str:
    return f"{_nucleo(titulo)}|{apellido(autor)}"
