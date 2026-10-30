"""Agente «guionista» (prompts/guionista.md) y comprobaciones del guion.

El guion se valida en código: extensión, estructura, citas entre comillas, libros y fuentes.
Si no pasa, se reintenta una vez con la lista de errores; si vuelve a fallar, la pieza queda
como fallida. Los datos de edición de los libros se sustituyen siempre por los verificados.
"""

from __future__ import annotations

import re

from folio.config import Config
from folio.llm import LLM, bloque_reenviable, cargar_prompt, con_cache
from folio.modelos import DiscrepanciaEdicion, FuenteNoticia, GuionLLM, HistoriaElegida, LibroGuion, LibroVerificado
from folio.verificacion_texto import apellido, autor_coincide, normalizar, sin_subtitulo, titulos_coinciden

_COMILLAS = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"")
_URL = re.compile(r"https?://\S+")
_FRASES_VETADAS = ("en un mundo donde", "en un mundo en el que")
# Afirmaciones sobre traducción: solo valen si algún libro tiene «no hay edición española» verificado.
_SOBRE_TRADUCCION = re.compile(
    r"sin traduc|no traducid|no (?:est[aá]n?|ha sido|han sido) traducid|no constan? traducid|"
    r"sin edici[oó]n (?:en )?espa|a[uú]n no hay edici|in[eé]dit[oa]s? en (?:espa|castellano)|"
    r"l[eé]el[oa]s? en (?:ingl[eé]s|el original)",
    re.IGNORECASE,
)


def afirmaciones_traduccion(g: GuionLLM) -> list[str]:
    """Frases del guion que afirman que un libro no está traducido. Siempre van a revisión humana:
    se apoyan en que dos catálogos no tengan la edición, y los catálogos tienen huecos."""
    textos = [(f"diapositiva {x.n}", x.texto) for x in g.diapositivas] + [("pie", g.pie_instagram)]
    return [f"{donde}: «{m.group(0)}…»" for donde, t in textos for m in _SOBRE_TRADUCCION.finditer(t)]
_ANIO = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
# Palabras que no distinguen una editorial de otra.
_GENERICAS_EDITORIAL = {
    "editorial", "ediciones", "edicions", "edizioni", "editions", "editores", "books", "press",
    "publishing", "publishers", "inc", "ltd", "limited", "llc", "co", "company", "sa", "sl", "s", "a", "l",
    "verlag", "grupo", "group", "de", "del", "the", "and", "y", "house",
}


def titulo_para_pieza(l: LibroVerificado) -> str:
    """El título español si hay edición española; si no, el de la ficha (el original)."""
    if l.edicion_es == "si":
        if l.edicion_es_detalle and l.edicion_es_detalle.titulo:
            # Las fichas traen a veces «Siempre Alice / Still Alice» o «El poder de los sin poder: Václav Havel»
            titulo = l.edicion_es_detalle.titulo.split(" / ")[0].strip()
            base, _, sub = titulo.partition(":")
            if sub and any(autor_coincide(sub, [a]) for a in l.autores):
                titulo = base.strip()
            return titulo
        return l.titulo_propuesto
    return l.titulo


def _linea_libro(l: LibroVerificado) -> str:
    original = ", ".join(x for x in (
        l.idioma_original, l.editorial_original,
        str(l.anio_primera_edicion) if l.anio_primera_edicion else None,
    ) if x) or "sin datos"
    if l.edicion_es == "si" and l.edicion_es_detalle:
        d = l.edicion_es_detalle
        es = ", ".join(x for x in (d.titulo, d.editorial, d.anio, f"trad. {d.traductor}" if d.traductor else None) if x)
        es = f"sí ({es})"
    elif l.edicion_es == "no":
        es = "no hay edición española (verificado: puedes presentarlo como libro todavía sin traducir)"
    else:
        es = "no consta (no digas nada sobre su traducción)"
    return (
        f"- Título que debes usar en la pieza: {titulo_para_pieza(l)}\n"
        f"  Título propuesto: {l.titulo_propuesto}\n"
        f"  Título en la ficha: {l.titulo}\n"
        f"  Autor(es): {', '.join(l.autores)}\n"
        f"  Primera edición: {original}\n"
        f"  Edición española: {es}"
    )


