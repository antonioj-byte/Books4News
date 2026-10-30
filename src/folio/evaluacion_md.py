"""Bloques de evaluación en markdown: el formato que comparten informe.md (evaluación de cada pieza)
y ab.md (prueba A/B ciega).

Un bloque va entre marcadores con una clave y lleva un campo por línea, que se rellena a mano o
desde la web:

    <!-- evaluacion:2026-10-30-1 -->
    **Evaluación** (rellenar a mano)

    - Selección (1–5): 4
    ...
    <!-- /evaluacion:2026-10-30-1 -->
"""

from __future__ import annotations

import re

CAMPOS_PIEZA = ("Selección (1–5)", "Libro (1–5)", "Idea nueva (1–5)", "Voz (1–5)",
                "¿La publicarías? (sí/no)", "Comentario")
# En la prueba A/B la selección es la misma para todas las versiones
CAMPOS_AB = CAMPOS_PIEZA[1:]


def bloque(clave: str, campos: tuple[str, ...], cabecera: list[str] | None = None) -> list[str]:
    """Líneas de un bloque vacío, con una línea en blanco al final."""
    return [f"<!-- {clave} -->", *(cabecera or []), *[f"- {c}: " for c in campos], f"<!-- /{clave} -->", ""]


def _patron(prefijo: str) -> re.Pattern:
    return re.compile(rf"<!-- ({re.escape(prefijo)}:[^ ]+) -->\n(.*?)<!-- /\1 -->", re.S)


def _campos(cuerpo: str) -> dict[str, str]:
    """Campos con valor de un bloque (las líneas «- campo: valor»)."""
    out = {}
    for linea in cuerpo.splitlines():
        if linea.startswith("- ") and ":" in linea:
            k, v = linea[2:].split(":", 1)
            if v.strip():
                out[k.strip()] = v.strip()
    return out


def leer(md: str, prefijo: str) -> dict[str, dict[str, str]]:
    """{resto de la clave: {campo: valor}} de los bloques con algún campo rellenado.
    Para «ab:2026-10-30-1:A», con prefijo «ab», el resto es «2026-10-30-1:A»."""
    out = {}
    for clave, cuerpo in _patron(prefijo).findall(md):
        campos = _campos(cuerpo)
        if campos:
            out[clave.split(":", 1)[1]] = campos
    return out


def rellenada(md: str, prefijo: str) -> bool:
    """¿Hay algún bloque con algún campo rellenado?"""
    return bool(leer(md, prefijo))


def rellenar(md: str, clave: str, valores: dict[str, object]) -> str | None:
    """Pone los valores en los campos del bloque `clave` (None, vacío). None si el bloque no está."""
    patron = re.compile(rf"(<!-- {re.escape(clave)} -->\n)(.*?)(<!-- /{re.escape(clave)} -->)", re.S)
    m = patron.search(md)
    if not m:
        return None

    def linea(l: str) -> str:
        if l.startswith("- ") and ":" in l:
            campo = l[2:].split(":", 1)[0].strip()
            if campo in valores:
                v = valores[campo]
                return f"- {campo}: {'' if v is None else v}"
        return l

    cuerpo = "\n".join(linea(l) for l in m.group(2).split("\n"))
    return md[: m.start()] + m.group(1) + cuerpo + m.group(3) + md[m.end():]
