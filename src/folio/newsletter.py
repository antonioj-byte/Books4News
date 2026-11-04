"""«La newsletter del jueves» (4/11, a petición del usuario: «cada jueves publicamos en la newsletter un ensayo largo
que normalmente firmo yo; me gustaría que haya una versión corta en Instagram»; la opción C del Artifact «La newsletter
del jueves», con la ronda 2: sin foto a sangre, quien firma en un botón arriba, una ilustración por frase).

La redacción pega el texto de la newsletter y:
1. El editor (Opus, `prompts/newsletter.md`) elige el titular (una frase del ensayo, entre comillas), escribe el
   subtítulo y la percha, elige seis frases literales (van cuatro) y escribe las escenas. El código comprueba que el
   titular y las frases están letra por letra en el texto (salvo mayúsculas, tildes y signos) y reintenta una vez.
2. Cinco ilustraciones a la vez (portada y cuatro frases), en el estilo de ilustración que toque en el día (collage o
   grabado), con el revisor de letras.
3. Comprobación de hechos de la percha contra el texto de la newsletter y la noticia que enlaza.
Carrusel: portada (píldora «Opinión», titular entre comillas, subtítulo y el botón con la foto, nombre y cargo de quien
firma) → percha → cuatro frases → cierre con la dirección de la newsletter → colofón.
"""

from __future__ import annotations

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from folio.config import Config
from folio.llm import LLM, ErrorLLM, cache_al_final, cargar_prompt
from folio.modelos import Arte, Diapositiva, FuenteNoticia, GuionLLM, HistoriaElegida, Pieza

FORMATO = "newsletter"
PREFIJO = "newsletter-"
SUFIJO_FRASE = "-frase"          # <pieza>-frase-1.jpg … <pieza>-frase-4.jpg (la portada es <pieza>.jpg)
ARCHIVO_FRASE = "magnific:newsletter"   # no cuentan para el tope diario de ilustraciones editoriales
N_FRASES = 4
N_CANDIDATAS = 6
MIN_TEXTO = 400                  # caracteres: menos no es un ensayo
FOTO_AUTOR = "autor.jpg"         # data/cache/newsletter/autor.jpg: la foto de quien firma, subida una vez
_URL = re.compile(r"https?://[^\s)\]]+")


class FraseNewsletter(BaseModel):
    texto: str = Field(description="La frase, copiada letra por letra del texto, sin comillas; de 4 a 30 palabras")
    remate: str = Field(description="Su final literal, de 1 a 6 palabras")
    escena: str = Field(description="En inglés, de 15 a 45 palabras: la metáfora visual de su ilustración")


class GuionNewsletter(BaseModel):
    titular: str = Field(description="Una frase del ensayo, letra por letra, sin comillas; de 4 a 20 palabras")
    remate: str = Field(description="El final literal del titular, de 2 a 5 palabras")
    subtitulo: str = Field(description="De 8 a 20 palabras, o vacío si el titular se entiende solo")
    percha: str = Field(description="La noticia que motiva el ensayo, de 12 a 35 palabras; vacío si no la hay")
    percha_url: str = Field(description="El enlace de la percha, copiado del texto; vacío si no hay")
    frases: list[FraseNewsletter] = Field(description="Seis frases literales, por orden de preferencia")
    cierre: str = Field(description="La frase final del ensayo que cierra el carrusel, letra por letra; de 3 a 15 palabras")
    remate_cierre: str = Field(description="El final literal de la frase de cierre, de 1 a 5 palabras")
    escena_portada: str = Field(description="En inglés, de 15 a 45 palabras: la ilustración de la portada")
    pie_instagram: str = Field(description="De 60 a 150 palabras")


# --- Comprobaciones -----------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Para comparar literales: sin tildes, mayúsculas, signos ni espacios de más (los cursivas *así* tampoco cuentan)."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", t).split())


def literal(frase: str, texto: str) -> bool:
    f = normalizar(frase)
    return bool(f) and f" {f} " in f" {normalizar(texto)} "


def _palabras(t: str) -> int:
    return len(t.split())


def _remate_valido(frase: str, remate: str, minimo: int, maximo: int) -> bool:
    f, r = normalizar(frase), normalizar(remate)
    return bool(r) and minimo <= len(r.split()) <= maximo and f.endswith(r) and f != r


