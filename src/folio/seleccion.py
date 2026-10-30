"""Agente «jefe de cultura» (prompts/jefe_cultura.md)."""

from __future__ import annotations

from folio.llm import LLM, ErrorLLM, cargar_prompt
from folio.modelos import Historia, SeleccionJefe


def _desde(h: Historia) -> str:
    """Fecha del artículo más antiguo del grupo: el jefe la usa para no tratar en caliente un suceso doloroso."""
    fechas = [a.publicado_en for a in h.articulos if a.publicado_en]
    return min(fechas).strftime("%Y-%m-%d %H:%M UTC") if fechas else "desconocida"


def bloque_historias(historias: list[Historia]) -> str:
    partes = []
    for h in historias:
        titulares = "\n".join(f"    · [{a.medio}] {a.titulo}" for a in h.articulos[:5])
        partes.append(
            f"- id: {h.id}\n"
            f"  titular: {h.titular_es}\n"
            f"  resumen: {h.resumen_es}\n"
            f"  sección: {h.seccion}\n"
            f"  medios que la cubren ({h.n_medios}): {', '.join(h.medios)}\n"
            f"  publicada desde: {_desde(h)}\n"
            f"  titulares originales:\n{titulares}"
        )
    return "<historias>\n" + "\n\n".join(partes) + "\n</historias>"


def seleccionar(llm: LLM, historias: list[Historia]) -> tuple[SeleccionJefe, list[str]]:
    """Devuelve la selección y avisos de validación (ids desconocidos, recuentos)."""
    cfg = llm.cfg.pipeline.seleccion
    prompt = cargar_prompt(llm.cfg, "jefe_cultura", {"[pegar lista]": bloque_historias(historias)})
    sel, _ = llm.estructurado("seleccion", [{"role": "user", "content": prompt}], SeleccionJefe,
                              etapa_modelo="seleccion")

    avisos: list[str] = []
    ids = {h.id for h in historias}
    for grupo in ("elegidas", "reserva"):
        validas = []
        for e in getattr(sel, grupo):
            if e.historia_id not in ids:
                avisos.append(f"El jefe de cultura devolvió un id inexistente ({e.historia_id}); se descarta «{e.titular}»")
                continue
            if not 2 <= len(e.libros_candidatos) <= 3:
                avisos.append(f"«{e.titular}»: {len(e.libros_candidatos)} libros candidatos (se pedían 2–3)")
            validas.append(e)
        setattr(sel, grupo, validas)
    if len(sel.elegidas) > cfg["elegidas"]:
        avisos.append(f"Se recibieron {len(sel.elegidas)} elegidas; se usan las {cfg['elegidas']} primeras")
        sel.elegidas = sel.elegidas[: cfg["elegidas"]]
    if len(sel.reserva) > cfg["reserva"]:
        sel.reserva = sel.reserva[: cfg["reserva"]]
    if not sel.elegidas and not sel.reserva:
        if sel.aviso:
            return sel, avisos
        raise ErrorLLM("El jefe de cultura no eligió ninguna historia válida")
    return sel, avisos