def construir_prompt(cfg: Config, eleccion: HistoriaElegida, textos: list[tuple[FuenteNoticia, str]],
                     libros: list[LibroVerificado]) -> str:
    fuentes = "\n".join(
        f'<fuente medio="{f.medio}" url="{f.url}" acceso="{f.acceso}">\n{t}\n</fuente>' for f, t in textos
    )
    noticia = (
        "\n<noticia>\n"
        f"Titular: {eleccion.titular}\n"
        f"De qué se está hablando: {eleccion.de_que_se_habla}\n"
        f"Cuestión de fondo (propuesta del jefe de cultura): {eleccion.cuestion_de_fondo}\n"
        f"Textos de los medios:\n{fuentes}\n"
        "</noticia>"
    )
    libros_txt = (
        "\n<libros_verificados>\n" + "\n".join(_linea_libro(l) for l in libros) + "\n</libros_verificados>\n"
        "Usa solo estos libros, que se han verificado en catálogos bibliográficos."
    )
    return cargar_prompt(cfg, "guionista", {
        "[pegar]": noticia,
        "[pegar o «propón tú»]": libros_txt,
    })


def _menciona_libro(texto: str, libros: list[LibroVerificado]) -> bool:
    """¿Nombra el texto a algún autor (apellido) o algún título de los libros verificados?"""
    palabras = set(normalizar(texto).split())
    tn = f" {normalizar(texto)} "
    for l in libros:
        if any(len(apellido(a)) >= 3 and apellido(a) in palabras for a in l.autores):
            return True
        for t in {l.titulo, l.titulo_propuesto, titulo_para_pieza(l)}:
            nt = normalizar(sin_subtitulo(t))
            if len(nt) >= 4 and f" {nt} " in tn:
                return True
    return False


def _palabras(texto: str) -> int:
    return len(texto.split())


def _es_titulo_de_libro(fragmento: str, libros: list[LibroVerificado]) -> bool:
    for l in libros:
        titulos = [l.titulo, l.titulo_propuesto, titulo_para_pieza(l)]
        if l.edicion_es_detalle and l.edicion_es_detalle.titulo:
            titulos.append(l.edicion_es_detalle.titulo)
        if any(titulos_coinciden(fragmento, t, umbral=0.9) for t in titulos):
            return True
    return False


def libro_verificado(lg: LibroGuion, libros: list[LibroVerificado]) -> LibroVerificado | None:
    """La ficha verificada de un libro del guion: mismo autor (apellido) y uno de sus títulos (el
    de la ficha, el propuesto, el que se usa en la pieza o el de la edición española). Es el único
    criterio para emparejarlos: lo usan la validación, la ficha del informe, el PNG y el pipeline."""
    return next((l for l in libros if autor_coincide(lg.autor, l.autores) and _es_titulo_de_libro(lg.titulo, [l])), None)


