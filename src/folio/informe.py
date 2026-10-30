"""Informe diario: informe.json (datos completos) + informe.md (lectura)."""

from __future__ import annotations

from pathlib import Path

from folio.modelos import HistoriaElegida, InformeDiario, LibroVerificado, Pieza

_ESTADO = {"propuesta": "propuesta", "en_edicion": "en edición", "aprobada": "aprobada",
           "publicada": "publicada", "fallida": "FALLIDA"}
_EDICION_ES = {"si": "sí", "no": "no", "desconocido": "no consta"}


def _libro_md(l: LibroVerificado) -> list[str]:
    original = ", ".join(x for x in (
        l.idioma_original, l.editorial_original, str(l.anio_primera_edicion) if l.anio_primera_edicion else None
    ) if x)
    lineas = [f"- **{l.titulo_propuesto}** — {', '.join(l.autores[:3])}"
              + (f" · título en la ficha: *{l.titulo}*" if l.titulo != l.titulo_propuesto else "")
              + (f" · primera edición: {original}" if original else "")]
    es = _EDICION_ES[l.edicion_es]
    if l.edicion_es_detalle:
        d = l.edicion_es_detalle
        es += " — " + ", ".join(x for x in (d.titulo, d.editorial, d.anio, d.pais,
                                            f"ISBN {d.isbn}" if d.isbn else None,
                                            f"trad. {d.traductor}" if d.traductor else None) if x)
    lineas.append(f"  - Edición española: {es}")
    enlace = f" · [ficha]({l.url_ficha})" if l.url_ficha else ""
    lineas.append(f"  - Verificado en {', '.join(l.fuentes_verificacion)} (confianza {l.confianza}){enlace}")
    for n in l.notas:
        lineas.append(f"  - _{n}_")
    return lineas


def _pieza_md(p: Pieza) -> list[str]:
    e = p.eleccion
    l = [f"### {p.id} · {e.titular}", "",
         f"**Estado:** {_ESTADO[p.estado]}" + (" · ⚠️ revisar edición" if p.revisar_edicion else "")
         + (" · historia de reserva" if p.reserva else "") + f" · {p.n_medios} medios", ""]
    if p.error:
        l += [f"> ⚠️ {p.error}", ""]
    l += [f"**De qué se habla.** {e.de_que_se_habla}", "",
          f"**Cuestión de fondo.** {e.cuestion_de_fondo}", ""]
    if p.libros:
        l += ["**Libros verificados**", ""] + [x for libro in p.libros for x in _libro_md(libro)] + [""]
    if p.libros_descartados:
        l += ["**Libros descartados**", ""]
        l += [f"- {d.titulo} — {d.autor}: {d.motivo}" for d in p.libros_descartados] + [""]
    g = p.guion
    if g:
        l += ["**Idea nueva**", ""]
        l += [f"{i}. {c}" for i, c in enumerate(g.idea_nueva_candidatas, 1)]
        l += ["", f"Elegida: **{g.idea_elegida}** — {g.por_que}", "", "**Carrusel**", ""]
        for d in g.diapositivas:
            l.append(f"{d.n}. _{d.tipo}_ ({len(d.texto.split())} pal.) — {d.texto}")
        l += ["", "**Pie de Instagram**", ""] + [f"> {linea}" if linea else ">" for linea in g.pie_instagram.split("\n")]
        if g.justificacion_extra:
            l += ["", "**Diapositivas por encima de 5**", ""] + [f"- {j}" for j in g.justificacion_extra]
        l += ["", "**Ficha de libros en el guion** (datos verificados)", ""]
        for lg in g.libros:
            l.append(f"- {lg.titulo} — {lg.autor} · ed. española: {lg.editorial_espanola or 'no consta'}"
                     f" · trad.: {lg.traductor or 'no consta'} · original: {lg.edicion_original}")
        l.append("")
    if p.discrepancias_edicion:
        l += ["**Revisar edición**: el guionista dio datos distintos de los verificados. La ficha usa los "
              "verificados; comprueba que el texto de las diapositivas no arrastre los del modelo.", "",
              "| Libro | Campo | Guionista | Fuente bibliográfica |", "|---|---|---|---|"]
        l += [f"| {d.libro} | {d.campo} | {d.modelo} | {d.api} |" for d in p.discrepancias_edicion] + [""]
    if p.fuentes:
        l += ["**Fuentes**", ""]
        l += [f"- {f.medio} ({f.acceso}{', texto completo' if f.texto_completo else ', solo titular y entradilla'}): "
              f"[{f.titulo}]({f.url})" for f in p.fuentes] + [""]
    if p.avisos:
        l += ["**Avisos**", ""] + [f"- {a}" for a in p.avisos] + [""]
    return l


