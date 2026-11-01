"""El lector sin contexto (2/11, a petición del usuario: «no entiendo este copy; van varias veces que los copies son
difíciles de entender si no conoces nada de la obra»).

Un modelo barato (prompts/lector_claridad.md, modelo `claridad`) lee el guion como un lector curioso que no conoce
ni el libro ni la noticia y señala lo que no se entiende: personas o episodios sin presentar, alusiones, jerga y
frases en clave. guion.escribir se lo devuelve al guionista una vez para que lo reescriba.
"""

from __future__ import annotations

from pydantic import Field

from folio.llm import LLM, cargar_prompt
from folio.modelos import BaseModel, GuionLLM


class Problema(BaseModel):
    diapositiva: int = Field(description="Número de la diapositiva; 0 para el pie")
    fragmento: str = Field(description="El fragmento exacto que no se entiende")
    falta: str = Field(description="Qué le falta saber al lector, en pocas palabras")


class Lectura(BaseModel):
    problemas: list[Problema] = Field(description="Vacía si todo se entiende sin contexto")


def texto_guion(g: GuionLLM) -> str:
    lineas = [f"Diapositiva {d.n} ({d.tipo}): {d.texto}" + (f" / {d.subtitulo}" if d.subtitulo else "") for d in g.diapositivas]
    return "\n".join(lineas + [f"Pie: {g.pie_instagram}"])


def revisar(llm: LLM, cfg, pieza_id: str, g: GuionLLM) -> list[str]:
    """Los problemas de comprensión del guion, ya redactados para el guionista (vacío si se entiende todo)."""
    prompt = cargar_prompt(cfg, "lector_claridad", {"[pegar guion]": f"<carrusel>\n{texto_guion(g)}\n</carrusel>"})
    lectura, _ = llm.estructurado(f"claridad:{pieza_id}", [{"role": "user", "content": prompt}], Lectura,
                                  etapa_modelo="claridad", max_tokens=3000)
    return [f"{'el pie' if p.diapositiva == 0 else f'diapositiva {p.diapositiva}'}: «{p.fragmento}» ({p.falta})"
            for p in lectura.problemas if p.fragmento.strip()]