def validar(cfg: Config, g: GuionLLM, libros: list[LibroVerificado], fuentes: list[FuenteNoticia]) -> list[str]:
    p = cfg.pipeline.guion
    errores: list[str] = []
    d = g.diapositivas

    if not 4 <= len(d) <= 7:
        errores.append(f"Hay {len(d)} diapositivas; deben ser entre 4 y 7.")
    extra = len(d) - p.diapositivas_por_defecto
    if extra > 0 and len([j for j in g.justificacion_extra if j.strip()]) < extra:
        errores.append(
            f"Hay {len(d)} diapositivas: justifica en justificacion_extra, con una línea cada una, "
            f"qué aporta cada una de las {extra} por encima de {p.diapositivas_por_defecto}, o recorta."
        )
    if [x.n for x in d] != list(range(1, len(d) + 1)):
        errores.append("Las diapositivas deben numerarse 1, 2, 3… sin saltos.")
    if d and d[0].tipo != "portada":
        errores.append("La diapositiva 1 debe ser de tipo «portada».")
    if d and d[-1].tipo != "cierre":
        errores.append("La última diapositiva debe ser de tipo «cierre».")
    for tipo in ("actualidad", "libro", "idea"):
        if not any(x.tipo == tipo for x in d):
            errores.append(f"Falta una diapositiva de tipo «{tipo}».")
    for x in d:
        limite = p.palabras_max_portada if x.tipo == "portada" else p.palabras_max_diapositiva
        if _palabras(x.texto) > limite:
            errores.append(f"La diapositiva {x.n} ({x.tipo}) tiene {_palabras(x.texto)} palabras; máximo {limite}.")
    # La noticia abre la pieza, el libro entra pronto y protagoniza el cierre.
    if d and d[0].tipo == "portada" and _menciona_libro(d[0].texto, libros):
        errores.append("La portada abre con la noticia o con su tensión, no con el libro: quita el título y el autor.")
    if d and d[-1].tipo == "cierre" and not _menciona_libro(d[-1].texto, libros):
        errores.append("El cierre es la recomendación: nombra el libro (título en cursiva) y a su autor.")
    n_actualidad = sum(x.tipo == "actualidad" for x in d)
    if n_actualidad > p.max_diapositivas_actualidad:
        errores.append(f"Hay {n_actualidad} diapositivas de actualidad; máximo {p.max_diapositivas_actualidad}. "
                       "La noticia es la excusa: resúmela.")
    primer_libro = next((x.n for x in d if x.tipo == "libro"), None)
    if primer_libro and primer_libro > p.posicion_max_primer_libro:
        errores.append(f"El libro entra en la diapositiva {primer_libro}; debe hacerlo como muy tarde en la "
                       f"{p.posicion_max_primer_libro}.")
    if not _menciona_libro(g.pie_instagram, libros):
        errores.append("El pie debe nombrar el libro que recomienda la pieza.")
    if d and d[0].texto.strip().endswith("?"):
        errores.append("La portada no puede ser una pregunta retórica.")
    if d and "folio" not in normalizar(d[-1].texto).split():
        errores.append("El cierre debe llevar la firma de Folio.")

    textos = [x.texto for x in d] + [g.pie_instagram]
    for t in textos:
        tn = t.lower()
        for frase in _FRASES_VETADAS:
            if frase in tn:
                errores.append(f"Frase vetada: «{frase}…».")
        for m in _COMILLAS.finditer(t):
            fragmento = next(s for s in m.groups() if s)
            if not _es_titulo_de_libro(fragmento, libros):
                errores.append(
                    f"Texto entre comillas que no es el título de un libro: «{fragmento[:80]}». "
                    "No se permiten citas: parafrasea sin comillas."
                )

    if not any(l.edicion_es == "no" for l in libros):
        for t in textos:
            m = _SOBRE_TRADUCCION.search(t)
            if m:
                errores.append(
                    f"«{m.group(0)}»: ningún libro tiene verificado que no haya edición española; "
                    "no digas nada sobre su traducción."
                )

    n_pie = _palabras(g.pie_instagram)
    if not p.pie_min_palabras <= n_pie <= p.pie_max_palabras:
        errores.append(f"El pie tiene {n_pie} palabras; debe tener entre {p.pie_min_palabras} y {p.pie_max_palabras}.")
    if not any(normalizar(f.medio) in normalizar(g.pie_instagram) for f in fuentes):
        errores.append("El pie debe citar el medio de la noticia (uno de: " + ", ".join(f.medio for f in fuentes) + ").")

    if not g.libros:
        errores.append("Falta la lista de libros.")
    for lg in g.libros:
        if libro_verificado(lg, libros) is None:
            errores.append(f"El libro «{lg.titulo}» de {lg.autor} no está entre los verificados.")

    urls_validas = {f.url for f in fuentes}
    for fn in g.fuentes_noticia:
        urls = _URL.findall(fn)
        if not urls or any(u.rstrip(".,;)") not in urls_validas for u in urls):
            errores.append(f"Fuente no reconocida: «{fn}». Usa solo los medios y URLs de los textos recibidos.")
    if not g.fuentes_noticia:
        errores.append("Falta fuentes_noticia.")
    return errores


def _nucleo_editorial(nombre: str) -> set[str]:
    return {p for p in normalizar(nombre).split() if p not in _GENERICAS_EDITORIAL}


def _editoriales_coinciden(a: str, b: str) -> bool:
    na, nb = _nucleo_editorial(a), _nucleo_editorial(b)
    if not na or not nb:
        return normalizar(a) == normalizar(b)
    return bool(na & nb)


def _partes_original(texto: str) -> tuple[str | None, str | None]:
    """(editorial, año) de «idioma, editorial, año» tal como lo escribe el guionista."""
    anio_m = _ANIO.search(texto or "")
    partes = [x.strip() for x in (texto or "").split(",") if x.strip()]
    partes = [x for x in partes if not _ANIO.fullmatch(x)]
    editorial = ", ".join(partes[1:]) if len(partes) >= 2 else None
    return editorial, anio_m.group(1) if anio_m else None


def comparar_edicion(g: GuionLLM, libros: list[LibroVerificado]) -> list[DiscrepanciaEdicion]:
    """Datos de edición del guionista que no coinciden con los verificados (editorial, traductor, año)."""
    out: list[DiscrepanciaEdicion] = []
    for lg in g.libros:
        l = libro_verificado(lg, libros)
        if l is None:
            continue
        d = l.edicion_es_detalle if l.edicion_es == "si" else None
        api_es = d.editorial if d else None
        if lg.editorial_espanola and (not api_es or not _editoriales_coinciden(lg.editorial_espanola, api_es)):
            out.append(DiscrepanciaEdicion(libro=lg.titulo, campo="editorial española", modelo=lg.editorial_espanola,
                                           api=api_es or "sin edición española verificada"))
        api_trad = d.traductor if d else None
        if lg.traductor and (not api_trad or not autor_coincide(lg.traductor, [api_trad])):
            out.append(DiscrepanciaEdicion(libro=lg.titulo, campo="traductor", modelo=lg.traductor,
                                           api=api_trad or "sin traductor verificado"))
        editorial_m, anio_m = _partes_original(lg.edicion_original)
        if editorial_m and l.editorial_original and not _editoriales_coinciden(editorial_m, l.editorial_original):
            out.append(DiscrepanciaEdicion(libro=lg.titulo, campo="editorial original", modelo=editorial_m,
                                           api=l.editorial_original))
        if anio_m and l.anio_primera_edicion and anio_m != str(l.anio_primera_edicion):
            out.append(DiscrepanciaEdicion(libro=lg.titulo, campo="año original", modelo=anio_m,
                                           api=str(l.anio_primera_edicion)))
    return out