def validar(g: GuionNewsletter, texto: str) -> list[str]:
    """Los errores del guion (lista vacía si vale)."""
    from folio.imagenes.editorial import validar_escena
    errores = []
    if not 4 <= _palabras(g.titular) <= 20:
        errores.append(f"El titular tiene que tener de 4 a 20 palabras (tiene {_palabras(g.titular)}).")
    if not literal(g.titular, texto):
        errores.append("El titular tiene que ser una frase del ensayo copiada letra por letra.")
    if not _remate_valido(g.titular, g.remate, 2, 5):
        errores.append("El remate del titular tiene que ser su final literal, de 2 a 5 palabras.")
    if g.subtitulo.strip() and not 8 <= _palabras(g.subtitulo) <= 20:
        errores.append(f"El subtítulo tiene que tener de 8 a 20 palabras o ir vacío (tiene {_palabras(g.subtitulo)}).")
    if g.percha.strip() and not 12 <= _palabras(g.percha) <= 35:
        errores.append(f"La percha tiene que tener de 12 a 35 palabras o ir vacía (tiene {_palabras(g.percha)}).")
    if g.percha_url.strip() and g.percha_url.strip() not in texto:
        errores.append("El enlace de la percha tiene que estar tal cual en el texto.")
    if len(g.frases) < N_FRASES:
        errores.append(f"Hacen falta al menos {N_FRASES} frases (hay {len(g.frases)}).")
    vistas = {normalizar(g.titular)}
    for i, f in enumerate(g.frases, 1):
        if not 4 <= _palabras(f.texto) <= 30:
            errores.append(f"Frase {i}: tiene que tener de 4 a 30 palabras (tiene {_palabras(f.texto)}).")
        if not literal(f.texto, texto):
            errores.append(f"Frase {i}: tiene que estar letra por letra en el texto («{f.texto[:60]}»).")
        if _URL.search(f.texto):
            errores.append(f"Frase {i}: no puede llevar enlaces.")
        if not _remate_valido(f.texto, f.remate, 1, 6):
            errores.append(f"Frase {i}: el remate tiene que ser su final literal, de 1 a 6 palabras.")
        if normalizar(f.texto) in vistas:
            errores.append(f"Frase {i}: repite otra frase o el titular.")
        vistas.add(normalizar(f.texto))
        if i <= N_FRASES:
            _, motivo = validar_escena(f.escena, max_palabras=45)
            if motivo:
                errores.append(f"Frase {i}, escena: {motivo}.")
    if not 3 <= _palabras(g.cierre) <= 15 or not literal(g.cierre, texto):
        errores.append("La frase de cierre tiene que estar letra por letra en el texto, de 3 a 15 palabras.")
    elif not _remate_valido(g.cierre, g.remate_cierre, 1, 5):
        errores.append("El remate del cierre tiene que ser su final literal, de 1 a 5 palabras.")
    _, motivo = validar_escena(g.escena_portada, max_palabras=45)
    if motivo:
        errores.append(f"Escena de la portada: {motivo}.")
    if not 50 <= _palabras(g.pie_instagram) <= 170:
        errores.append(f"El pie tiene que tener de 60 a 150 palabras (tiene {_palabras(g.pie_instagram)}).")
    return errores


# --- Escribir -------------------------------------------------------------------------------------

