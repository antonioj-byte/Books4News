"""Los prompts viven en `videos/prompts/<nombre>.md`, uno por archivo. La primera línea dice su versión
(`<!-- version: 3 -->`) y cada resultado guarda qué versión lo produjo («conceptos@3»), para poder iterarlos y
comparar. Los marcadores son `{{nombre}}`; la carga falla si sobra o falta alguno.
"""
from __future__ import annotations

import re

from videos.config import Config

_RE_VERSION = re.compile(r"<!--\s*version:\s*(\S+)\s*-->")
_RE_MARCADOR = re.compile(r"\{\{(\w+)\}\}")


class ErrorPrompt(RuntimeError):
    pass


def cargar(cfg: Config, nombre: str, **valores: str) -> tuple[str, str]:
    """Devuelve (texto con los marcadores rellenos, «nombre@versión»)."""
    ruta = cfg.prompts / f"{nombre}.md"
    texto = ruta.read_text(encoding="utf-8")
    m = _RE_VERSION.search(texto.splitlines()[0] if texto else "")
    version = m.group(1) if m else "0"
    marcadores = set(_RE_MARCADOR.findall(texto))
    faltan, sobran = marcadores - valores.keys(), valores.keys() - marcadores
    if faltan or sobran:
        raise ErrorPrompt(f"{nombre}.md: faltan {sorted(faltan)} / sobran {sorted(sobran)}")
    texto = _RE_MARCADOR.sub(lambda m: str(valores[m.group(1)]), texto)
    texto = _RE_VERSION.sub("", texto, count=1).lstrip()
    return texto, f"{nombre}@{version}"