def corregir_mecanico(g: GuionLLM) -> list[str]:
    """Arregla en código lo puramente mecánico, sin volver a llamar al modelo: la numeración de
    las diapositivas y la firma de Folio que falta al final del cierre. No toca nada más."""
    hechas = []
    if [x.n for x in g.diapositivas] != list(range(1, len(g.diapositivas) + 1)):
        for i, x in enumerate(g.diapositivas, 1):
            x.n = i
        hechas.append("numeración de las diapositivas")
    d = g.diapositivas
    if d and d[-1].tipo == "cierre" and "folio" not in normalizar(d[-1].texto).split():
        texto = d[-1].texto.rstrip()
        d[-1].texto = texto + (" Folio." if texto.endswith((".", "!", "?", "…")) else ". Folio.")
        hechas.append("firma de Folio en el cierre")
    return hechas


def ajustar_libros(g: GuionLLM, libros: list[LibroVerificado]) -> list[DiscrepanciaEdicion]:
    """Pone en la ficha los datos verificados y devuelve en qué discrepaba el guionista.

    La sustitución no es silenciosa: si hay discrepancias, la pieza se marca «revisar edición»
    y el informe muestra los dos valores.
    """
    discrepancias = comparar_edicion(g, libros)
    for lg in g.libros:
        l = libro_verificado(lg, libros)
        if l is None:
            continue
        d = l.edicion_es_detalle if l.edicion_es == "si" else None
        lg.editorial_espanola = d.editorial if d else None
        lg.traductor = d.traductor if d else None
        lg.edicion_original = ", ".join([
            l.idioma_original or "idioma no consta",
            l.editorial_original or "editorial no consta",
            str(l.anio_primera_edicion) if l.anio_primera_edicion else "año no consta",
        ])
    return discrepancias


def _contenido_para_reenviar(contenido: list) -> list[dict]:
    return [bloque_reenviable(b) for b in contenido]


def escribir(llm: LLM, pieza_id: str, eleccion: HistoriaElegida, textos: list[tuple[FuenteNoticia, str]],
             libros: list[LibroVerificado]) -> tuple[GuionLLM, list[str]]:
    """Devuelve (guion validado, avisos). Lanza ValueError si no pasa la validación.

    La ficha de libros del guion sale tal como la escribió el modelo: ajustar_libros() la
    corrige después y devuelve las discrepancias.
    """
    cfg = llm.cfg
    fuentes = [f for f, _ in textos]
    prompt = construir_prompt(cfg, eleccion, textos, libros)
    mensajes = [{"role": "user", "content": con_cache(cfg, "guionista", prompt)}]
    errores: list[str] = []
    avisos: list[str] = []
    for intento in range(cfg.pipeline.guion.reintentos + 1):
        guion, contenido = llm.estructurado(f"guion:{pieza_id}:{intento + 1}", mensajes, GuionLLM,
                                            etapa_modelo="guion")
        corregido = corregir_mecanico(guion)
        if corregido:
            avisos.append(f"Corregido en código en el intento {intento + 1}: {', '.join(corregido)}")
        errores = validar(cfg, guion, libros, fuentes)
        if not errores:
            if intento:
                avisos.append(f"Guion aceptado en el intento {intento + 1}")
            return guion, avisos
        # Se registra por qué se rechaza cada intento: es lo que permite saber qué reglas
        # provocan los reintentos y si conviene reforzarlas en el prompt.
        avisos.append(f"Rechazado en el intento {intento + 1}: " + " | ".join(errores))
        mensajes += [
            {"role": "assistant", "content": _contenido_para_reenviar(contenido)},
            {"role": "user", "content": "El guion no cumple estas condiciones:\n"
             + "\n".join(f"- {e}" for e in errores)
             + "\nCorrígelo y devuelve el JSON completo."},
        ]
    raise ValueError("El guion no pasó la validación: " + " | ".join(errores))
