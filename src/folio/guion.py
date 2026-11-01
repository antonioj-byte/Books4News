"""Agente «guionista» (prompts/guionista.md) y comprobaciones del guion.

El guion se valida en código: extensión, estructura, citas entre comillas, libros y fuentes.
Si no pasa, se reintenta una vez con la lista de errores; si vuelve a fallar, la pieza queda
como fallida. Los datos de edición de los libros se sustituyen siempre por los verificados.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from folio.config import Config
from folio.config import Guion as ConfigGuion
from folio.llm import LLM, bloque_reenviable, cargar_prompt, con_cache
from folio.modelos import CitaVerificada, DiscrepanciaEdicion, FuenteNoticia, GuionLLM, HistoriaElegida, LibroGuion, LibroVerificado
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


def instrucciones_formato(cfg: Config, formato: str) -> str:
    """La sección del formato en prompts/formatos.md (lateral, dialogo, edicion)."""
    texto = (cfg.dir_prompts / "formatos.md").read_text(encoding="utf-8")
    secciones = {m.group(1): m.group(2).strip() for m in re.finditer(r"^## (\w+)\n(.*?)(?=^## |\Z)", texto, re.M | re.S)}
    if formato not in secciones:
        raise ValueError(f"prompts/formatos.md no tiene la sección «## {formato}»")
    return secciones[formato]


def construir_prompt(cfg: Config, eleccion: HistoriaElegida, textos: list[tuple[FuenteNoticia, str]],
                     libros: list[LibroVerificado]) -> str:
    fuentes = "\n".join(
        f'<fuente medio="{f.medio}" url="{f.url}" acceso="{f.acceso}"{" critica=\"si\"" if f.critica else ""}{" prensa_del_libro=\"si\"" if f.prensa else ""}>\n{t}\n</fuente>'
        for f, t in textos
    )
    noticia = (
        "\n<noticia>\n"
        f"Titular: {eleccion.titular}\n"
        f"De qué se está hablando: {eleccion.de_que_se_habla}\n"
        f"Cuestión de fondo (propuesta del jefe de cultura): {eleccion.cuestion_de_fondo}\n"
        + (f"Gancho del libro para la portada (propuesta del jefe de cultura): {eleccion.gancho_libro}\n" if eleccion.gancho_libro else "")
        + f"Textos de los medios:\n{fuentes}\n"
        "</noticia>"
    )
    libros_txt = (
        "\n<libros_verificados>\n" + "\n".join(_linea_libro(l) for l in libros) + "\n</libros_verificados>\n"
        "Usa solo estos libros, que se han verificado en catálogos bibliográficos."
    ) if libros else (
        "ninguno. Esta pieza no lleva libro: no hay diapositiva de libro, la lista de libros va vacía y la portada, "
        "el cierre y el pie no recomiendan ninguno. Las reglas sobre el libro no se aplican; las demás, sí."
    )
    return cargar_prompt(cfg, "guionista", {
        "[pegar formato]": instrucciones_formato(cfg, eleccion.formato),
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


# --- Validación del guion -------------------------------------------------------
# Cada regla devuelve sus errores. El orden de REGLAS es el de los mensajes que recibe el modelo
# en el reintento: no cambiarlo sin motivo.

@dataclass
class _Guion:
    """Lo que necesita cada regla: el guion, los libros verificados, las fuentes y los límites."""
    g: GuionLLM
    libros: list[LibroVerificado]
    fuentes: list[FuenteNoticia]
    p: ConfigGuion
    citas_ok: frozenset[str] = frozenset()   # citas encontradas en el texto del libro (normalizadas)
    criticas_ok: frozenset[str] = frozenset()  # citas de la crítica encontradas en el texto de crítica (normalizadas)
    formato: str = ""

    @property
    def sin_libro(self) -> bool:
        """Pieza sin libro verificado: solo pasa en una curiosidad del cajón (el pipeline descarta las demás).
        Entonces no se aplican las reglas del libro."""
        return not self.libros

    @property
    def d(self) -> list:
        return self.g.diapositivas

    @property
    def textos(self) -> list[str]:
        return [t for x in self.d for t in (x.texto, x.subtitulo) if t] + [self.g.pie_instagram]


def _extension(c: _Guion) -> list[str]:
    return [] if 4 <= len(c.d) <= 7 else [f"Hay {len(c.d)} diapositivas; deben ser entre 4 y 7."]


def _justificacion_extra(c: _Guion) -> list[str]:
    extra = len(c.d) - c.p.diapositivas_por_defecto
    if extra > 0 and len([j for j in c.g.justificacion_extra if j.strip()]) < extra:
        return [f"Hay {len(c.d)} diapositivas: justifica en justificacion_extra, con una línea cada una, "
                f"qué aporta cada una de las {extra} por encima de {c.p.diapositivas_por_defecto}, o recorta."]
    return []


def _numeracion(c: _Guion) -> list[str]:
    ok = [x.n for x in c.d] == list(range(1, len(c.d) + 1))
    return [] if ok else ["Las diapositivas deben numerarse 1, 2, 3… sin saltos."]


def _primera_es_portada(c: _Guion) -> list[str]:
    return ["La diapositiva 1 debe ser de tipo «portada»."] if c.d and c.d[0].tipo != "portada" else []


def _ultima_es_cierre(c: _Guion) -> list[str]:
    return ["La última diapositiva debe ser de tipo «cierre»."] if c.d and c.d[-1].tipo != "cierre" else []


def _tipos_obligatorios(c: _Guion) -> list[str]:
    tipos = ("actualidad", "idea") if c.sin_libro else ("actualidad", "libro", "idea")
    return [f"Falta una diapositiva de tipo «{tipo}»." for tipo in tipos if not any(x.tipo == tipo for x in c.d)]


def _palabras_por_diapositiva(c: _Guion) -> list[str]:
    errores = []
    for x in c.d:
        limite = c.p.palabras_max_portada if x.tipo == "portada" else c.p.palabras_max_diapositiva
        if _palabras(x.texto) > limite:
            errores.append(f"La diapositiva {x.n} ({x.tipo}) tiene {_palabras(x.texto)} palabras; máximo {limite}.")
        if x.subtitulo and x.tipo == "portada" and _palabras(x.subtitulo) > c.p.palabras_max_subtitulo:
            errores.append(f"El subtítulo de la portada tiene {_palabras(x.subtitulo)} palabras; máximo {c.p.palabras_max_subtitulo}.")
        if x.subtitulo and x.tipo != "portada":
            errores.append(f"La diapositiva {x.n} ({x.tipo}) lleva subtítulo: solo la portada lo lleva.")
    return errores


# El libro está desde la portada (titular o subtítulo), entra pronto y protagoniza el cierre.
def _portada_con_libro(c: _Guion) -> list[str]:
    if c.sin_libro or not c.d or c.d[0].tipo != "portada":
        return []
    portada = c.d[0]
    if not portada.subtitulo:
        return ["La portada necesita un subtítulo que traiga el libro o a su autor."]
    if not _menciona_libro(f"{portada.texto} {portada.subtitulo}", c.libros):
        return ["Desde la portada tiene que saberse que la pieza va de un libro: nombra el libro o a su autor "
                "en el titular o en el subtítulo."]
    return []


def _cierre_nombra_libro(c: _Guion) -> list[str]:
    if not c.sin_libro and c.d and c.d[-1].tipo == "cierre" and not _menciona_libro(c.d[-1].texto, c.libros):
        return ["El cierre es la recomendación: nombra el libro (título en cursiva) y a su autor."]
    return []


def _una_actualidad(c: _Guion) -> list[str]:
    n = sum(x.tipo == "actualidad" for x in c.d)
    if n > c.p.max_diapositivas_actualidad:
        return [f"Hay {n} diapositivas de actualidad; máximo {c.p.max_diapositivas_actualidad}. "
                "La noticia es la excusa: resúmela."]
    return []


def _libro_pronto(c: _Guion) -> list[str]:
    primer_libro = next((x.n for x in c.d if x.tipo == "libro"), None)
    if primer_libro and primer_libro > c.p.posicion_max_primer_libro:
        return [f"El libro entra en la diapositiva {primer_libro}; debe hacerlo como muy tarde en la "
                f"{c.p.posicion_max_primer_libro}."]
    return []


def _pie_nombra_libro(c: _Guion) -> list[str]:
    if c.sin_libro or _menciona_libro(c.g.pie_instagram, c.libros):
        return []
    return ["El pie debe nombrar el libro que recomienda la pieza."]


def _portada_no_pregunta(c: _Guion) -> list[str]:
    return ["La portada no puede ser una pregunta retórica."] if c.d and c.d[0].texto.strip().endswith("?") else []


def _firma(c: _Guion) -> list[str]:
    return ["El cierre debe llevar la firma de Folio."] if c.d and "folio" not in normalizar(c.d[-1].texto).split() else []


MAX_CRITICAS = 2          # citas de la crítica por guion (formato «recomendado»; decisión del usuario, 1/11)


def citas_de_la_critica(g: GuionLLM, libros: list[LibroVerificado], textos: list[tuple[FuenteNoticia, str]]) -> list[CitaVerificada]:
    """Las frases entre comillas del guion que aparecen letra por letra (salvo mayúsculas, tildes y signos) en un
    texto de crítica recibido. Solo esas pueden ir entre comillas además de la cita verificada del libro."""
    criticas = [(f, normalizar(t)) for f, t in textos if f.critica]
    if not criticas:
        return []
    textos_g = [t for x in g.diapositivas for t in (x.texto, x.subtitulo) if t] + [g.pie_instagram]
    salida, vistos = [], set()
    for frase in citas_entre_comillas(textos_g, libros):
        n = normalizar(frase)
        if len(n.split()) < 2 or n in vistos:
            continue
        fuente = next((f for f, t in criticas if f" {n} " in f" {t} "), None)
        if fuente:
            vistos.add(n)
            libro = libros[0] if libros else None
            salida.append(CitaVerificada(texto=frase, libro=libro.titulo_propuesto if libro else "", autor=(libro.autores or [""])[0] if libro else "",
                                         fragmento=frase, tipo="critica", fuente=fuente.url))
    return salida


def citas_entre_comillas(textos: list[str], libros: list[LibroVerificado]) -> list[str]:
    """Los fragmentos entre comillas que no son títulos de libros: posibles citas literales."""
    return [f for t in textos for m in _COMILLAS.finditer(t)
            if not _es_titulo_de_libro(f := next(x for x in m.groups() if x), libros)]


def _frases_vetadas_y_citas(c: _Guion) -> list[str]:
    """Texto a texto: primero las frases vetadas y luego los textos entre comillas que no son títulos
    ni citas encontradas en el texto del libro. Después, el número y la longitud de las citas."""
    errores, citas, criticas = [], [], []
    for t in c.textos:
        tn = t.lower()
        errores += [f"Frase vetada: «{frase}…»." for frase in _FRASES_VETADAS if frase in tn]
        for fragmento in citas_entre_comillas([t], c.libros):
            if normalizar(fragmento) in c.citas_ok:
                citas.append(fragmento)
            elif normalizar(fragmento) in c.criticas_ok:
                criticas.append(fragmento)
            else:
                errores.append(f"Texto entre comillas que no es el título de un libro ni una cita encontrada en su "
                               f"texto: «{fragmento[:80]}». Parafrasea sin comillas.")
    minimo, maximo = c.p.palabras_cita
    errores += [f"La cita «{x[:60]}» tiene {_palabras(x)} palabras; entre {minimo} y {maximo}."
                for x in citas if not minimo <= _palabras(x) <= maximo]
    if len(citas) > c.p.max_citas:
        errores.append(f"Hay {len(citas)} citas literales; como mucho {c.p.max_citas}.")
    if len(set(criticas)) > MAX_CRITICAS:
        errores.append(f"Hay {len(set(criticas))} citas de la crítica; como mucho {MAX_CRITICAS}.")
    return errores


def _traduccion(c: _Guion) -> list[str]:
    if any(l.edicion_es == "no" for l in c.libros):
        return []
    return [f"«{m.group(0)}»: ningún libro tiene verificado que no haya edición española; "
            "no digas nada sobre su traducción." for t in c.textos if (m := _SOBRE_TRADUCCION.search(t))]


def _longitud_pie(c: _Guion) -> list[str]:
    n = _palabras(c.g.pie_instagram)
    if c.p.pie_min_palabras <= n <= c.p.pie_max_palabras:
        return []
    return [f"El pie tiene {n} palabras; debe tener entre {c.p.pie_min_palabras} y {c.p.pie_max_palabras}."]


def _pie_cita_medio(c: _Guion) -> list[str]:
    if c.formato == "recomendado":           # no hay noticia: los textos son la ficha del libro y su crítica
        return []
    if any(normalizar(f.medio) in normalizar(c.g.pie_instagram) for f in c.fuentes):
        return []
    return ["El pie debe citar el medio de la noticia (uno de: " + ", ".join(f.medio for f in c.fuentes) + ")."]


def _libros_verificados(c: _Guion) -> list[str]:
    errores = [] if c.g.libros or c.sin_libro else ["Falta la lista de libros."]
    return errores + [f"El libro «{lg.titulo}» de {lg.autor} no está entre los verificados."
                      for lg in c.g.libros if libro_verificado(lg, c.libros) is None]


def _una_de_libro_por_libro(c: _Guion) -> list[str]:
    """Cada libro tiene una sola diapositiva de libro: la cubierta no se repite (decisión del usuario, 31/10)."""
    n = sum(1 for x in c.d if x.tipo == "libro")
    libros = len(c.g.libros)
    if not libros or n <= libros:          # sin libros ya lo dice _libros_verificados
        return []
    return [f"Hay {n} diapositivas de libro y {libros} libro{'s' if libros > 1 else ''}: cada libro tiene una sola "
            "(con su cubierta, que no se repite); lo demás sobre el libro va en una diapositiva de idea."]


def _uno_o_tres_libros(c: _Guion) -> list[str]:
    """Una pieza lleva uno o tres libros, nunca dos (decisión del usuario, 31/10)."""
    n = len(c.g.libros)
    if n in (0, 1, 3):                     # sin libros ya lo dice _libros_verificados
        return []
    if n > 3:
        return [f"Hay {n} libros; una pieza lleva 1 o 3."]
    tercero = " o añade un tercero de la lista verificada que aporte de verdad" if len(c.libros) >= 3 else ""
    return [f"Hay 2 libros; una pieza lleva 1 o 3, nunca 2: quédate con el principal{tercero}."]


def _fuentes_conocidas(c: _Guion) -> list[str]:
    urls_validas = {f.url for f in c.fuentes}
    errores = []
    for fn in c.g.fuentes_noticia:
        urls = _URL.findall(fn)
        if not urls or any(u.rstrip(".,;)") not in urls_validas for u in urls):
            errores.append(f"Fuente no reconocida: «{fn}». Usa solo los medios y URLs de los textos recibidos.")
    return errores + ([] if c.g.fuentes_noticia else ["Falta fuentes_noticia."])


REGLAS = (
    _extension, _justificacion_extra, _numeracion, _primera_es_portada, _ultima_es_cierre, _tipos_obligatorios,
    _palabras_por_diapositiva, _portada_con_libro, _cierre_nombra_libro, _una_actualidad, _libro_pronto,
    _pie_nombra_libro, _portada_no_pregunta, _firma, _frases_vetadas_y_citas, _traduccion, _longitud_pie,
    _pie_cita_medio, _libros_verificados, _uno_o_tres_libros, _una_de_libro_por_libro, _fuentes_conocidas,
)


def validar(cfg: Config, g: GuionLLM, libros: list[LibroVerificado], fuentes: list[FuenteNoticia],
            citas_ok: frozenset[str] = frozenset(), criticas_ok: frozenset[str] = frozenset(), formato: str = "") -> list[str]:
    """Errores del guion según las reglas editoriales (vacío si cumple todas). `citas_ok`: las citas
    (normalizadas) que se han encontrado en el texto del libro; `criticas_ok`, las de la crítica encontradas
    en su texto (ver citas_de_la_critica)."""
    c = _Guion(g, libros, fuentes, cfg.pipeline.guion, citas_ok, criticas_ok, formato)
    return [error for regla in REGLAS for error in regla(c)]


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


def _verificar_citas(g: GuionLLM, libros: list[LibroVerificado], verificar_cita, ya: dict[str, CitaVerificada | None],
                     avisos: list[str]) -> dict[str, CitaVerificada | None]:
    """Busca en el texto del libro cada cita del guion (una sola vez cada una)."""
    textos = [t for x in g.diapositivas for t in (x.texto, x.subtitulo) if t] + [g.pie_instagram]
    for frase in citas_entre_comillas(textos, libros):
        if frase not in ya and verificar_cita:
            try:
                ya[frase] = verificar_cita(frase, libros)
            except Exception as exc:     # sin red no se verifica: la cita no pasa
                ya[frase] = None
                avisos.append(f"No se pudo verificar la cita «{frase[:60]}»: {type(exc).__name__}")
    return ya


def escribir(llm: LLM, pieza_id: str, eleccion: HistoriaElegida, textos: list[tuple[FuenteNoticia, str]],
             libros: list[LibroVerificado], verificar_cita=None) -> tuple[GuionLLM, list[str], list[CitaVerificada]]:
    """Devuelve (guion validado, avisos, citas verificadas). Lanza ValueError si no pasa la validación.

    `verificar_cita` (folio.libros.citas) busca cada cita literal en el texto del libro; sin él, ninguna
    cita pasa. La ficha de libros del guion sale tal como la escribió el modelo: ajustar_libros() la
    corrige después y devuelve las discrepancias.
    """
    cfg = llm.cfg
    fuentes = [f for f, _ in textos]
    prompt = construir_prompt(cfg, eleccion, textos, libros)
    mensajes = [{"role": "user", "content": con_cache(cfg, "guionista", prompt)}]
    errores: list[str] = []
    avisos: list[str] = []
    citas: dict[str, CitaVerificada | None] = {}
    # El lector sin contexto (2/11): una vez, cuando el guion ya cumple las reglas. Si no entiende algo, el guionista
    # reescribe esas frases en un turno más; si esa reescritura rompe alguna regla, vale la versión anterior.
    claridad_pendiente = cfg.pipeline.guion.lector_sin_contexto
    respaldo = None
    reintentos = cfg.pipeline.guion.reintentos
    intento = 0
    while True:
        guion, contenido = llm.estructurado(f"guion:{pieza_id}:{intento + 1}", mensajes, GuionLLM,
                                            etapa_modelo="guion")
        corregido = corregir_mecanico(guion)
        if corregido:
            avisos.append(f"Corregido en código en el intento {intento + 1}: {', '.join(corregido)}")
        citas = _verificar_citas(guion, libros, verificar_cita, citas, avisos)
        citas_ok = frozenset(normalizar(f) for f, c in citas.items() if c)
        criticas = citas_de_la_critica(guion, libros, textos)
        errores = validar(cfg, guion, libros, fuentes, citas_ok, frozenset(normalizar(c.texto) for c in criticas), eleccion.formato)
        if not errores:
            textos_finales = " ".join(t for x in guion.diapositivas for t in (x.texto, x.subtitulo) if t) + guion.pie_instagram
            aceptado = (guion, [c for f, c in citas.items() if c and f in textos_finales] + criticas)
            problemas = []
            if claridad_pendiente:
                claridad_pendiente = False
                try:
                    from folio import claridad
                    problemas = claridad.revisar(llm, cfg, pieza_id, guion)
                except Exception as exc:          # el lector nunca para el guion
                    avisos.append(f"Lector sin contexto: no se pudo ({type(exc).__name__})")
            if not problemas:
                if intento:
                    avisos.append(f"Guion aceptado en el intento {intento + 1}")
                return aceptado[0], avisos, aceptado[1]
            respaldo = aceptado
            avisos.append("Lector sin contexto: " + " | ".join(problemas))
            mensajes += [
                {"role": "assistant", "content": _contenido_para_reenviar(contenido)},
                {"role": "user", "content": "Un lector que no conoce la obra ni la noticia no entiende esto:\n"
                 + "\n".join(f"- {x}" for x in problemas)
                 + "\nReescribe esas frases para que se entiendan sin saber nada: presenta en pocas palabras a cada persona, "
                 "lugar o episodio que no sea de dominio común y cambia las alusiones por lo que significan, sin pasarte de las "
                 "palabras por diapositiva y sin tocar lo demás. Devuelve el JSON completo."},
            ]
            intento += 1
            continue
        if respaldo:
            # La reescritura para el lector sin contexto rompió alguna regla: vale la versión que las cumplía
            avisos.append(f"Lector sin contexto: la reescritura no cumplía las reglas ({' | '.join(errores)}); "
                          "se queda la versión anterior")
            return respaldo[0], avisos, respaldo[1]
        # Se registra por qué se rechaza cada intento: es lo que permite saber qué reglas
        # provocan los reintentos y si conviene reforzarlas en el prompt.
        avisos.append(f"Rechazado en el intento {intento + 1}: " + " | ".join(errores))
        if intento >= reintentos:
            break
        mensajes += [
            {"role": "assistant", "content": _contenido_para_reenviar(contenido)},
            {"role": "user", "content": "El guion no cumple estas condiciones:\n"
             + "\n".join(f"- {e}" for e in errores)
             + "\nCorrígelo y devuelve el JSON completo."},
        ]
        intento += 1
    raise ValueError("El guion no pasó la validación: " + " | ".join(errores))
