"""El pase de estilo (2/11, a petición del usuario: «escribe bastante mal»): un editor de Opus con esfuerzo alto
reescribe las frases de un guion ya válido para que tengan la voz de Folio (prompts/voz_folio.md), sin tocar hechos,
libros, citas ni estructura (prompts/editor_estilo.md). El código vuelve a pasar todas las reglas y comprueba que no
entra ninguna cifra nueva; si algo no cuadra, se queda el guion de antes. De momento solo lo usa la prueba A/B."""

from __future__ import annotations

import json
import re

from folio.config import Config
from folio.llm import LLM, cargar_prompt
from folio.modelos import CitaVerificada, FuenteNoticia, GuionLLM, LibroVerificado


def _cifras(g: GuionLLM) -> set[str]:
    texto = " ".join(t for d in g.diapositivas for t in (d.texto, d.subtitulo or "")) + " " + g.pie_instagram
    return set(re.findall(r"\d[\d.,]*", texto))


def pulir(llm: LLM, cfg: Config, pieza_id: str, g: GuionLLM, libros: list[LibroVerificado],
          fuentes: list[FuenteNoticia], citas: list[CitaVerificada], formato: str) -> tuple[GuionLLM, list[str]]:
    """Devuelve (guion pulido o el de antes, avisos)."""
    from folio import guion as guionista
    voz = (cfg.dir_prompts / "voz_folio.md").read_text(encoding="utf-8").strip()
    prompt = cargar_prompt(cfg, "editor_estilo", {"[pegar voz]": voz,
                                                  "[pegar guion]": json.dumps(g.model_dump(mode="json"), ensure_ascii=False, indent=1)})
    try:
        nuevo, _ = llm.estructurado(f"estilo:{pieza_id}", [{"role": "user", "content": prompt}], GuionLLM, etapa_modelo="estilo")
    except Exception as exc:
        return g, [f"Pase de estilo: no se pudo ({type(exc).__name__})"]
    guionista.corregir_mecanico(nuevo)
    citas_ok = frozenset(guionista.normalizar(c.texto) for c in citas if c.tipo == "libro")
    criticas_ok = frozenset(guionista.normalizar(c.texto) for c in citas if c.tipo != "libro")
    errores = guionista.validar(cfg, nuevo, libros, fuentes, citas_ok, criticas_ok, formato)
    nuevas = _cifras(nuevo) - _cifras(g)
    if nuevas:
        errores.append(f"cifras que no estaban: {', '.join(sorted(nuevas))}")
    if [d.tipo for d in nuevo.diapositivas] != [d.tipo for d in g.diapositivas]:
        errores.append("cambió la estructura")
    if errores:
        return g, ["Pase de estilo descartado: " + " | ".join(errores)]
    return nuevo, ["Pase de estilo aplicado"]
