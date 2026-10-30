"""Comprobación de hechos (prompts/comprobador_hechos.md).

Un modelo barato coteja cada cifra, fecha, nombre y hecho de la noticia que aparece en el
guion con los textos fuente que recibió el guionista. No se fía de su palabra: si da un dato
por verificado, la evidencia que copia tiene que aparecer literalmente en el texto del medio
que cita. Lo que no se sostiene se marca en el informe como «hecho no verificado».
"""

from __future__ import annotations

from folio.llm import LLM, cargar_prompt
from folio.modelos import ComprobacionHechos, FuenteNoticia, GuionLLM, HechoComprobado
from folio.verificacion_texto import normalizar


def _bloque_guion(g: GuionLLM) -> str:
    diapositivas = "\n".join(f"diapositiva {x.n}: {x.texto}" for x in g.diapositivas)
    return f"<guion>\n{diapositivas}\npie: {g.pie_instagram}\n</guion>"


def _bloque_fuentes(textos: list[tuple[FuenteNoticia, str]]) -> str:
    return "\n".join(f'<fuente medio="{f.medio}">\n{t}\n</fuente>' for f, t in textos)


def _evidencia_en_fuente(h: HechoComprobado, textos: list[tuple[FuenteNoticia, str]]) -> bool:
    ev = normalizar(h.evidencia or "")
    if len(ev.split()) < 3:
        return False
    candidatos = [t for f, t in textos if h.medio and normalizar(f.medio) == normalizar(h.medio)] or [t for _, t in textos]
    return any(ev in normalizar(t) for t in candidatos)


def comprobar(llm: LLM, pieza_id: str, g: GuionLLM, textos: list[tuple[FuenteNoticia, str]]) -> list[HechoComprobado]:
    prompt = cargar_prompt(llm.cfg, "comprobador_hechos", {
        "[pegar guion]": _bloque_guion(g),
        "[pegar fuentes]": _bloque_fuentes(textos),
    })
    res, _ = llm.estructurado(f"hechos:{pieza_id}", [{"role": "user", "content": prompt}], ComprobacionHechos,
                              etapa_modelo="comprobacion", max_tokens=16000)
    for h in res.hechos:
        if h.verificado and not _evidencia_en_fuente(h, textos):
            h.verificado = False
            h.nota = ("La evidencia que dio el comprobador no aparece literalmente en la fuente"
                      + (f" ({h.medio})" if h.medio else ""))
    return res.hechos
