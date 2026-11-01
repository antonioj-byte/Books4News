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


NOMBRES_FORMATO = {"lateral": "lectura lateral", "dialogo": "diálogo con la actualidad", "edicion": "mundo del libro",
                   "curiosidad": "historia editorial", "recomendado": "libro recomendado", "radar": "radar del libro"}
_EN_EL_REPARTO = {"lateral": "de lectura lateral", "dialogo": "de diálogo con la actualidad", "edicion": "del mundo del libro",
                  "curiosidad": "de historia editorial (del cajón)", "recomendado": "de libro recomendado"}
# El carril del que tiene que salir cada formato que no es de actualidad
_CARRIL_DEL_FORMATO = {"curiosidad": "cajon", "recomendado": "catalogo"}


def bloque_cajon(historias: list[Historia]) -> str:
    """Las curiosidades del cajón que se pueden usar hoy: sin fecha ni medios, que no son noticias."""
    if not historias:
        return "<cajon_de_curiosidades>\n(ninguna disponible hoy)\n</cajon_de_curiosidades>"
    partes = [f"- id: {h.id}\n  titular: {h.titular_es}\n  resumen: {h.resumen_es}\n  fuentes: {', '.join(h.medios)}"
              for h in historias]
    return "<cajon_de_curiosidades>\n" + "\n\n".join(partes) + "\n</cajon_de_curiosidades>"


def reparto_del_dia(reparto: dict[str, int], historias: list[Historia]) -> dict[str, int]:
    """El reparto de la configuración, sin la curiosidad si el cajón no tiene ninguna disponible hoy ni el
    recomendado si el catálogo no ha dado candidatos."""
    carriles = {h.carril for h in historias}
    return {f: n for f, n in reparto.items() if f not in _CARRIL_DEL_FORMATO or _CARRIL_DEL_FORMATO[f] in carriles}


def bloque_catalogo(historias: list[Historia]) -> str:
    """Las novedades de las editoriales independientes: título, autor, editorial, fecha y sinopsis."""
    if not historias:
        return "<catalogo>\n(ninguna novedad disponible hoy)\n</catalogo>"
    partes = [f"- id: {h.id}\n  libro: {h.titular_es}\n  sinopsis: {h.resumen_es}" for h in historias]
    return "<catalogo>\n" + "\n\n".join(partes) + "\n</catalogo>"
# Las propuestas de la mesa (seis, con 3–4 libros cada una) y el razonamiento del modelo no caben en
# 16.000 tokens; 21.000 es lo máximo que el SDK permite sin streaming
MAX_TOKENS_SELECCION = 21000


def texto_reparto(reparto: dict[str, int]) -> str:
    """«2 de lectura lateral, 2 de diálogo con la actualidad y 2 del mundo del libro»."""
    partes = [f"{n} {_EN_EL_REPARTO[f]}" for f, n in reparto.items() if n]
    return ", ".join(partes[:-1]) + (" y " if len(partes) > 1 else "") + partes[-1]


def _validar(sel: SeleccionJefe, carriles: dict[str, str], cfg, reparto: dict[str, int]) -> tuple[list[str], dict[str, int]]:
    """Quita las propuestas con ids inexistentes (o que mezclan el cajón de curiosidades con otro formato)
    y recorta lo que sobra. `carriles`: id de historia → carril. Devuelve los avisos y lo que falta de
    cada formato del reparto."""
    avisos: list[str] = []
    for grupo in ("elegidas", "reserva"):
        validas = []
        for e in getattr(sel, grupo):
            if e.historia_id not in carriles:
                avisos.append(f"El jefe de cultura devolvió un id inexistente ({e.historia_id}); se descarta «{e.titular}»")
                continue
            carril = carriles[e.historia_id]
            if carril == "radar" or any((carril == c) != (e.formato == f) for f, c in _CARRIL_DEL_FORMATO.items()):
                avisos.append(f"«{e.titular}»: la curiosidad tiene que salir del cajón y el recomendado del catálogo (y "
                              "cada uno solo sirve para su formato); se descarta")
                continue
            minimo = {"curiosidad": 0, "recomendado": 1}.get(e.formato, 3)
            if not minimo <= len(e.libros_candidatos) <= 4:
                avisos.append(f"«{e.titular}»: {len(e.libros_candidatos)} libros candidatos (se pedían {minimo}–4)")
            validas.append(e)
        setattr(sel, grupo, validas)
    faltan = {}
    for formato, n in reparto.items():
        hay = sum(e.formato == formato for e in sel.elegidas)
        if hay != n:
            avisos.append(f"Propuestas {_EN_EL_REPARTO[formato]}: {hay} (se pedían {n})")
        if hay < n:
            faltan[formato] = n - hay
    maximo = cfg["elegidas"] - sum(n for f, n in cfg.reparto.items() if f not in reparto)
    if len(sel.elegidas) > maximo:
        avisos.append(f"Se recibieron {len(sel.elegidas)} elegidas; se usan las {maximo} primeras")
        sel.elegidas = sel.elegidas[:maximo]
    if len(sel.reserva) > cfg["reserva"]:
        sel.reserva = sel.reserva[: cfg["reserva"]]
    return avisos, faltan