def escribir(llm: LLM, cfg: Config, fecha: str, texto: str) -> tuple[GuionNewsletter, list[str]]:
    """El guion de la newsletter. ErrorLLM si el texto es demasiado corto o si no valida tras un reintento."""
    from folio.guion import linea_hoy
    if len(texto.strip()) < MIN_TEXTO:
        raise ErrorLLM(f"El texto de la newsletter es demasiado corto ({len(texto.strip())} caracteres)")
    nl = cfg.pipeline.newsletter
    prompt = cargar_prompt(cfg, "newsletter", {"[pegar autor]": nl.autor, "[pegar cargo]": nl.cargo,
                                               "[pegar hoy]": linea_hoy(fecha), "[pegar texto]": texto.strip()})
    mensajes = [{"role": "user", "content": prompt}]
    avisos, errores = [], []
    for intento in range(2):
        g, _ = llm.estructurado(f"newsletter:{fecha}:{intento + 1}", cache_al_final(mensajes, hasta=0), GuionNewsletter,
                                etapa_modelo="newsletter", max_tokens=16000)
        errores = validar(g, texto)
        if not errores:
            return g, avisos
        avisos.append(f"Newsletter: rechazado en el intento {intento + 1}: " + " | ".join(errores))
        mensajes += [{"role": "assistant", "content": json.dumps(g.model_dump(), ensure_ascii=False)},
                     {"role": "user", "content": "No cumple estas condiciones:\n" + "\n".join(f"- {e}" for e in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    raise ErrorLLM("Newsletter: el guion no cumple las reglas tras un reintento (" + " | ".join(errores) + ")")


def pie_completo(cfg: Config, pie: str) -> str:
    nl = cfg.pipeline.newsletter
    return f"{pie.strip()}\n\nLéelo entero en {nl.url} (enlace en la bio)."


def a_pieza(cfg: Config, g: GuionNewsletter, pieza_id: str, fecha: str, texto: str) -> Pieza:
    nl = cfg.pipeline.newsletter
    frases = g.frases[:N_FRASES]
    diapositivas = [Diapositiva(n=1, tipo="portada", texto=_mayuscula(g.titular), subtitulo=g.subtitulo.strip() or None)]
    if g.percha.strip():
        diapositivas.append(Diapositiva(n=len(diapositivas) + 1, tipo="actualidad", texto=g.percha.strip()))
    for f in frases:
        diapositivas.append(Diapositiva(n=len(diapositivas) + 1, tipo="cita", texto=_mayuscula(f.texto)))
    diapositivas.append(Diapositiva(n=len(diapositivas) + 1, tipo="cierre", texto=_mayuscula(g.cierre)))
    fuentes = [FuenteNoticia(medio=nl.nombre, titulo=g.titular.strip(), url=f"https://{nl.url}", acceso="abierto",
                             publicado=fecha)]
    if g.percha_url.strip():
        fuentes.append(FuenteNoticia(medio=_medio_de(g.percha_url), titulo=g.percha.strip(), url=g.percha_url.strip(),
                                     acceso="abierto"))
    guion = GuionLLM(idea_nueva_candidatas=[], idea_elegida="", por_que=f"Versión corta del ensayo de {nl.nombre}",
                     diapositivas=diapositivas, pie_instagram=pie_completo(cfg, g.pie_instagram), libros=[],
                     fuentes_noticia=[f"{f.medio} {f.url}" for f in fuentes])
    eleccion = HistoriaElegida(formato=FORMATO, historia_id=PREFIJO + fecha, titular=g.titular.strip(),
                               de_que_se_habla=g.subtitulo.strip() or g.titular.strip(),
                               cuestion_de_fondo=g.subtitulo.strip(), libros_candidatos=[], gancho_libro="",
                               por_que=f"El ensayo del jueves de {nl.nombre}, firmado por {nl.autor}",
                               encargo=texto.strip())
    reserva = [f"«{f.texto.strip()}»" for f in g.frases[N_FRASES:]]
    return Pieza(id=pieza_id, fecha=fecha, estado="propuesta", historia_id=PREFIJO + fecha, eleccion=eleccion, n_medios=1,
                 guion=guion, fuentes=fuentes,
                 avisos=[f"La newsletter del jueves: firmada por {nl.autor}, en primera persona (excepción del formato)"]
                 + ([f"Frases de reserva: {' · '.join(reserva)}"] if reserva else []),
                 arte=Arte(tono="reflexivo", recurso="ilustracion", portada="sangre", remate=g.remate.strip(),
                           remate_cierre=g.remate_cierre.strip(),
                           escena=g.escena_portada.strip(), remates_noticias=[f.remate.strip() for f in frases],
                           escenas_noticias=[f.escena.strip() for f in frases]))


def _mayuscula(frase: str) -> str:
    """Una frase que empieza a mitad de una oración del texto, con mayúscula (la comprobación literal no mira mayúsculas)."""
    f = frase.strip()
    return f[:1].upper() + f[1:]


def _medio_de(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url.strip())
    return m.group(1) if m else "Fuente"


# --- Las ilustraciones ------------------------------------------------------------------------------

def clave_frase(pieza_id: str, i: int) -> str:
    return f"{pieza_id}{SUFIJO_FRASE}-{i}"


def _una(llm: LLM, cfg: Config, pieza: Pieza, i: int, nombre_estilo: str, intentos: int = 2) -> str | None:
    """La ilustración i (0, la portada; 1–4, las frases). None si salió; si no, el motivo."""
    from folio.imagenes import editorial, libres
    from folio.imagenes import retrato_generado as rg
    dir_fecha = cfg.dir_cache(pieza.fecha)
    escena = pieza.arte.escena if i == 0 else pieza.arte.escenas_noticias[i - 1]
    clave = pieza.id if i == 0 else clave_frase(pieza.id, i)
    descartes = []
    for _ in range(intentos):
        try:
            dibujo = editorial.dibujar(cfg, clave, escena, nombre_estilo=nombre_estilo)
        except rg.ErrorMagnific as exc:
            return f"{'portada' if i == 0 else f'frase {i}'}: no se pudo dibujar ({exc})"
        motivo = editorial.revisar(llm, cfg, pieza.id, dibujo)
        if motivo is None:
            img = editorial.fijar(cfg, clave, dir_fecha, escena, dibujo, nombre_estilo)
            if i:                                  # las de las frases no cuentan para el tope de ilustraciones del día
                from dataclasses import replace
                libres.guardar_metadatos(replace(img, archivo=ARCHIVO_FRASE), clave, dir_fecha)
            return None
        descartes.append(motivo)
    return f"{'portada' if i == 0 else f'frase {i}'}: el revisor encontró letras ({' | '.join(descartes)})"


def ilustrar(llm: LLM, cfg: Config, pieza: Pieza) -> list[str]:
    """Las cinco ilustraciones, a la vez y en el mismo estilo. Devuelve los motivos de las que no salieron (esas
    diapositivas van sin ilustración)."""
    from folio.imagenes import editorial
    nombre_estilo = editorial.estilo_de_pieza(cfg, pieza.id, cfg.dir_cache(pieza.fecha))
    n = 1 + len(pieza.arte.escenas_noticias)
    with ThreadPoolExecutor(max_workers=n) as pool:
        motivos = list(pool.map(lambda i: _una(llm, cfg, pieza, i, nombre_estilo), range(n)))
    if motivos[0] is None:
        from folio.imagenes import libres
        img = libres.de_pieza(pieza.id, cfg.dir_cache(pieza.fecha))
        pieza.arte.imagen, pieza.arte.registro = img.archivo, "ilustracion"
    if any(m is None for m in motivos):
        pieza.arte.credito = "Ilustraciones generadas con IA (Magnific) para Folio"
    return [m for m in motivos if m]


# --- La foto de quien firma -------------------------------------------------------------------------

def ruta_foto(cfg: Config) -> Path:
    """En data/cache/newsletter/: la web sirve las imágenes de data/cache/ (/api/medios/)."""
    return cfg.dir_cache("x").parent / "newsletter" / FOTO_AUTOR


def guardar_foto(cfg: Config, datos: bytes) -> Path:
    """La foto de quien firma, vuelta a codificar en JPEG cuadrado de 600 px (comprueba que es una imagen y quita los
    metadatos). Se sube una vez y vale para todos los jueves."""
    from io import BytesIO

    from PIL import Image, ImageOps
    with Image.open(BytesIO(datos)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im = ImageOps.fit(im, (600, 600), centering=(0.5, 0.35))
    ruta = ruta_foto(cfg)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    im.save(tmp, "JPEG", quality=88)
    tmp.replace(ruta)
    return ruta


# --- Todo junto -------------------------------------------------------------------------------------

def preparar(tuberia, texto: str, pieza_id: str, dibujar: bool = True) -> Pieza:
    """Escribe, ilustra y comprueba la pieza. Si falla el guion, sale «fallida» con el motivo; las ilustraciones y la
    comprobación nunca la paran."""
    from folio import hechos
    cfg, llm, fecha = tuberia.cfg, tuberia.llm, tuberia.fecha
    try:
        g, avisos = escribir(llm, cfg, fecha, texto)
    except ErrorLLM as exc:
        e = HistoriaElegida(formato=FORMATO, historia_id=PREFIJO + fecha, titular="La newsletter del jueves",
                            de_que_se_habla="", cuestion_de_fondo="", libros_candidatos=[], por_que="")
        return Pieza(id=pieza_id, fecha=fecha, estado="fallida", historia_id=PREFIJO + fecha, eleccion=e, n_medios=0,
                     error=str(exc)[:400])
    pieza = a_pieza(cfg, g, pieza_id, fecha, texto)
    pieza.avisos += avisos
    from folio.pipeline import progreso
    if dibujar:
        progreso("La newsletter: las ilustraciones de la portada y las frases")
        for motivo in ilustrar(llm, cfg, pieza):
            pieza.avisos.append(f"Newsletter: sin ilustración en la {motivo}")
    # La percha y el pie, contra el texto de la newsletter con quien firma (y la noticia de la percha, si se lee)
    progreso("La newsletter: comprobando la percha y el pie")
    nl = cfg.pipeline.newsletter
    firma = f"Firma el ensayo {nl.autor}, {nl.cargo[:1].lower() + nl.cargo[1:]}, en {nl.nombre}.\n\n"
    try:
        textos = [(pieza.fuentes[0], firma + texto.strip())] + _texto_de_la_percha(pieza)
        pieza.hechos = hechos.comprobar(llm, pieza.id, pieza.guion, textos)
    except Exception as exc:                        # la comprobación nunca para la pieza
        pieza.avisos.append(f"No se pudo comprobar los hechos: {type(exc).__name__}: {exc}"[:300])
    return pieza


def _texto_de_la_percha(pieza: Pieza) -> list[tuple[FuenteNoticia, str]]:
    """El texto de la noticia que enlaza la percha, si se puede descargar (ante 403/429, sin él: no se reintenta)."""
    if len(pieza.fuentes) < 2:
        return []
    from folio import temas
    with temas._cliente() as c:
        fuente, motivo = temas.descargar(pieza.fuentes[1].url, c)
    if not fuente:
        pieza.avisos.append(f"La noticia de la percha no se pudo leer ({motivo}): se comprueba solo contra la newsletter")
        return []
    pieza.fuentes[1].medio = fuente.medio
    return [(pieza.fuentes[1], fuente.texto)]
