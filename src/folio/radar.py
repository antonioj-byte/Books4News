"""Radar del libro (1/11, a petición del usuario): «una lista no desarrollada de posibles temas del mundo del
libro, solo noticias que puedan tener entidad por sí solas a partir de las referencias del radar, y que se puedan
desarrollar con un clic».

Después de la mesa, un modelo barato (prompts/radar.md) repasa las historias del carril editorial que el jefe no
ha elegido (también las que no le llegaron: el radar ve más) y devuelve unos pocos temas. Cada uno queda como
pieza «pendiente» con `radar=True` y formato «radar» (sin libro obligatorio), y se escribe al pulsar
«Desarrollar» en la web (lo mismo que «Proceder»).
"""

from __future__ import annotations

import re
import unicodedata

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


_NO_NOMBRES = {"el", "la", "los", "las", "un", "una", "del", "de", "en", "por", "con", "tras", "para", "premio", "festival",
               "editorial", "libro", "libros", "feria", "nuevo", "nueva", "gran"}


def nombres(texto: str) -> set[str]:
    """Los nombres propios de un titular (palabras con mayúscula de 4 letras o más, sin tildes ni mayúsculas): lo que
    dice de qué noticia se trata aunque cambie la forma de contarla («Jaenada», «goncourt»)."""
    def plano(w: str) -> str:
        return unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode().lower()
    return {plano(w) for w in re.findall(r"\b[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü'-]{3,}", texto or "")} - _NO_NOMBRES


def misma_noticia(a: str, b: str) -> bool:
    """Dos titulares cuentan la misma noticia si comparten al menos dos nombres propios (4/11, a petición del usuario:
    «no tiene sentido que dé el mismo breve dos veces»: «Jaenada gana el Goncourt…» salió de las crónicas alemanas y de
    las hispanas, que se agrupan aparte por el idioma)."""
    return len(nombres(a) & nombres(b)) >= 2


def temas(llm: LLM, historias: list[Historia], sel: SeleccionJefe | None,
          ya: list[str] = ()) -> tuple[list[HistoriaElegida], list[str]]:
    """Los temas del radar y los avisos (ids que no existen, repetidos). Nada si está apagado o no hay historias.
    `ya`: titulares que no se repiten como breve (lo de la mesa y lo publicado en los últimos días)."""
    p = llm.cfg.pipeline.radar
    elegidas = {e.historia_id for e in (sel.elegidas if sel else [])}
    candidatas = [h for h in historias if h.carril in ("editorial", "radar") and h.id not in elegidas]
    # 6/11 («los breves seleccionan el Femina, pero no el Herralde»): primero las del mundo en español
    candidatas.sort(key=lambda h: not any(a.idioma == "es" for a in h.articulos))
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
        repetido = next((x for x in [*ya, *(o.titular for o in out)] if misma_noticia(t.titular, x)), None)
        if repetido:
            avisos.append(f"Radar: «{t.titular}» cuenta lo mismo que «{repetido}»; se descarta")
            continue
        vistos.add(t.historia_id)
        out.append(HistoriaElegida(formato="radar", historia_id=t.historia_id, titular=t.titular,
                                   de_que_se_habla=t.de_que_se_habla, cuestion_de_fondo=t.cuestion_de_fondo,
                                   libros_candidatos=[], gancho_libro="", por_que=t.por_que,
                                   protagonista=t.protagonista.strip()))
    return out[: p.max_temas], avisos
