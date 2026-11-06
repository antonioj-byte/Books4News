"""«Perfil de autor» (6/11, a petición del usuario: «una breve semblanza biográfica con un título, un subtítulo y varias
diapositivas que traten sobre la trayectoria del autor… al menos una quote de una entrevista del autor, puede ser también
una cita significativa de un libro, cosas que la prensa ha dicho del autor, de qué tratan sus libros… Puede llevar percha
o no, puede ser un premio, puede ser un obituario»; en el Artifact «El perfil de autor» eligió las direcciones B, «la
revista», y C, «el collage»: «Me gustan la B y la C»).

Es un formato «propio» que sí pasa por la mesa (`Formato.en_mesa`): lo propone el editor del libro de madrugada (en el
hueco del mundo del libro) o la redacción en un tema, sus libros se verifican como siempre (la obra del autor, sin
exigir novedad), se escribe con «Proceder» y la comprobación de hechos es la general. Este módulo hace lo suyo:
1. Busca la prensa sobre la persona (entrevistas primero, reseñas, perfiles; `prompts/prensa_autor.md`, Haiku con
   búsqueda, las mismas comprobaciones que la prensa del libro).
2. El editor (Opus, `prompts/perfil.md`) escribe las siete diapositivas: portada, quién es / por qué hoy, trayectoria con
   años, su obra, su voz (una frase suya literal), la prensa (0–2 frases literales) y por dónde empezar.
3. El código comprueba que las frases entre comillas están letra por letra en los textos (o, las de un libro, en su texto
   de Google Books), que cada año de la trayectoria sale de los textos o de las fichas, y reintenta una vez. Si al final
   solo falla la frase de su voz o la de la prensa, la diapositiva sale fuera con un aviso (corrección mecánica).
4. El arte: la foto de la persona (Commons o prensa) y el estilo del día, «revista» (B: foto a sangre en blanco y negro,
   oscuro) o «collage» (C: el recorte en trama sobre papel de color), alternados; un obituario, siempre «revista» y sin
   color.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from folio.config import Config
from folio.llm import LLM, ErrorLLM, cache_al_final, cargar_prompt
from folio.modelos import (Arte, CitaVerificada, Diapositiva, FuenteNoticia, GuionLLM, LibroGuion, LibroVerificado,
                           Pieza)
from folio.newsletter import literal, normalizar

FORMATO = "perfil"
ESTILOS = ("revista", "collage")       # B y C del Artifact
SEP = " | "                            # entre hitos y entre frases de la prensa, en el texto de su diapositiva
SEP_HITO = ": "                        # «2026: Premio Herralde»
SEP_MEDIO = " — "                      # «Una frase de la crítica — El Cultural»
# Las posiciones de los remates de los titulillos en Arte.remates_noticias
R_PORQUE, R_TRAYECTORIA, R_OBRA, R_VOZ = range(4)
MAX_PRENSA = 2
AVISO_SIN_VOZ = "Perfil sin frase suya verificada: ninguna de las que propuso el editor aparece letra por letra en los textos"


class HitoPerfil(BaseModel):
    anio: str = Field(description="El año, con cuatro cifras; solo uno que esté en los textos o en las fichas")
    texto: str = Field(description="De 2 a 14 palabras: qué pasó ese año")


class VozPerfil(BaseModel):
    texto: str = Field(description="Una frase suya, letra por letra, sin comillas; de 4 a 40 palabras")
    remate: str = Field(description="El final literal de la frase, de 1 a 6 palabras")
    origen: Literal["entrevista", "libro"]
    atribucion: str = Field(description="De dónde sale, en pocas palabras: «En una entrevista con El País, 2024»")
    fuente_url: str = Field(description="La URL del texto donde está; vacía si es de un libro")


class PrensaPerfil(BaseModel):
    texto: str = Field(description="Una frase de la crítica o la prensa, letra por letra, sin comillas; de 3 a 30 palabras")
    medio: str
    fuente_url: str


class GuionPerfil(BaseModel):
    obituario: bool = Field(description="True si la percha es su muerte")
    titular: str = Field(description="De 4 a 14 palabras; nombra a la persona")
    remate: str = Field(description="El final literal del titular, de 2 a 6 palabras")
    subtitulo: str = Field(description="De 10 a 26 palabras: la percha, si la hay, y la idea que recorre su obra")
    porque_titulo: str = Field(description="Titulillo de «quién es / por qué hoy», de 2 a 9 palabras")
    porque_remate: str = Field(description="Su final literal, de 1 a 5 palabras")
    porque_texto: str = Field(description="De 25 a 60 palabras")
    trayectoria_titulo: str = Field(description="Titulillo de la trayectoria, de 2 a 9 palabras")
    trayectoria_remate: str = Field(description="Su final literal, de 1 a 5 palabras")
    hitos: list[HitoPerfil] = Field(description="De 3 a 5 hitos, en orden cronológico")
    obra_titulo: str = Field(description="Titulillo de «su obra», de 2 a 9 palabras")
    obra_remate: str = Field(description="Su final literal, de 1 a 5 palabras")
    obra_texto: str = Field(description="De 25 a 60 palabras: de qué van sus libros")
    voz: VozPerfil
    prensa: list[PrensaPerfil] = Field(description="De 0 a 2 frases de la crítica o la prensa")
    cierre: str = Field(description="De 6 a 20 palabras: por dónde empezar (en un obituario, el homenaje)")
    remate_cierre: str = Field(description="El final literal del cierre, de 1 a 5 palabras")
    cierre_texto: str = Field(description="De 15 a 40 palabras: por qué empezar por ese libro")
    pie_instagram: str = Field(description="De 60 a 150 palabras")
    titulares_alternativos: list[str] = Field(description="Cinco titulares alternativos, de 14 palabras como mucho")


# --- Comprobaciones -----------------------------------------------------------------------------

def _palabras(t: str) -> int:
    return len(t.replace("*", " ").split())


def _remate_valido(frase: str, remate: str, minimo: int, maximo: int) -> bool:
    f, r = normalizar(frase), normalizar(remate)
    return bool(r) and minimo <= len(r.split()) <= maximo and f.endswith(r) and f != r


def anios_permitidos(textos: list[tuple[FuenteNoticia, str]], libros: list[LibroVerificado], fecha: str) -> set[str]:
    """Los años que pueden ir en la trayectoria: los que salen en los textos, los de las fichas y el de hoy."""
    anios = {fecha[:4]}
    for f, t in textos:
        anios |= set(re.findall(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)", f"{f.titulo} {t}"))
    for l in libros:
        if l.anio_primera_edicion:
            anios.add(str(l.anio_primera_edicion))
        if l.edicion_es_detalle and l.edicion_es_detalle.anio:
            anios |= set(re.findall(r"\d{4}", str(l.edicion_es_detalle.anio)))
    return anios


def fuente_literal(frase: str, textos: list[tuple[FuenteNoticia, str]]) -> FuenteNoticia | None:
    """El primer texto que contiene la frase letra por letra (salvo mayúsculas, tildes y signos)."""
    return next((f for f, t in textos if literal(frase, t)), None)


def _apellido_en(texto: str, persona: str) -> bool:
    from folio.verificacion_texto import apellido
    ap = apellido(persona)
    return len(ap) >= 3 and ap in normalizar(texto).split()


def validar(g: GuionPerfil, textos: list[tuple[FuenteNoticia, str]], libros: list[LibroVerificado], fecha: str,
            persona: str, cita_de_libro=None) -> list[tuple[str, str]]:
    """Los errores del guion, cada uno con su parte («voz», «prensa» u «otro»), y la verificación de las frases.
    `cita_de_libro(frase, libros)`: busca una frase en el texto de los libros (Google Books); None si no hay clave."""
    from folio.guion import _menciona_libro, citas_entre_comillas
    errores: list[tuple[str, str]] = []

    def mal(msg: str, parte: str = "otro") -> None:
        errores.append((parte, msg))

    if not 4 <= _palabras(g.titular) <= 14:
        mal(f"El titular tiene que tener de 4 a 14 palabras (tiene {_palabras(g.titular)}).")
    if g.titular.strip().endswith("?"):
        mal("El titular no puede ser una pregunta.")
    if not _remate_valido(g.titular, g.remate, 2, 6):
        mal("El remate del titular tiene que ser su final literal, de 2 a 6 palabras.")
    if not 10 <= _palabras(g.subtitulo) <= 26:
        mal(f"El subtítulo tiene que tener de 10 a 26 palabras (tiene {_palabras(g.subtitulo)}).")
    if persona and not _apellido_en(f"{g.titular} {g.subtitulo}", persona):
        mal(f"La portada (titular o subtítulo) tiene que nombrar a {persona}.")
    for nombre, titulo, remate, texto in (("quién es", g.porque_titulo, g.porque_remate, g.porque_texto),
                                          ("su obra", g.obra_titulo, g.obra_remate, g.obra_texto)):
        if not 25 <= _palabras(texto) <= 60:
            mal(f"El texto de «{nombre}» tiene que tener de 25 a 60 palabras (tiene {_palabras(texto)}).")
        if not 2 <= _palabras(titulo) <= 9 or not _remate_valido(titulo, remate, 1, 5):
            mal(f"El titulillo de «{nombre}» tiene que tener de 2 a 9 palabras y su remate ser su final literal (1 a 5).")
    if not 2 <= _palabras(g.trayectoria_titulo) <= 9 or not _remate_valido(g.trayectoria_titulo, g.trayectoria_remate, 1, 5):
        mal("El titulillo de la trayectoria tiene que tener de 2 a 9 palabras y su remate ser su final literal (1 a 5).")
    if libros and not _menciona_libro(g.obra_texto, [l.model_copy(update={"autores": []}) for l in libros]):
        mal("«Su obra» tiene que nombrar al menos uno de los libros verificados, en cursiva.")
    if not 3 <= len(g.hitos) <= 5:
        mal(f"La trayectoria lleva de 3 a 5 hitos (lleva {len(g.hitos)}).")
    permitidos = anios_permitidos(textos, libros, fecha)
    anteriores = []
    for h in g.hitos:
        if not re.fullmatch(r"\d{4}", h.anio.strip()):
            mal(f"Hito «{h.texto[:40]}»: el año tiene que tener cuatro cifras («{h.anio}»).")
            continue
        if h.anio.strip() not in permitidos:
            mal(f"Hito de {h.anio}: ese año no sale en los textos ni en las fichas de los libros; quítalo o usa otro.")
        if not 2 <= _palabras(h.texto) <= 14:
            mal(f"Hito de {h.anio}: de 2 a 14 palabras (tiene {_palabras(h.texto)}).")
        anteriores.append(int(h.anio.strip()))
    if anteriores != sorted(anteriores):
        mal("Los hitos de la trayectoria tienen que ir en orden cronológico.")
    # Su voz: letra por letra en los textos o, si es de un libro, en su texto (Google Books)
    if not 4 <= _palabras(g.voz.texto) <= 40:
        mal(f"La frase de su voz tiene que tener de 4 a 40 palabras (tiene {_palabras(g.voz.texto)}).", "voz")
    elif not (fuente_literal(g.voz.texto, textos)
              or (g.voz.origen == "libro" and cita_de_libro and cita_de_libro(g.voz.texto, libros))):
        mal("La frase de su voz no aparece letra por letra en los textos"
            + (" ni en el texto de sus libros" if g.voz.origen == "libro" else "")
            + f": «{g.voz.texto[:70]}». Copia una frase suya exacta de una entrevista de los textos.", "voz")
    elif not _remate_valido(g.voz.texto, g.voz.remate, 1, 6):
        mal("El remate de la frase de su voz tiene que ser su final literal, de 1 a 6 palabras.", "voz")
    if len(g.prensa) > MAX_PRENSA:
        mal(f"La prensa lleva como mucho {MAX_PRENSA} frases.", "prensa")
    for i, p in enumerate(g.prensa[:MAX_PRENSA], 1):
        if not 3 <= _palabras(p.texto) <= 30:
            mal(f"Frase de prensa {i}: de 3 a 30 palabras (tiene {_palabras(p.texto)}).", "prensa")
        elif not fuente_literal(p.texto, textos):
            mal(f"Frase de prensa {i}: no aparece letra por letra en los textos («{p.texto[:60]}»).", "prensa")
        elif normalizar(p.texto) == normalizar(g.voz.texto):
            mal(f"Frase de prensa {i}: repite la frase de su voz.", "prensa")
    if not 6 <= _palabras(g.cierre) <= 20 or not _remate_valido(g.cierre, g.remate_cierre, 1, 5):
        mal("El cierre tiene que tener de 6 a 20 palabras y su remate ser su final literal (1 a 5).")
    if not 15 <= _palabras(g.cierre_texto) <= 40:
        mal(f"El texto del cierre tiene que tener de 15 a 40 palabras (tiene {_palabras(g.cierre_texto)}).")
    if libros and not _menciona_libro(f"{g.cierre} {g.cierre_texto}", [libros[0].model_copy(update={"autores": []})]):
        mal("El cierre tiene que nombrar el libro principal (el primero de la lista verificada), en cursiva.")
    if not 50 <= _palabras(g.pie_instagram) <= 170:
        mal(f"El pie tiene que tener de 60 a 150 palabras (tiene {_palabras(g.pie_instagram)}).")
    # Nada entre comillas fuera de su voz y la prensa (los títulos, en cursiva)
    sueltos = [g.titular, g.subtitulo, g.porque_texto, g.obra_texto, g.cierre, g.cierre_texto, g.pie_instagram,
               *(h.texto for h in g.hitos)]
    validas = {normalizar(g.voz.texto), *(normalizar(p.texto) for p in g.prensa)}
    for frase in citas_entre_comillas(sueltos, libros):
        if normalizar(frase) not in validas:
            mal(f"Texto entre comillas que no es el título de un libro: «{frase[:60]}». Parafrasea sin comillas.")
    return errores


# --- Escribir -------------------------------------------------------------------------------------

def persona_de(pieza: Pieza) -> str:
    """A quién retrata: el protagonista de la propuesta o el autor del libro principal."""
    if pieza.eleccion.protagonista.strip():
        return pieza.eleccion.protagonista.strip()
    return (pieza.libros[0].autores or [""])[0] if pieza.libros else ""


def construir_prompt(cfg: Config, pieza: Pieza, textos: list[tuple[FuenteNoticia, str]]) -> str:
    from folio.guion import _linea_libro, atributo_publicado, linea_hoy
    e = pieza.eleccion
    perfil = (f"Persona: {persona_de(pieza)}\nTitular propuesto: {e.titular}\nDe qué se habla: {e.de_que_se_habla}\n"
              f"Por qué ahora: {e.por_que}"
              + (f"\nEncargo de la redacción (síguelo dentro de las reglas):\n{e.encargo.strip()}" if e.encargo.strip() else ""))
    fuentes = "\n".join(
        f'<fuente medio="{f.medio}" url="{f.url}"{atributo_publicado(f)}{" critica=\"si\"" if f.critica else ""}'
        f'{" prensa=\"si\"" if f.prensa else ""}>\n{t}\n</fuente>' for f, t in textos)
    return cargar_prompt(cfg, "perfil", {
        "[pegar hoy]": linea_hoy(pieza.fecha), "[pegar perfil]": perfil,
        "[pegar libros]": "\n".join(_linea_libro(l) for l in pieza.libros) or "(ninguno verificado)",
        "[pegar textos]": fuentes or "(ninguno)",
    })


def escribir(llm: LLM, cfg: Config, pieza: Pieza, textos: list[tuple[FuenteNoticia, str]], cita_de_libro=None,
             anunciar=None) -> tuple[GuionPerfil, list[str], list[str]]:
    """El guion del perfil, el reintento si no valida y la corrección mecánica final: devuelve el guion, los avisos y lo
    que hay que revisar a mano. ErrorLLM si tras el reintento sigue fallando algo que no sea la voz o la prensa."""
    persona = persona_de(pieza)
    mensajes = [{"role": "user", "content": construir_prompt(cfg, pieza, textos)}]
    avisos, revisar = [], []
    ya: dict[str, bool] = {}

    def de_libro(frase: str, libros) -> bool:                # sin repetir la consulta a Google Books entre intentos
        clave = normalizar(frase)
        if clave not in ya:
            ya[clave] = bool(cita_de_libro and cita_de_libro(frase, libros))
        return ya[clave]

    g, errores = None, []
    for intento in range(2):
        if anunciar:
            anunciar("El editor escribe el perfil" if intento == 0 else "El editor corrige el perfil")
        g, _ = llm.estructurado(f"perfil:{pieza.id}:{intento + 1}", cache_al_final(mensajes, hasta=0), GuionPerfil,
                                etapa_modelo="perfil" if intento == 0 else "perfil_correccion", max_tokens=16000)
        errores = validar(g, textos, pieza.libros, pieza.fecha, persona, de_libro if cita_de_libro else None)
        if not errores:
            return g, avisos, revisar
        avisos.append(f"Perfil: rechazado en el intento {intento + 1}: " + " | ".join(m for _, m in errores))
        mensajes += [{"role": "assistant", "content": json.dumps(g.model_dump(), ensure_ascii=False)},
                     {"role": "user", "content": "No cumple estas condiciones:\n" + "\n".join(f"- {m}" for _, m in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    if any(parte == "otro" for parte, _ in errores):
        raise ErrorLLM("Perfil: el guion no cumple las reglas tras un reintento ("
                       + " | ".join(m for p, m in errores if p == "otro") + ")")
    # Solo fallan las frases: fuera las que no se verifican (corrección mecánica, anotada)
    if any(parte == "voz" for parte, _ in errores):
        g.voz = VozPerfil(texto="", remate="", origen="entrevista", atribucion="", fuente_url="")
        avisos.append(AVISO_SIN_VOZ + ": la diapositiva de su voz sale fuera")
        revisar.append("El perfil va sin frase suya entre comillas: busca una entrevista y pídesela al chat")
    if any(parte == "prensa" for parte, _ in errores):
        antes = len(g.prensa)
        g.prensa = [p for p in g.prensa[:MAX_PRENSA] if 3 <= _palabras(p.texto) <= 30 and fuente_literal(p.texto, textos)
                    and normalizar(p.texto) != normalizar(g.voz.texto)]
        avisos.append(f"Perfil: {antes - len(g.prensa)} frases de prensa sin verificar, fuera")
    return g, avisos, revisar


def libros_del_guion(libros: list[LibroVerificado]) -> list[LibroGuion]:
    from folio.guion import titulo_para_pieza
    out = []
    for l in libros:
        es = l.edicion_es_detalle if l.edicion_es == "si" else None
        original = ", ".join(str(x) for x in (l.idioma_original, l.editorial_original, l.anio_primera_edicion) if x)
        out.append(LibroGuion(titulo=f"*{titulo_para_pieza(l)}*", autor=(l.autores or [""])[0],
                              editorial_espanola=es.editorial if es else None, traductor=es.traductor if es else None,
                              edicion_original=original or "sin datos"))
    return out


def a_guion(g: GuionPerfil, pieza: Pieza, textos: list[tuple[FuenteNoticia, str]]) -> tuple[GuionLLM, list[CitaVerificada]]:
    """Las diapositivas del perfil en el guion de siempre (para editar, comprobar hechos y publicar) y las citas
    verificadas. Los titulillos van en `subtitulo`; los hitos y la prensa, en el texto, separados por « | »."""
    d = [Diapositiva(n=1, tipo="portada", texto=g.titular.strip(), subtitulo=g.subtitulo.strip()),
         Diapositiva(n=2, tipo="actualidad", texto=g.porque_texto.strip(), subtitulo=g.porque_titulo.strip()),
         Diapositiva(n=3, tipo="trayectoria", subtitulo=g.trayectoria_titulo.strip(),
                     texto=SEP.join(f"{h.anio.strip()}{SEP_HITO}{h.texto.strip()}" for h in g.hitos)),
         Diapositiva(n=4, tipo="libro", texto=g.obra_texto.strip(), subtitulo=g.obra_titulo.strip())]
    citas: list[CitaVerificada] = []
    libro = pieza.libros[0] if pieza.libros else None
    titulo, autor = (libro.titulo_propuesto if libro else ""), persona_de(pieza)
    if g.voz.texto.strip():
        fuente = fuente_literal(g.voz.texto, textos)
        d.append(Diapositiva(n=len(d) + 1, tipo="cita", texto=_mayuscula(g.voz.texto), subtitulo=g.voz.atribucion.strip()))
        citas.append(CitaVerificada(texto=g.voz.texto.strip(), libro=titulo, autor=autor, fragmento=g.voz.texto.strip(),
                                    tipo="prensa" if fuente else "libro", fuente=fuente.url if fuente else None))
    prensa = []
    for p in g.prensa[:MAX_PRENSA]:
        fuente = fuente_literal(p.texto, textos)
        if fuente:                                       # el medio es el del texto donde está, no el que dijo el modelo
            prensa.append(f"{_mayuscula(p.texto)}{SEP_MEDIO}{fuente.medio}")
            citas.append(CitaVerificada(texto=p.texto.strip(), libro=titulo, autor=autor, fragmento=p.texto.strip(),
                                        tipo="critica" if fuente.critica else "prensa", fuente=fuente.url))
    if prensa:
        d.append(Diapositiva(n=len(d) + 1, tipo="prensa", texto=SEP.join(prensa)))
    d.append(Diapositiva(n=len(d) + 1, tipo="cierre", texto=g.cierre.strip(), subtitulo=g.cierre_texto.strip()))
    guion = GuionLLM(idea_nueva_candidatas=[], idea_elegida="", por_que=f"Perfil de {autor}", diapositivas=d,
                     pie_instagram=g.pie_instagram.strip(), libros=libros_del_guion(pieza.libros),
                     titulares_alternativos=[t for t in g.titulares_alternativos if _palabras(t) <= 14
                                             and not t.strip().endswith("?")][:5],
                     fuentes_noticia=[f"{f.medio} {f.url}" for f, _ in textos])
    return guion, citas


def _mayuscula(frase: str) -> str:
    f = frase.strip()
    return f[:1].upper() + f[1:]


def remates(g: GuionPerfil) -> list[str]:
    return [g.porque_remate.strip(), g.trayectoria_remate.strip(), g.obra_remate.strip(), g.voz.remate.strip()]


def preparar(llm: LLM, cfg: Config, pieza: Pieza, textos: list[tuple[FuenteNoticia, str]], cita_de_libro=None,
             anunciar=None) -> None:
    """Escribe el perfil en la pieza (guion, citas, remates y tono). Lanza ErrorLLM si no sale."""
    g, avisos, revisar = escribir(llm, cfg, pieza, textos, cita_de_libro, anunciar)
    pieza.guion, pieza.citas = a_guion(g, pieza, textos)
    pieza.avisos += avisos
    pieza.revision_humana += revisar
    pieza.arte = Arte(tono="grave" if g.obituario else "reflexivo", recurso="", remate=g.remate.strip(),
                      remate_cierre=g.remate_cierre.strip(), remates_noticias=remates(g),
                      antetitulo="In memoriam" if g.obituario else "Perfil")


def fichas(pieza: Pieza) -> list[tuple[FuenteNoticia, str]]:
    """Las fichas verificadas de sus libros, como un texto más para la comprobación de hechos: la trayectoria toma años
    y editoriales de ahí (en la prueba del 6/11, «Salió en España en 2015» salía como no verificado)."""
    from folio.guion import _linea_libro
    if not pieza.libros:
        return []
    return [(FuenteNoticia(medio="Fichas verificadas de los libros", titulo="Catálogos bibliográficos", url="",
                           acceso="abierto"), "\n".join(_linea_libro(l) for l in pieza.libros))]


# --- La prensa sobre la persona -----------------------------------------------------------------

def buscar_prensa(llm: LLM, cfg: Config, pieza: Pieza, ya: set[str], maximo: int = 4) -> tuple[list, list[str]]:
    """Entrevistas, reseñas y perfiles de la persona (Haiku con búsqueda, ~0,04 $): solo URLs que salieron en la búsqueda,
    que se descargan con texto y que la nombran."""
    from folio import temas
    persona = persona_de(pieza)
    if not persona:
        return [], ["sin persona a la que buscar"]
    with temas._cliente() as c:
        encontradas, avisos = temas.buscar_fuentes(llm, cfg, f"{persona}. {pieza.eleccion.titular}", c,
                                                   plantilla="prensa_autor", excluir=ya, maximo=maximo)
    fuera = [f for f in encontradas if not _apellido_en(f.texto, persona)]
    if fuera:
        avisos.append(f"descartados {len(fuera)} que no nombran a {persona} ({', '.join(f.medio for f in fuera)})")
    return [f for f in encontradas if f not in fuera], avisos


# --- El arte ------------------------------------------------------------------------------------

def estilo_del_dia(pieza: Pieza, otras: list[Pieza]) -> str:
    """«revista» (B) o «collage» (C), alternados en el día; el primero, según el día. Un obituario, siempre «revista»."""
    if pieza.arte and pieza.arte.tono == "grave":
        return "revista"
    previos = [o.arte.recurso for o in otras if o.id != pieza.id and o.eleccion.formato == FORMATO and o.arte
               and o.arte.recurso in ESTILOS]
    if previos:
        return ESTILOS[1 - ESTILOS.index(previos[-1])]
    return ESTILOS[int(hashlib.sha256(pieza.fecha.encode()).hexdigest(), 16) % 2]


def dirigir_arte(llm: LLM, cfg: Config, pieza: Pieza, otras: list[Pieza], dir_fecha: Path | None = None) -> Arte:
    """La foto de la persona y el estilo. Nunca para la pieza: sin foto, la portada es tipográfica (en «revista»)."""
    from folio import arte as direccion
    from folio.imagenes import cara, libres, recorte
    dir_fecha = dir_fecha or cfg.dir_cache(pieza.fecha)
    a = pieza.arte or Arte(tono="reflexivo", recurso="")
    a.avisos = []
    grave = a.tono == "grave"
    a.acento = None if grave else "pluma"
    a.recurso = estilo_del_dia(pieza, otras)
    a.portada = "sangre"
    retrato = direccion._retrato(cfg, pieza, a, dir_fecha) if cfg.pipeline.arte.retratos and persona_de(pieza) else None
    a.registro = "foto_autor" if retrato else None
    if a.recurso == "collage":
        motivo = "no hay foto de la persona" if not retrato else recorte.se_puede(retrato)
        if not motivo:
            try:
                recorte.aplicar(cfg, pieza.id, dir_fecha, "papel", a.acento)
                a.registro = "recorte"
                retrato = True
            except Exception as exc:
                motivo = f"no se pudo recortar ({type(exc).__name__}: {exc})"[:160]
        if motivo:
            a.avisos.append(f"Perfil: sin collage ({motivo}); va en «revista»")
            a.recurso = "revista"
    if retrato:
        aviso = cara.encuadrar(llm, cfg, f"{pieza.id}-retrato", dir_fecha)
        if aviso:
            a.avisos.append(aviso)
        img = libres.de_pieza(f"{pieza.id}-retrato", dir_fecha)
        a.retrato = img.credito if img else a.retrato
    return a


# --- Al editar ----------------------------------------------------------------------------------

def hitos_de(texto: str) -> list[tuple[str, str]]:
    """«2004: Primer libro | 2026: Premio Herralde» → [(«2004», «Primer libro»), …]. Lo que no casa, sin año."""
    out = []
    for parte in (x.strip() for x in texto.split("|")):
        if not parte:
            continue
        m = re.match(r"^(\d{4})\s*[:—–-]\s*(.+)$", parte)
        out.append((m.group(1), m.group(2).strip()) if m else ("", parte))
    return out


def prensa_de(texto: str) -> list[tuple[str, str]]:
    """«Frase — Medio | Otra — Medio» → [(frase, medio), …]."""
    out = []
    for parte in (x.strip() for x in texto.split("|")):
        if parte:
            frase, _, medio = parte.rpartition(SEP_MEDIO.strip()) if SEP_MEDIO.strip() in parte else (parte, "", "")
            out.append((frase.strip().strip("«»\"").strip(), medio.strip()))
    return out


def validar_edicion(cfg: Config, p: Pieza, g: GuionLLM) -> list[str]:
    """Las reglas de un perfil ya escrito, al editarlo a mano o desde el chat: las frases entre comillas (su voz y la
    prensa) solo pueden ser las ya verificadas; la trayectoria sigue con años; nada de comillas sueltas."""
    from folio.guion import citas_entre_comillas
    errores = []
    verificadas = {normalizar(c.texto) for c in p.citas}
    for d in g.diapositivas:
        if d.tipo == "portada" and _palabras(d.texto) > 14:
            errores.append(f"El titular tiene {_palabras(d.texto)} palabras; máximo 14.")
        if d.tipo == "cita" and normalizar(d.texto) not in verificadas:
            errores.append(f"La frase de la diapositiva {d.n} tiene que ser una de las ya verificadas (va entre comillas).")
        if d.tipo == "prensa":
            for frase, _ in prensa_de(d.texto):
                if normalizar(frase) not in verificadas:
                    errores.append(f"La frase de prensa «{frase[:50]}» no está verificada.")
        if d.tipo == "trayectoria" and any(not anio for anio, _ in hitos_de(d.texto)):
            errores.append("Cada hito de la trayectoria empieza por su año: «2004: Primer libro | 2026: Premio…».")
        if d.tipo not in ("cita", "prensa"):
            for frase in citas_entre_comillas([d.texto, d.subtitulo or ""], p.libros):
                if normalizar(frase) not in verificadas:
                    errores.append(f"Texto entre comillas sin verificar en la diapositiva {d.n}: «{frase[:50]}».")
    return errores