def _eleccion_md(e: HistoriaElegida) -> str:
    def _c(c):
        original = ", ".join(x for x in (c.titulo_original if c.titulo_original != c.titulo else None,
                                         c.idioma_original) if x)
        return f"{c.titulo} ({c.autor}{'; ' + original if original else ''})"
    libros = "; ".join(_c(c) for c in e.libros_candidatos)
    return f"- **{e.titular}** (`{e.historia_id}`) — {e.por_que} · Libros: {libros}"


def markdown(inf: InformeDiario) -> str:
    s = inf.stats
    l = [f"# Folio Lateral · {inf.fecha}", "",
         f"Generado: {inf.generado_en:%Y-%m-%d %H:%M} UTC · {s.get('articulos', 0)} artículos de "
         f"{s.get('medios', 0)} medios · {s.get('historias', 0)} historias "
         f"({s.get('historias_multimedio', 0)} en 2 o más medios) · coste estimado {inf.coste_total_usd:.2f} $", ""]
    if inf.avisos:
        l += ["## Avisos", ""] + [f"- {a}" for a in inf.avisos] + [""]
    if inf.piezas:
        l += ["## Piezas", ""]
        for p in inf.piezas:
            l += _pieza_md(p)
    if inf.seleccion:
        l += ["## Selección del jefe de cultura", ""]
        if inf.seleccion.aviso:
            l += [f"> {inf.seleccion.aviso}", ""]
        l += ["**Elegidas**", ""] + [_eleccion_md(e) for e in inf.seleccion.elegidas] + [""]
        if inf.seleccion.reserva:
            l += ["**Reserva**", ""] + [_eleccion_md(e) for e in inf.seleccion.reserva] + [""]
    l += ["## Historias del día", "", "| # | Titular | Sección | Medios | Nota |", "|---|---|---|---|---|"]
    for i, h in enumerate(inf.top_historias, 1):
        titular = (h.titular_es or "").replace("|", "/")
        l.append(f"| {i} | {titular} | {h.seccion or ''} | {h.n_medios}: {', '.join(h.medios)} | {h.excluida or ''} |")
    if inf.trazas:
        l += ["", "## Llamadas a modelos", "", "| Paso | Modelo | Entrada | Salida | Coste $ |", "|---|---|---|---|---|"]
        for t in inf.trazas:
            l.append(f"| {t.paso} | {t.modelo}{' · ' + t.nota if t.nota else ''} | {t.tokens_entrada} | "
                     f"{t.tokens_salida} | {t.coste_usd:.4f} |")
    return "\n".join(l) + "\n"


def escribir(inf: InformeDiario, directorio: Path) -> tuple[Path, Path]:
    directorio.mkdir(parents=True, exist_ok=True)
    ruta_json = directorio / "informe.json"
    ruta_md = directorio / "informe.md"
    ruta_json.write_text(inf.model_dump_json(indent=2), encoding="utf-8")
    ruta_md.write_text(markdown(inf), encoding="utf-8")
    return ruta_json, ruta_md
