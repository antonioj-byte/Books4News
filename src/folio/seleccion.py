"""Agente «jefe de cultura» (prompts/jefe_cultura.md)."""

from __future__ import annotations

from folio.llm import LLM, ErrorLLM, cargar_prompt
from folio.modelos import Historia, SeleccionJefe


def _desde(h: Historia) -> str:
    """Fecha del artículo más antiguo del grupo: el jefe la usa para no tratar en caliente un suceso doloroso."""
    fechas = [a.publicado_en for a in h.articulos if a.publicado_en]
    return min(fechas).strftime("%Y-%m-%d %H:%M UTC") if fechas else "desconocida"


def bloque_historias(historias: list[Historia], etiqueta: str = "historias") -> str:
    if not historias:
        return f"<{etiqueta}>\n(ninguna hoy)\n</{etiqueta}>"
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
    return f"<{etiqueta}>\n" + "\n\n".join(partes) + f"\n</{etiqueta}>"


def anio_minimo(fecha: str, anios: int) -> int:
    """El año de publicación más antiguo que cuenta como novedad el día `fecha`."""
    return int(fecha[:4]) - anios


NOMBRES_FORMATO = {"lateral": "lectura lateral", "dialogo": "diálogo con la actualidad", "edicion": "mundo del libro"}
_EN_EL_REPARTO = {"lateral": "de lectura lateral", "dialogo": "de diálogo con la actualidad", "edicion": "del mundo del libro"}
# Las propuestas de la mesa (seis, con 3–4 libros cada una) y el razonamiento del modelo no caben en
# 16.000 tokens; 21.000 es lo máximo que el SDK permite sin streaming
MAX_TOKENS_SELECCION = 21000


def texto_reparto(reparto: dict[str, int]) -> str:
    """«2 de lectura lateral, 2 de diálogo con la actualidad y 2 del mundo del libro»."""
    partes = [f"{n} {_EN_EL_REPARTO[f]}" for f, n in reparto.items() if n]
    return ", ".join(partes[:-1]) + (" y " if len(partes) > 1 else "") + partes[-1]


def seleccionar(llm: LLM, historias: list[Historia], fecha: str) -> tuple[SeleccionJefe, list[str]]:
    """Devuelve las propuestas del día y avisos de validación (ids desconocidos, recuentos, reparto)."""
    cfg = llm.cfg.pipeline.seleccion
    prompt = cargar_prompt(llm.cfg, "jefe_cultura", {
        "[pegar reparto]": texto_reparto(cfg.reparto),
        "[pegar año mínimo]": str(anio_minimo(fecha, cfg.antiguedad_libros)),
        "[pegar lista]": bloque_historias([h for h in historias if h.carril == "actualidad"]),
        "[pegar lista editorial]": bloque_historias([h for h in historias if h.carril == "editorial"], "mundo_del_libro"),
    })
    sel, _ = llm.estructurado("seleccion", [{"role": "user", "content": prompt}], SeleccionJefe,
                              etapa_modelo="seleccion", max_tokens=MAX_TOKENS_SELECCION)

    avisos: list[str] = []
    ids = {h.id for h in historias}
    for grupo in ("elegidas", "reserva"):
        validas = []
        for e in getattr(sel, grupo):
            if e.historia_id not in ids:
                avisos.append(f"El jefe de cultura devolvió un id inexistente ({e.historia_id}); se descarta «{e.titular}»")
                continue
            if not 3 <= len(e.libros_candidatos) <= 4:
                avisos.append(f"«{e.titular}»: {len(e.libros_candidatos)} libros candidatos (se pedían 3–4)")
            validas.append(e)
        setattr(sel, grupo, validas)
    for formato, n in cfg.reparto.items():
        hay = sum(e.formato == formato for e in sel.elegidas)
        if hay != n:
            avisos.append(f"Propuestas {_EN_EL_REPARTO[formato]}: {hay} (se pedían {n})")
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