def seleccionar(llm: LLM, historias: list[Historia], fecha: str) -> tuple[SeleccionJefe, list[str]]:
    """Devuelve las propuestas del día y avisos de validación (ids desconocidos, recuentos, reparto).
    Si falta algún formato del reparto (el 1/11 salieron 5 de 6), se le pide al jefe una vez, en la misma
    conversación, que complete la mesa; si tampoco puede, se sigue con lo que hay y queda el aviso."""
    cfg = llm.cfg.pipeline.seleccion
    reparto = reparto_del_dia(cfg.reparto, historias)
    prompt = cargar_prompt(llm.cfg, "jefe_cultura", {
        "[pegar reparto]": texto_reparto(reparto),
        "[pegar año mínimo]": str(anio_minimo(fecha, cfg.antiguedad_libros)),
        "[pegar lista]": bloque_historias([h for h in historias if h.carril == "actualidad"]),
        "[pegar lista editorial]": bloque_historias([h for h in historias if h.carril == "editorial"], "mundo_del_libro"),
        "[pegar cajón]": bloque_cajon([h for h in historias if h.carril == "cajon"]),
        "[pegar catálogo]": bloque_catalogo([h for h in historias if h.carril == "catalogo"]),
    })
    mensajes = [{"role": "user", "content": prompt}]
    sel, contenido = llm.estructurado("seleccion", mensajes, SeleccionJefe,
                                      etapa_modelo="seleccion", max_tokens=MAX_TOKENS_SELECCION)
    carriles = {h.id: h.carril for h in historias}
    avisos, faltan = _validar(sel, carriles, cfg, reparto)
    if faltan and sel.elegidas:
        pedido = texto_reparto(faltan)
        mensajes += [{"role": "assistant", "content": contenido},
                     {"role": "user", "content": f"Falta completar el reparto: {pedido}. Devuelve la mesa entera, con las "
                      "propuestas que ya diste (en el mismo orden) y las que faltan, eligiendo historias de las listas. "
                      "Si de verdad no hay ninguna buena para ese formato, dilo en «aviso»."}]
        try:
            otra, _ = llm.estructurado("seleccion-completar", mensajes, SeleccionJefe,
                                       etapa_modelo="seleccion", max_tokens=MAX_TOKENS_SELECCION)
        except ErrorLLM as exc:
            avisos.append(f"No se pudo completar la mesa ({exc}); se sigue con {len(sel.elegidas)} propuestas")
        else:
            avisos2, faltan2 = _validar(otra, carriles, cfg, reparto)
            if len(otra.elegidas) > len(sel.elegidas):
                sel = otra
                avisos = [f"La primera mesa traía {texto_reparto(faltan)} de menos; el jefe la ha completado"] + avisos2
            else:
                avisos.append("El jefe no pudo completar la mesa" + (f": {otra.aviso}" if otra.aviso else ""))
    if not sel.elegidas and not sel.reserva:
        if sel.aviso:
            return sel, avisos
        raise ErrorLLM("El jefe de cultura no eligió ninguna historia válida")
    return sel, avisos
