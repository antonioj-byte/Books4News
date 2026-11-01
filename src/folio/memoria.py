"""Memoria del feedback (1/11, a petición del usuario: «ver si luego se contempla en nuevas reglas o no»).

Junta lo que quien edita ha dicho y hecho con las piezas (puntuaciones, comentarios, ediciones a mano con el
antes y el después, peticiones al chat, descartes), se lo pasa a Opus (prompts/memoria_feedback.md) y guarda
los patrones que se repiten, cada uno con su evidencia y una propuesta de regla, en la tabla `memoria`. Un
patrón que vuelve a salir se refuerza (una vez más y más evidencia), no se duplica. La persona decide en la
web (página «Memoria») si cada propuesta se acepta o se rechaza; las aceptadas se pasan a los prompts y a
CLAUDE.md a mano, en una sesión, y entonces se marcan como aplicadas.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Literal

from pydantic import Field

from folio.almacen import Almacen
from folio.config import Config
from folio.llm import LLM, cargar_prompt
from folio.modelos import _TodoObligatorio

Destino = Literal["jefe_cultura", "guionista", "director_arte", "formatos", "codigo"]


class PatronLLM(_TodoObligatorio):
    existente: int = Field(description="El número del patrón guardado si es el mismo; 0 si es nuevo")
    patron: str = Field(description="Lo que se repite, en una frase concreta")
    evidencia: list[str] = Field(description="Las piezas en que se ve, una línea cada una («id: qué pasó»)")
    propuesta: str = Field(description="La regla que se propone, como iría en las instrucciones del agente")
    destino: Destino = Field(description="Dónde iría la regla")


class MemoriaLLM(_TodoObligatorio):
    patrones: list[PatronLLM] = Field(description="Los patrones que se repiten; vacía si no hay ninguno claro")
    aviso: str = Field(description="Si no hay patrones o falta feedback, por qué; si no, vacío")


def _bloque_feedback(datos: list[dict]) -> str:
    lineas = []
    for d in datos:
        lineas.append(f"## {d['pieza']} ({d['formato'] or 'sin formato'}, {d['estado']}): {d['titular']}")
        ev = d["evaluacion"]
        if ev:
            notas = ", ".join(f"{k} {ev[k]}" for k in ("seleccion", "libro", "idea", "voz") if ev.get(k))
            pub = {True: "sí", False: "no"}.get(ev.get("publicaria"), "sin responder")
            lineas.append(f"- Evaluación: {notas or 'sin notas'}; ¿la publicaría? {pub}")
            if ev.get("comentario"):
                lineas.append(f"- Comentario: {ev['comentario']}")
        for p in d["pedidos_chat"]:
            lineas.append(f"- Pidió al chat: {p}")
        for e in d["ediciones"]:
            lineas.append(f"- Editó a mano la diapositiva {e['diapositiva']}:\n  antes: {e['antes']}\n  después: {e['despues']}")
    return "\n".join(lineas)


def analizar(llm: LLM, cfg: Config, almacen: Almacen, dias: int = 14, hoy: date | None = None) -> tuple[list[int], str, int]:
    """Analiza el feedback de los últimos `dias` y guarda los patrones. Devuelve (ids guardados, aviso, piezas leídas)."""
    desde = ((hoy or date.today()) - timedelta(days=dias)).isoformat()
    datos = almacen.feedback(desde)
    if not datos:
        return [], f"No hay feedback desde el {desde}: ninguna pieza evaluada, editada, comentada ni descartada.", 0
    guardados = almacen.patrones()
    patrones = "\n".join(f"{p.id}. [{p.estado}] {p.patron} → {p.propuesta} ({p.destino}; {p.veces} veces)" for p in guardados) or "(ninguno)"
    prompt = cargar_prompt(cfg, "memoria_feedback", {"[pegar patrones]": patrones, "[pegar feedback]": _bloque_feedback(datos)})
    r, _ = llm.estructurado("memoria", [{"role": "user", "content": prompt}], MemoriaLLM, etapa_modelo="memoria", max_tokens=8000)
    ids_validos = {p.id for p in guardados}
    ids = [almacen.guardar_patron(p.patron.strip(), [e.strip() for e in p.evidencia if e.strip()], p.propuesta.strip(), p.destino,
                                  p.existente if p.existente in ids_validos else None)
           for p in r.patrones if p.patron.strip() and p.propuesta.strip()]
    return ids, r.aviso, len(datos)


def markdown(almacen: Almacen) -> str:
    """La memoria en markdown, para pasar las aceptadas a los prompts y a CLAUDE.md."""
    out = ["# Memoria del feedback", ""]
    for estado, titulo in (("aceptada", "Aceptadas (pendientes de pasar a las reglas)"), ("propuesta", "Propuestas"),
                           ("aplicada", "Aplicadas"), ("rechazada", "Rechazadas")):
        grupo = [p for p in almacen.patrones() if p.estado == estado]
        if not grupo:
            continue
        out += [f"## {titulo}", ""]
        for p in grupo:
            out += [f"- **{p.patron}** ({p.destino}, {p.veces} {'vez' if p.veces == 1 else 'veces'}, #{p.id})", f"  - Propuesta: {p.propuesta}"]
            out += [f"  - {e}" for e in p.evidencia[:6]]
            if p.nota:
                out.append(f"  - Nota: {p.nota}")
        out.append("")
    return "\n".join(out)
