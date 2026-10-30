"""Agente «guionista» (prompts/guionista.md) y comprobaciones del guion.

El guion se valida en código: extensión, estructura, citas entre comillas, libros y fuentes.
Si no pasa, se reintenta una vez con la lista de errores; si vuelve a fallar, la pieza queda
como fallida. Los datos de edición de los libros se sustituyen siempre por los verificados.
"""

from __future__ import annotations

import re

from folio.config import Config
from folio.llm import LLM, cargar_prompt
from folio.modelos import FuenteNoticia, GuionLLM, HistoriaElegida, LibroVerificado
from folio.verificacion_texto import autor_coincide, normalizar, titulos_coinciden

_COMILLAS = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"")
_URL = re.compile(r"https?://\S+")
_FRASES_VETADAS = ("en un mundo donde", "en un mundo en el que")


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
        es = "no hay edición española"
    else:
        es = "no consta"
    return (
        f"- Título propuesto: {l.titulo_propuesto}\n"
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


def _palabras(texto: str) -> int:
    return len(texto.split())


def _es_titulo_de_libro(fragmento: str, libros: list[LibroVerificado]) -> bool:
    for l in libros:
        titulos = [l.titulo, l.titulo_propuesto]
        if l.edicion_es_detalle and l.edicion_es_detalle.titulo:
            titulos.append(l.edicion_es_detalle.titulo)
        if any(titulos_coinciden(fragmento, t, umbral=0.9) for t in titulos):
            return True
    return False


def validar(cfg: Config, g: GuionLLM, libros: list[LibroVerificado], fuentes: list[FuenteNoticia]) -> list[str]:
    p = cfg.pipeline["guion"]
    errores: list[str] = []
    d = g.diapositivas

    if not 4 <= len(d) <= 7:
        errores.append(f"Hay {len(d)} diapositivas; deben ser entre 4 y 7.")
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
        limite = p["palabras_max_portada"] if x.tipo == "portada" else p["palabras_max_diapositiva"]
        if _palabras(x.texto) > limite:
            errores.append(f"La diapositiva {x.n} ({x.tipo}) tiene {_palabras(x.texto)} palabras; máximo {limite}.")
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

    n_pie = _palabras(g.pie_instagram)
    if not p["pie_min_palabras"] <= n_pie <= p["pie_max_palabras"]:
        errores.append(f"El pie tiene {n_pie} palabras; debe tener entre {p['pie_min_palabras']} y {p['pie_max_palabras']}.")
    if not any(normalizar(f.medio) in normalizar(g.pie_instagram) for f in fuentes):
        errores.append("El pie debe citar el medio de la noticia (uno de: " + ", ".join(f.medio for f in fuentes) + ").")

    if not g.libros:
        errores.append("Falta la lista de libros.")
    for lg in g.libros:
        if not any(
            autor_coincide(lg.autor, l.autores) and _es_titulo_de_libro(lg.titulo, [l]) for l in libros
        ):
            errores.append(f"El libro «{lg.titulo}» de {lg.autor} no está entre los verificados.")

    urls_validas = {f.url for f in fuentes}
    for fn in g.fuentes_noticia:
        urls = _URL.findall(fn)
        if not urls or any(u.rstrip(".,;)") not in urls_validas for u in urls):
            errores.append(f"Fuente no reconocida: «{fn}». Usa solo los medios y URLs de los textos recibidos.")
    if not g.fuentes_noticia:
        errores.append("Falta fuentes_noticia.")
    return errores


def ajustar_libros(g: GuionLLM, libros: list[LibroVerificado]) -> list[str]:
    """Sustituye editorial, traductor y edición original por los datos verificados."""
    avisos = []
    for lg in g.libros:
        l = next((l for l in libros if autor_coincide(lg.autor, l.autores) and _es_titulo_de_libro(lg.titulo, [l])), None)
        if l is None:
            continue
        d = l.edicion_es_detalle if l.edicion_es == "si" else None
        nuevo_editorial = d.editorial if d else None
        nuevo_traductor = d.traductor if d else None
        nuevo_original = ", ".join([
            l.idioma_original or "idioma no consta",
            l.editorial_original or "editorial no consta",
            str(l.anio_primera_edicion) if l.anio_primera_edicion else "año no consta",
        ])
        if (lg.editorial_espanola or None) != nuevo_editorial or (lg.traductor or None) != nuevo_traductor:
            avisos.append(f"«{lg.titulo}»: datos de edición del guionista sustituidos por los verificados")
        lg.editorial_espanola, lg.traductor, lg.edicion_original = nuevo_editorial, nuevo_traductor, nuevo_original
    return avisos


def _contenido_para_reenviar(contenido: list) -> list[dict]:
    bloques = []
    for b in contenido:
        d = b.model_dump(mode="json", exclude_none=True)
        d.pop("parsed_output", None)
        bloques.append(d)
    return bloques


def escribir(llm: LLM, pieza_id: str, eleccion: HistoriaElegida, textos: list[tuple[FuenteNoticia, str]],
             libros: list[LibroVerificado]) -> tuple[GuionLLM, list[str]]:
    """Devuelve (guion validado, avisos). Lanza ValueError si no pasa la validación."""
    cfg = llm.cfg
    fuentes = [f for f, _ in textos]
    mensajes = [{"role": "user", "content": construir_prompt(cfg, eleccion, textos, libros)}]
    errores: list[str] = []
    for intento in range(cfg.pipeline["guion"]["reintentos"] + 1):
        guion, contenido = llm.estructurado(f"guion:{pieza_id}:{intento + 1}", mensajes, GuionLLM,
                                            etapa_modelo="guion")
        errores = validar(cfg, guion, libros, fuentes)
        if not errores:
            avisos = ajustar_libros(guion, libros)
            if intento:
                avisos.append(f"Guion aceptado en el intento {intento + 1}")
            return guion, avisos
        mensajes += [
            {"role": "assistant", "content": _contenido_para_reenviar(contenido)},
            {"role": "user", "content": "El guion no cumple estas condiciones:\n"
             + "\n".join(f"- {e}" for e in errores)
             + "\nCorrígelo y devuelve el JSON completo."},
        ]
    raise ValueError("El guion no pasó la validación: " + " | ".join(errores))
