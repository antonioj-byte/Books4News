"""Memoria del feedback (1/11, a petición del usuario: «ver si luego se contempla en nuevas reglas o no»).

Junta lo que quien edita ha dicho y hecho con las piezas (puntuaciones, comentarios, ediciones a mano con el
antes y el después, peticiones al chat, descartes), se lo pasa a Opus (prompts/memoria_feedback.md) y guarda
los patrones que se repiten, cada uno con su evidencia y una propuesta de regla, en la tabla `memoria`. Un
patrón que vuelve a salir se refuerza (una vez más y más evidencia), no se duplica. La persona decide en la
web (página «Memoria») si cada propuesta se acepta o se rechaza; las aceptadas se pasan a los prompts y a
CLAUDE.md a mano, en una sesión, y entonces se marcan como aplicadas.

Desde el 2/11 (a petición del usuario: «¿se está recogiendo el feedback que voy dando?»):
- el análisis se lanza solo una vez por semana, los lunes tras la ejecución de madrugada (`folio memoria
  analizar --si-toca`, último paso de la diaria; si un lunes no se pudo, el primer día siguiente), y cada análisis
  queda registrado (tabla `memoria_analisis`);
- lo que el usuario pide en las conversaciones de trabajo y acaba en reglas se apunta en
  config/memoria_conversacion.yaml y la API lo carga al arrancar como patrones «aplicada» de origen
  «conversacion»: en la página «Memoria» está todo lo que ha cambiado y por qué, venga de donde venga.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

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


def analizar(llm: LLM, cfg: Config, almacen: Almacen, dias: int = 14, hoy: date | None = None,
             origen: str = "manual") -> tuple[list[int], str, int]:
    """Analiza el feedback de los últimos `dias` y guarda los patrones. Devuelve (ids guardados, aviso, piezas leídas).
    Cada análisis queda registrado, también el que no encuentra feedback (no gasta: no llama al modelo)."""
    trazas = getattr(llm, "trazas", [])
    antes = len(trazas)
    ids, aviso, n = _analizar(llm, cfg, almacen, dias, hoy)
    almacen.registrar_analisis(origen, n, len(ids), sum(t.coste_usd for t in trazas[antes:]), aviso)
    return ids, aviso, n


DIA_SEMANAL = 0          # lunes


def toca_analisis(almacen: Almacen, hoy: date | None = None) -> tuple[bool, str]:
    """¿Toca el análisis semanal? Los lunes, si no ha habido otro en los últimos seis días; cualquier día, si
    han pasado ocho o más (o nunca ha habido uno). Devuelve (toca, por qué)."""
    hoy = hoy or date.today()
    ultimo = almacen.ultimo_analisis()
    if not ultimo:
        return True, "nunca se ha analizado el feedback"
    dias = (hoy - datetime.fromisoformat(ultimo["ts"]).date()).days
    if hoy.weekday() == DIA_SEMANAL and dias >= 6:
        return True, f"es lunes y el último análisis fue hace {dias} días"
    if dias >= 8:
        return True, f"el último análisis fue hace {dias} días"
    return False, f"el último análisis fue hace {dias} días; el siguiente, el lunes"


def proximo_analisis(almacen: Almacen, hoy: date | None = None) -> date:
    """El día de la próxima ejecución diaria en que tocará el análisis."""
    hoy = hoy or date.today()
    for n in range(0, 9):
        if toca_analisis(almacen, hoy + timedelta(days=n))[0]:
            return hoy + timedelta(days=n)
    return hoy + timedelta(days=8)


class EntradaConversacion(BaseModel):
    clave: str = Field(pattern=r"^[a-z0-9-]+$")
    fecha: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    destino: Destino
    patron: str = Field(min_length=10)        # lo que pidió el usuario, en una frase
    propuesta: str = Field(min_length=10)     # la regla en que quedó
    evidencia: list[str] = Field(min_length=1)


def cargar_conversacion(raiz: Path) -> list[dict]:
    """Las reglas que salieron de las conversaciones de trabajo (config/memoria_conversacion.yaml), validadas.
    Las claves no se pueden repetir."""
    f = raiz / "config" / "memoria_conversacion.yaml"
    if not f.exists():
        return []
    entradas = [EntradaConversacion(**e) for e in (yaml.safe_load(f.read_text(encoding="utf-8")) or [])]
    claves = [e.clave for e in entradas]
    if len(claves) != len(set(claves)):
        raise ValueError(f"Claves repetidas en {f.name}: {sorted({c for c in claves if claves.count(c) > 1})}")
    return [e.model_dump() for e in entradas]


def _analizar(llm: LLM, cfg: Config, almacen: Almacen, dias: int, hoy: date | None) -> tuple[list[int], str, int]:
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
    out = ["# Memoria del feedback", "", "(«conversación»: decidido en una sesión de trabajo; el resto sale del análisis del feedback de la web)", ""]
    for estado, titulo in (("aceptada", "Aceptadas (pendientes de pasar a las reglas)"), ("propuesta", "Propuestas"),
                           ("aplicada", "Aplicadas"), ("rechazada", "Rechazadas")):
        grupo = [p for p in almacen.patrones() if p.estado == estado]
        if not grupo:
            continue
        out += [f"## {titulo}", ""]
        for p in grupo:
            origen = "conversación" if p.origen == "conversacion" else f"{p.veces} {'vez' if p.veces == 1 else 'veces'}"
            out += [f"- **{p.patron}** ({p.destino}, {origen}, #{p.id})", f"  - Regla: {p.propuesta}"]
            out += [f"  - {e}" for e in p.evidencia[:6]]
            if p.nota:
                out.append(f"  - Nota: {p.nota}")
        out.append("")
    return "\n".join(out)
