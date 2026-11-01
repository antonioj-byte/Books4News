"""Radar del libro (1/11, a petición del usuario): «una lista no desarrollada de posibles temas del mundo del
libro, solo noticias que puedan tener entidad por sí solas a partir de las referencias del radar, y que se puedan
desarrollar con un clic».

Después de la mesa, un modelo barato (prompts/radar.md) repasa las historias del carril editorial que el jefe no
ha elegido (también las que no le llegaron: el radar ve más) y devuelve unos pocos temas. Cada uno queda como
pieza «pendiente» con `radar=True` y formato «radar» (sin libro obligatorio), y se escribe al pulsar
«Desarrollar» en la web (lo mismo que «Proceder»).
"""

from __future__ import annotations

from pydantic import Field

from folio import seleccion
from folio.llm import LLM, cargar_prompt
from folio.modelos import BaseModel, Historia, HistoriaElegida, SeleccionJefe


class TemaRadar(BaseModel):
    historia_id: str = Field(description="Identificador de la historia tal como aparece en la lista")
    titular: str = Field(description="Titular de portada, 12 palabras como máximo, sin pregunta")
    de_que_se_habla: str = Field(description="De qué se habla, en dos frases, solo con lo que dicen titulares y resúmenes")
    cuestion_de_fondo: str = Field(description="La cuestión de fondo, en una frase")
    por_que: str = Field(description="Por qué merece una pieza, en una línea")
    protagonista: str = Field(description="Nombre completo de la persona real que protagoniza la historia, si la hay; si no, vacío")


class RadarLLM(BaseModel):
    temas: list[TemaRadar] = Field(description="De mejor a peor; vacía si ninguna historia vale")


def temas(llm: LLM, historias: list[Historia], sel: SeleccionJefe | None) -> tuple[list[HistoriaElegida], list[str]]:
    """Los temas del radar y los avisos (ids que no existen, repetidos). Nada si está apagado o no hay historias."""
    p = llm.cfg.pipeline.radar
    elegidas = {e.historia_id for e in (sel.elegidas if sel else [])}
    candidatas = [h for h in historias if h.carril in ("editorial", "radar") and h.id not in elegidas]
    if not p.activo or not candidatas:
        return [], []
    prompt = cargar_prompt(llm.cfg, "radar", {
        "[pegar máximo]": str(p.max_temas),
        "[pegar lista]": seleccion.bloque_historias(candidatas, "radar"),
    })
    salida, _ = llm.estructurado("radar", [{"role": "user", "content": prompt}], RadarLLM, etapa_modelo="radar", max_tokens=4000)
    ids = {h.id for h in candidatas}
    avisos, vistos, out = [], set(), []
    for t in salida.temas:
        if t.historia_id not in ids or t.historia_id in vistos:
            avisos.append(f"Radar: id inexistente o repetido ({t.historia_id}); se descarta «{t.titular}»")
            continue
        vistos.add(t.historia_id)
        out.append(HistoriaElegida(formato="radar", historia_id=t.historia_id, titular=t.titular,
                                   de_que_se_habla=t.de_que_se_habla, cuestion_de_fondo=t.cuestion_de_fondo,
                                   libros_candidatos=[], gancho_libro="", por_que=t.por_que,
                                   protagonista=t.protagonista.strip()))
    return out[: p.max_temas], avisos
