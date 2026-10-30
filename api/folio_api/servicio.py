"""Lógica de la API que no es HTTP: marcas de una pieza y hechos no verificados ligados a su frase."""

from __future__ import annotations

import re

from folio.modelos import Pieza
from folio.verificacion_texto import normalizar
from folio_api.esquemas import HechoLigado, Marcas

_FRASES = re.compile(r"(?<=[.!?…])\s+")


def marcas(p: Pieza) -> Marcas:
    """Avisos que tienen que verse en la portada del día."""
    return Marcas(revisar_edicion=p.revisar_edicion, hechos_no_verificados=sum(not h.verificado for h in p.hechos),
                  revision_humana=len(p.revision_humana), error=p.error)


def hechos_ligados(p: Pieza) -> list[HechoLigado]:
    """Cada hecho no verificado con la frase del guion que lo contiene (o la que más se le parece)."""
    out = []
    for h in p.hechos:
        if h.verificado:
            continue
        m = re.search(r"\d+", h.donde)
        n = int(m.group()) if m and "diapositiva" in h.donde else None
        texto = ""
        if p.guion:
            if n and 1 <= n <= len(p.guion.diapositivas):
                texto = p.guion.diapositivas[n - 1].texto
            elif n is None:
                texto = p.guion.pie_instagram
        frases = [f for f in _FRASES.split(texto) if f.strip()]
        objetivo = normalizar(h.afirmacion)
        frase = next((f for f in frases if objetivo and objetivo in normalizar(f)), None)
        if frase is None and frases:
            palabras = set(objetivo.split())
            frase = max(frases, key=lambda f: len(palabras & set(normalizar(f).split())))
        out.append(HechoLigado(hecho=h, diapositiva=n, frase=frase))
    return out
