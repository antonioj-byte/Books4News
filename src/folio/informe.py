"""Informe diario: informe.json (datos completos) + informe.md (lectura)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from folio import evaluacion_md
from folio.modelos import HistoriaElegida, InformeDiario, LibroGuion, LibroVerificado, Pieza
from folio.guion import libro_verificado

_ESTADO = {"propuesta": "propuesta", "en_edicion": "en edición", "aprobada": "aprobada",
           "descartada": "descartada", "publicada": "publicada", "fallida": "FALLIDA"}
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


def _edicion_es_guion(lg: LibroGuion, libros: list[LibroVerificado]) -> str:
    """Estado de la edición española del libro del guion, según su ficha verificada."""
    v = libro_verificado(lg, libros)
    if v is None or v.edicion_es == "desconocido":
        return "no consta"
    if v.edicion_es == "no":
        return "no"
    return f"sí, {lg.editorial_espanola}" if lg.editorial_espanola else "sí (editorial no consta)"


def _pieza_md(p: Pieza) -> list[str]:
    e = p.eleccion
    l = [f"### {p.id} · {e.titular}", "",
         f"**Estado:** {_ESTADO[p.estado]}" + "".join(f" · ⚠️ {m}" for m in _marcas(p))
         + (" · historia de reserva" if p.reserva else "") + f" · {p.n_medios} medios", ""]
    if p.error:
        l += [f"> ⚠️ {p.error}", ""]
    l += [f"**De qué se habla.** {e.de_que_se_habla}", "",
          f"**Cuestión de fondo.** {e.cuestion_de_fondo}", ""]
    if e.gancho_libro:
        l += [f"**Gancho del libro.** {e.gancho_libro}", ""]
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
            if d.subtitulo:
                l.append(f"   Subtítulo ({len(d.subtitulo.split())} pal.) — {d.subtitulo}")
        l += ["", "**Pie de Instagram**", ""] + [f"> {linea}" if linea else ">" for linea in g.pie_instagram.split("\n")]
        if g.justificacion_extra:
            l += ["", "**Diapositivas por encima de 5**", ""] + [f"- {j}" for j in g.justificacion_extra]
        l += ["", "**Ficha de libros en el guion** (datos verificados)", ""]
        for lg in g.libros:
            l.append(f"- {lg.titulo} — {lg.autor} · ed. española: {_edicion_es_guion(lg, p.libros)}"
                     f" · trad.: {lg.traductor or 'no consta'} · original: {lg.edicion_original}")
        l.append("")
    if p.discrepancias_edicion:
        l += ["**Revisar edición**: el guionista dio datos distintos de los verificados. La ficha usa los "
              "verificados; comprueba que el texto de las diapositivas no arrastre los del modelo.", "",
              "| Libro | Campo | Guionista | Fuente bibliográfica |", "|---|---|---|---|"]
        l += [f"| {d.libro} | {d.campo} | {d.modelo} | {d.api} |" for d in p.discrepancias_edicion] + [""]
    if p.revision_humana:
        l += ["**Para revisión humana**", ""] + [f"- {r}" for r in p.revision_humana] + [""]
    no_verificados = [h for h in p.hechos if not h.verificado]
    if no_verificados:
        l += ["**Hechos no verificados**: datos de la noticia que no aparecen en los textos fuente. "
              "Corrígelos o quítalos antes de publicar.", "",
              "| Dónde | Tipo | Afirmación | Nota |", "|---|---|---|---|"]
        l += [f"| {h.donde} | {h.tipo} | {_celda(h.afirmacion)} | {_celda(h.nota or '')} |" for h in no_verificados] + [""]
    if p.hechos:
        l += [f"_Hechos comprobados contra las fuentes: {len(p.hechos) - len(no_verificados)} de {len(p.hechos)}._", ""]
    if p.arte:
        a = p.arte
        l += [f"**Arte**: tono {a.tono}, portada {a.portada}, {a.recurso}. "
              + (f"Ilustración: {a.concepto} " if a.concepto else "")
              + (f"Imagen de archivo: {a.credito}. " if a.credito else "Sin imagen de archivo. ")
              + (f"Cifra destacada: {a.cifra}" + (f" ({a.cifra_rotulo})" if a.cifra_rotulo else "") + ". " if a.cifra else ""), ""]
        creditos = ([f"Retrato: {a.retrato}"] if a.retrato else []) + \
                   ([f"{'Ilustración' if a.recurso == 'grabado' else 'Imagen'}: {a.credito}"] if a.credito else [])
        if creditos:
            l += [f"Añadir al pie de la publicación: «{'. '.join(creditos)}.»", ""]
        l += [f"- {x}" for x in a.avisos] + ([""] if a.avisos else [])
    if p.fuentes:
        l += ["**Fuentes**", ""]
        l += [f"- {f.medio} ({f.acceso}{', texto completo' if f.texto_completo else ', solo titular y entradilla'}): "
              f"[{f.titulo}]({f.url})" for f in p.fuentes] + [""]
    if p.avisos:
        l += ["**Avisos**", ""] + [f"- {a}" for a in p.avisos] + [""]
    if p.guion:
        l += _plantilla_evaluacion(p.id)
    return l


def _celda(texto: str) -> str:
    return texto.replace("|", "/").replace("\n", " ")


def _marcas(p: Pieza) -> list[str]:
    marcas = []
    if p.revisar_edicion:
        marcas.append("revisar edición")
    no_verificados = sum(not h.verificado for h in p.hechos)
    if no_verificados:
        marcas.append(f"{no_verificados} hecho{'s' if no_verificados > 1 else ''} no verificado{'s' if no_verificados > 1 else ''}")
    if p.revision_humana:
        marcas.append("revisión humana")
    return marcas


def _plantilla_evaluacion(pieza_id: str) -> list[str]:
    return evaluacion_md.bloque(f"evaluacion:{pieza_id}", evaluacion_md.CAMPOS_PIEZA,
                                cabecera=["**Evaluación** (rellenar a mano)", ""])


def evaluacion_rellenada(md: str) -> bool:
    """¿Hay alguna evaluación con algún campo rellenado en este informe?"""
    return evaluacion_md.rellenada(md, "evaluacion")


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
        l += ["", "## Llamadas a modelos", "",
              "| Paso | Modelo | Entrada | Caché (escritura / lectura) | Salida | Coste $ |", "|---|---|---|---|---|---|"]
        for t in inf.trazas:
            l.append(f"| {t.paso} | {t.modelo}{' · ' + t.nota if t.nota else ''} | {t.tokens_entrada} | "
                     f"{t.tokens_cache_escritura} / {t.tokens_cache_lectura} | {t.tokens_salida} | {t.coste_usd:.4f} |")
    return "\n".join(l) + "\n"


def escribir(inf: InformeDiario, directorio: Path) -> tuple[Path, Path]:
    directorio.mkdir(parents=True, exist_ok=True)
    ruta_json = directorio / "informe.json"
    ruta_md = directorio / "informe.md"
    if ruta_md.exists() and evaluacion_rellenada(ruta_md.read_text(encoding="utf-8")):
        # Relanzar el mismo día no puede borrar las notas puestas a mano.
        copia = directorio / f"informe.evaluado-{datetime.now():%H%M%S}.md"
        ruta_md.rename(copia)
        inf.avisos.append(f"El informe anterior tenía evaluaciones rellenadas: se ha guardado en {copia.name}")
    ruta_json.write_text(inf.model_dump_json(indent=2), encoding="utf-8")
    ruta_md.write_text(markdown(inf), encoding="utf-8")
    return ruta_json, ruta_md
