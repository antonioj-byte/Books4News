"""Edición de una pieza desde la web: a mano, sobre la diapositiva, o con el chat de edición.

- A mano (paso 4 del plan de la Fase 3): el texto de una diapositiva se cambia tal cual. Se aplican
  las correcciones mecánicas (numeración, firma de Folio en el cierre) y se valida con las reglas del
  guion; si alguna no pasa, la versión se guarda igual, con los avisos a la vista.
- Con el chat (paso 5): el modelo (prompts/chat_edicion.md) contesta y, si hay que cambiar algo,
  devuelve el guion completo revisado. Ese guion no puede romper ninguna regla que la pieza cumpliera: si
  lo hace, se le devuelven los errores para que corrija en el mismo turno; si sigue sin pasar, no se
  cambia nada. Lo que ya incumplía antes (p. ej. tras una edición a mano) no bloquea el chat. No puede añadir
  libros (los libros salen del verificador) ni citas que no estén ya verificadas.

Los cambios del chat pueden traer datos que no estaban: la pieza pasa a revisión humana.

El chat también puede cambiar la imagen (1/11, a petición del usuario): reencuadrar la de portada, cambiar la
composición, usar la foto del autor o la de archivo, buscar otra imagen de archivo (el director de arte
elige en la hoja de contactos) o dibujar una ilustración editorial nueva (con el tope diario de Magnific).
Lo aplica el código (aplicar_imagen), con las mismas comprobaciones que la etapa de arte.
"""

from __future__ import annotations

import json
import re

from typing import Literal

from pydantic import BaseModel, Field

from folio import guion as guionista
from folio.config import Config
from folio.llm import LLM, cache_al_final, cargar_prompt
from folio.modelos import GuionLLM, Pieza
from folio.verificacion_texto import normalizar

AVISO_CHAT = "Editada con el chat: comprueba los datos nuevos (no se han vuelto a cotejar con las fuentes)"


class AccionImagen(BaseModel):
    """Un cambio en la imagen de la pieza, que aplica el código."""
    tipo: Literal["encuadre", "composicion", "usar_foto_autor", "usar_archivo", "buscar_archivo", "ilustrar",
                  "buscar_retrato", "retrato_ilustrado", "usar_material", "formato", "cubierta", "friso", "cambiar_libro"] = Field(
        description="encuadre: mover el punto de interés de la imagen de portada; composicion: sangre, banda, caja o neon; "
                    "usar_foto_autor / usar_archivo: qué imagen va en la portada; buscar_archivo: otra imagen de archivo con "
                    "nuevas búsquedas; ilustrar: una ilustración editorial nueva con una escena (sin personas reales); "
                    "buscar_retrato: buscar la foto libre de una persona real (autor o protagonista) para la portada; "
                    "retrato_ilustrado: pasar esa foto a ilustración en un estilo de la casa; "
                    "usar_material: poner en la pieza una foto que ha subido quien edita; "
                    "formato: destacado del titular, antetítulo o color de la pieza; "
                    "cubierta: la cubierta (y la ficha) de otra edición en castellano de un libro, por su editorial o ISBN; "
                    "friso: dibujar de nuevo (o quitar) la ilustración en banda que cruza las tres fichas de «Tres libros»; "
                    "cambiar_libro: cambiar el libro de la pieza por otro (se verifica) y dejarla lista para reescribirla")
    enfoque_x: int = Field(description="Solo encuadre: 0–100, dónde está lo importante en horizontal (50 = centro)")
    enfoque_y: int = Field(description="Solo encuadre: 0–100, en vertical (0 = arriba; para ver una cara entera, 20–35)")
    composicion: str = Field(description="Solo composicion: sangre, banda, caja o neon; si no, vacío")
    consultas: list[str] = Field(description="Solo buscar_archivo: 3 o 4 búsquedas de 1 a 3 palabras, en inglés; si no, vacía")
    escena: str = Field(description="Solo ilustrar o friso: la escena en inglés, de 12 a 70 palabras, sin nombres propios, cifras ni comillas (en el friso, un paisaje continuo con un motivo por libro de izquierda a derecha; vacía, la escribe el ilustrador; «ninguno», quita el friso); si no, vacío")
    persona: str = Field(description="Solo buscar_retrato: nombre completo de la persona real (el autor del libro o quien protagoniza la historia); si no, vacío")
    estilo: str = Field(description="Solo retrato_ilustrado: low_poly, voxel, render_2000 o dithering (vacío: el que va con el tono); si no, vacío")
    material: str = Field(description="Solo usar_material: el id del material (la foto subida); si no, vacío")
    como: str = Field(description="Solo usar_material: «portada» (la imagen de la portada) o «retrato» (la foto del autor o protagonista); si no, vacío")
    destacado: str = Field(description="Solo formato: el trozo del titular de portada que va destacado (cursiva en el color de la casa, con marcador sobre foto), copiado letra por letra, de 1 a 6 palabras; «ninguno» lo quita; vacío, no se toca")
    antetitulo: str = Field(description="Solo formato: el antetítulo de la portada, de 1 a 3 palabras; «ninguno» lo quita; vacío, no se toca")
    acento: str = Field(description="Solo formato: el color de la pieza, «pluma» (rojo) o «marcador» (amarillo); «ninguno» lo quita; vacío, no se toca")
    libro: str = Field(description="Solo cubierta: el título del libro de la pieza cuya cubierta se cambia; solo cambiar_libro: el título del libro nuevo, tal como lo da quien edita; si no, vacío")
    autor: str = Field(description="Solo cambiar_libro: el autor del libro nuevo; si no, vacío")
    sin_castellano: str = Field(description="Solo cambiar_libro: «si» solo si quien edita pide expresamente ese libro aunque no tenga edición en castellano; si no, vacío")
    editorial: str = Field(description="Solo cubierta: la editorial de la edición en castellano que se quiere («Mondadori»); si no, vacío")
    isbn: str = Field(description="Solo cubierta: el ISBN de esa edición, si lo da quien edita; si no, vacío")


class RespuestaChat(BaseModel):
    respuesta: str = Field(description="Lo que contestas a quien edita: breve, en español")
    guion: GuionLLM | None = Field(default=None, description="El guion completo revisado, solo si hay que cambiar algo; null si no")
    imagen: AccionImagen | None = Field(default=None, description="Un cambio en la imagen, solo si lo piden; null si no")


def _citas_ok(p: Pieza, tipo: str = "libro") -> frozenset[str]:
    return frozenset(normalizar(c.texto) for c in p.citas if c.tipo == tipo)


def validar(cfg: Config, p: Pieza, g: GuionLLM) -> list[str]:
    """Las citas que valen son las que ya se verificaron al escribir la pieza (del libro y de la crítica)."""
    return guionista.validar(cfg, g, p.libros, p.fuentes, _citas_ok(p), _citas_ok(p, "critica"), p.eleccion.formato)


def editar_diapositiva(cfg: Config, p: Pieza, n: int, texto: str, subtitulo: str | None = None) -> tuple[Pieza, list[str]]:
    """La pieza con la diapositiva n cambiada a mano y los avisos (reglas que no cumple)."""
    nueva = p.model_copy(deep=True)
    d = nueva.guion.diapositivas[n - 1]
    d.texto = " ".join(texto.split())
    if d.tipo == "portada":
        d.subtitulo = " ".join((subtitulo or "").split()) or None
    guionista.corregir_mecanico(nueva.guion)
    return nueva, validar(cfg, nueva, nueva.guion)


def _buscar_retrato(cfg: Config, p: Pieza, nueva: Pieza, ar, a: AccionImagen, dir_fecha) -> tuple[Pieza | None, str]:
    """La foto libre de una persona real para la portada (Commons; si no, la de prensa de su editorial). Nunca se
    genera una cara desde cero (regla del usuario): sin foto con licencia comprobada, no hay retrato."""
    from folio import arte as direccion
    from folio.imagenes import prensa, retratos
    persona = " ".join(a.persona.split()) or direccion.autor_principal(p) or ""
    if not persona:
        return None, "(Dime de quién es el retrato: el nombre completo de la persona.)"
    from folio.verificacion_texto import autor_coincide
    principal = direccion.autor_principal(p)
    # Por apellido, no letra por letra: «Gonçalo Tavares» es «Gonçalo M. Tavares» (2/11, el editor se negó a su retrato)
    if p.libros and principal and not autor_coincide(persona, [principal]):
        return None, f"(El retrato de la portada es el del autor del libro, {principal}; no se pone la cara de otra persona.)"
    img, motivo = retratos.buscar_y_fijar(persona, p.id, dir_fecha, cfg.pipeline.arte.retratos_cc_by_sa)
    if not img and cfg.pipeline.arte.fotos_editoriales and p.libros:
        from folio.infografia import libro_principal
        libro = libro_principal(p)
        editorial = libro.edicion_es_detalle.editorial if libro and libro.edicion_es_detalle else None
        try:
            img, motivo = prensa.buscar_y_fijar(persona, editorial, p.id, dir_fecha)
        except prensa.BloqueoEditorial as exc:
            motivo = str(exc)
    if not img:
        return None, (f"(No hay una foto de {persona} con licencia libre: {motivo}. Sin ella no puedo poner su cara, ni "
                      "dibujarla: una cara solo se ilustra a partir de una foto con la licencia comprobada.)")
    if not p.libros:
        nueva.eleccion.protagonista = persona         # sin libro, la cara que vale es la de quien protagoniza la historia
    ar.registro, ar.retrato = "foto_autor", img.credito
    if ar.portada == "panorama":
        ar.portada = cfg.pipeline.arte.portadas[0]
    return nueva, f"(Retrato de {persona} en la portada: {img.credito}.)"


def _retrato_ilustrado(cfg: Config, nueva: Pieza, ar, a: AccionImagen, retrato, dir_fecha) -> tuple[Pieza | None, str]:
    """El retrato pasado a un estilo de la casa (Magnific), siempre a partir de la foto libre ya fijada; nunca de la
    de prensa (la cesión es para publicarla, no para obras derivadas)."""
    from folio import arte as direccion
    from folio.imagenes import prensa, retrato_generado
    if not retrato:
        return None, "(Primero hace falta una foto libre de la persona: pide que busque su retrato.)"
    if prensa.es_de_prensa(retrato):
        return None, "(Es una foto de prensa de la editorial: se puede publicar tal cual, pero no transformarla.)"
    from folio import materiales
    if materiales.es_material(retrato):
        return None, "(Es una foto subida por quien edita: se puede publicar tal cual, pero no transformarla con IA.)"
    if ar.tono == "grave":
        return None, "(En piezas graves el retrato va en foto, sin ilustrar.)"
    estilos = ["low_poly", "voxel", "render_2000", "dithering"]
    estilo = a.estilo.strip() if a.estilo.strip() in estilos else (cfg.pipeline.arte.retrato_generado.por_tono.get(ar.tono) or ["low_poly"])[0]
    try:
        img = retrato_generado.aplicar(cfg, nueva.id, dir_fecha, estilo)
    except Exception as exc:
        return None, f"(No se pudo ilustrar el retrato: {exc}.)"
    ar.registro, ar.retrato = "retrato_ia", img.credito
    if direccion.AVISO_RETRATO_GENERADO not in nueva.revision_humana:
        nueva.revision_humana.append(direccion.AVISO_RETRATO_GENERADO)
    if ar.portada == "panorama":
        ar.portada = cfg.pipeline.arte.portadas[0]
    return nueva, f"(Retrato ilustrado en estilo {estilo.replace('_', ' ')}, a partir de la foto libre. Comprueba el parecido.)"


def _copiar_imagenes(dir_fecha, pid: str) -> dict:
    from folio.imagenes import libres
    carpeta = libres.dir_imagenes(dir_fecha)
    return {f: f.read_bytes() for patron in (f"{pid}.*", f"{pid}-noticia.*") for f in carpeta.glob(patron)} if carpeta.exists() else {}


def _restaurar_imagenes(dir_fecha, copia: dict) -> None:
    for f, datos in copia.items():
        f.write_bytes(datos)


def _bloque_pieza(p: Pieza) -> str:
    libros = "\n".join(f"- {l.titulo_propuesto} ({', '.join(l.autores)}; edición española: {l.edicion_es})" for l in p.libros)
    citas = "\n".join(f"- «{c.texto}»" for c in p.citas) or "(ninguna)"
    return (f"<pieza>\nnoticia: {p.eleccion.titular}\nde qué se habla: {p.eleccion.de_que_se_habla}\n"
            f"libros verificados (los únicos posibles):\n{libros}\ncitas verificadas (las únicas que pueden ir entre comillas):\n{citas}\n"
            f"guion actual (JSON):\n{p.guion.model_dump_json(indent=1)}\n</pieza>")


def chat(llm: LLM, cfg: Config, p: Pieza, historial: list[tuple[str, str]], mensaje: str) -> tuple[str, Pieza | None, list[str]]:
    """Un turno del chat. `historial`: [(rol, texto)] de los turnos anteriores. Devuelve (respuesta,
    pieza nueva o None si no hay cambios, avisos)."""
    sistema = cargar_prompt(cfg, "chat_edicion", {"[pegar pieza]": _bloque_pieza(p)})
    mensajes = [{"role": "user" if rol == "usuario" else "assistant", "content": texto} for rol, texto in historial]
    from folio import materiales
    avisos_enlaces = leer_enlaces(cfg, p, mensaje)   # los enlaces del mensaje, como material de texto (2/11)
    extra = materiales.bloques(cfg, p)          # lo que ha subido quien edita (2/11), como datos delimitados
    ultimo = [*extra, {"type": "text", "text": mensaje}] if extra else mensaje
    mensajes = [{"role": "user", "content": sistema}, {"role": "assistant", "content": "Entendido. ¿Qué cambiamos?"},
                *mensajes, {"role": "user", "content": ultimo}]
    avisos: list[str] = list(avisos_enlaces)
    previos = set(validar(cfg, p, p.guion))
    for intento in range(cfg.pipeline.guion.reintentos + 1):
        r, contenido = llm.estructurado(f"chat:{p.id}:{intento + 1}", cache_al_final(mensajes), RespuestaChat, etapa_modelo="chat")
        if r.guion is None and _dice_que_cambio_el_texto(r.respuesta) and intento < cfg.pipeline.guion.reintentos:
            # 2/11: el editor describió cambios en el texto, devolvió solo un cambio de imagen y la «versión nueva» no
            # tenía el texto nuevo. Si dice que ha cambiado el texto, tiene que traer el guion
            avisos.append("El editor describió cambios en el texto sin devolver el guion; se le pide entero")
            mensajes += [{"role": "assistant", "content": json.dumps(r.model_dump(mode="json"), ensure_ascii=False)},
                         {"role": "user", "content": "Dices que has cambiado el texto, pero `guion` va a null y el cambio no se "
                          "guardaría. Devuelve el JSON con el guion completo revisado (y la imagen, si la cambias)."}]
            continue
        if r.guion is None:
            if r.imagen is None:
                return r.respuesta, None, avisos
            nueva, nota = _imagen_sin_romper(llm, cfg, p, r.imagen)
            return (f"{r.respuesta} {nota}".strip()), nueva, avisos
        guionista.corregir_mecanico(r.guion)
        errores = [e for e in validar(cfg, p, r.guion) if e not in previos]
        if not errores:
            nueva = p.model_copy(deep=True)
            nueva.guion = r.guion
            nueva.discrepancias_edicion = guionista.ajustar_libros(nueva.guion, nueva.libros)
            nueva.revisar_edicion = bool(nueva.discrepancias_edicion)
            if AVISO_CHAT not in nueva.revision_humana:
                nueva.revision_humana.append(AVISO_CHAT)
            if r.imagen is not None:
                con_imagen, nota = _imagen_sin_romper(llm, cfg, nueva, r.imagen)
                return f"{r.respuesta} {nota}".strip(), con_imagen or nueva, avisos
            return r.respuesta, nueva, avisos
        avisos.append(f"Intento {intento + 1} rechazado: " + " | ".join(errores))
        mensajes += [{"role": "assistant", "content": json.dumps(r.model_dump(mode="json"), ensure_ascii=False)},
                     {"role": "user", "content": "El guion no cumple estas condiciones:\n" + "\n".join(f"- {e}" for e in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    return ("No he podido hacer ese cambio sin romper las reglas de Folio: " + "; ".join(errores)), None, avisos


# Un verbo de cambio en pasado o en presente («he acortado», «acorto», «amplío»); un número de diapositiva suelto no
# basta (2/11: «siguen pendientes las diapositivas 2 a 5» hacía pedir el guion entero)
_CAMBIO_DE_TEXTO = re.compile(r"\b(he|hemos)\s+(reescrito|cambiado|quitado|eliminado|añadido|ajustado|acortado|ampliado|"
                              r"sustituido|rehecho|corregido|reformulado|recortado|movido)\b|"
                              r"\b(reescribo|quito|elimino|añado|acorto|amplío|sustituyo|rehago|corrijo|reformulo|recorto)\b", re.I)


# Frases sobre el formato o la imagen («he cambiado el color», «he destacado…»): no son cambios de texto (2/11: un
# destacado pedido por el chat hacía pedir el guion entero y el editor reescribía diapositivas que nadie había pedido)
_DE_FORMATO = re.compile(r"destacad|color|rojo|amarill|pluma|marcador|antet[ií]tulo|cursiva|imagen|foto|retrato|"
                         r"encuadre|composici[oó]n|portada en|ilustraci", re.I)


def _dice_que_cambio_el_texto(respuesta: str) -> bool:
    frases = re.split(r"(?<=[.!?;])\s+", respuesta or "")
    return any(_CAMBIO_DE_TEXTO.search(f) and not _DE_FORMATO.search(f) for f in frases)


def _imagen_sin_romper(llm: LLM, cfg: Config, p: Pieza, a: AccionImagen) -> tuple[Pieza | None, str]:
    """El cambio de imagen, sin que un fallo de Europeana, Commons o Magnific tumbe el turno del chat."""
    try:
        return aplicar_imagen(llm, cfg, p, a)
    except Exception as exc:
        return None, f"(No se pudo cambiar la imagen: {type(exc).__name__}: {str(exc)[:160]}.)"


_URL = re.compile(r"https?://[^\s<>\"'«»]+")


def leer_enlaces(cfg: Config, p: Pieza, mensaje: str, cliente=None) -> list[str]:
    """Descarga los enlaces que se pegan en el chat y los guarda como material de texto de la pieza, para que el
    editor los lea en este turno y en los siguientes (2/11: el editor no veía el artículo del FT que se le pegó).
    Ante 403 o 429 no se reintenta: se dice. Devuelve los avisos."""
    from folio import materiales, temas
    urls = list(dict.fromkeys(u.rstrip(".,);") for u in _URL.findall(mensaje or "")))[:3]
    if not urls:
        return []
    ya = {m.nombre for m in materiales.lista(cfg, p)}
    avisos = []
    with (cliente or temas._cliente()) as c:
        for url in urls:
            if url in ya:
                continue
            f, motivo = temas.descargar(url, c)
            if not f:
                avisos.append(f"Enlace sin leer ({url[:60]}…): {motivo}")
                continue
            try:
                materiales.guardar(cfg, p, url, f"{f.titulo}\n\n{f.texto}".encode(), "text/plain", credito=f.medio,
                                   nota=materiales.NOTA_ENLACE)
            except materiales.NoValido as exc:
                avisos.append(f"Enlace sin guardar: {exc}")
    return avisos


def _cambiar_libro(cfg: Config, llm: LLM, nueva: Pieza, a: AccionImagen) -> tuple[Pieza | None, str]:
    """Cambia el libro de la pieza por el que dice quien edita y la deja pendiente para reescribirla con «Proceder»
    (2/11, a petición del usuario: «te has confundido enteramente de libro; el bueno es Killer App, de Darren
    Loucaides; rehazlo de 0»). El libro se verifica como siempre (catálogos, edición en castellano; la novedad no se
    exige: lo elige la redacción); los enlaces que se pegaron en el chat pasan a las fuentes de la pieza para que el
    guionista y la comprobación de hechos los vean. Sin verificar, no se cambia."""
    from folio import materiales
    from folio.etapas import EtapasGuardadas
    from folio.modelos import FuenteNoticia, LibroCandidato
    from folio.pipeline import Pipeline
    if not (a.libro.strip() and a.autor.strip()):
        return None, "(Para cambiar el libro necesito su título y su autor.)"
    prueba = nueva.model_copy(deep=True)
    prueba.eleccion.libros_candidatos = [LibroCandidato(titulo=a.libro.strip(), autor=a.autor.strip())]
    prueba.libros, prueba.libros_descartados, prueba.error = [], [], None
    tuberia = Pipeline(cfg, nueva.fecha, llm=llm)
    tuberia.sin_novedad = True
    # Por excepción, un título sin traducir si quien edita lo pide expresamente (2/11, regla del usuario)
    tuberia.permitir_sin_castellano = a.sin_castellano.strip().lower() in ("si", "sí", "true")
    if not tuberia._verificar(prueba, set()):
        motivos = "; ".join(f"{d.titulo}: {d.motivo}" for d in prueba.libros_descartados) or prueba.error or "no aparece en los catálogos"
        pista = (" Si lo quieres igualmente, dímelo expresamente («aunque no tenga edición en castellano») y lo pongo por excepción."
                 if "castellano" in motivos and not tuberia.permitir_sin_castellano else "")
        return None, f"(No puedo poner «{a.libro.strip()}»: {motivos}. Sin verificar no entra en una pieza.{pista})"
    tuberia._cubiertas_de(prueba)
    # Los enlaces leídos en el chat, a las fuentes congeladas de la historia (los usarán el guionista y los hechos)
    etapas = EtapasGuardadas(cfg.dir_cache(nueva.fecha))
    textos = etapas.textos(nueva.historia_id) or []
    vistos = {f.url for f, _ in textos}
    for m in materiales.lista(cfg, nueva):
        if m.tipo == "texto" and m.nota == materiales.NOTA_ENLACE and m.nombre not in vistos:
            texto = materiales.ruta(cfg, nueva, m).read_text(encoding="utf-8")
            textos.append((FuenteNoticia(medio=m.credito or m.nombre, titulo=m.nombre, url=m.nombre, acceso="abierto",
                                         texto_completo=True), texto[:cfg.pipeline.guion.max_caracteres_texto]))
    if textos:
        etapas.guardar_textos(nueva.historia_id, textos)
    nueva.eleccion = prueba.eleccion
    nueva.libros, nueva.libros_descartados = prueba.libros, prueba.libros_descartados
    nueva.guion, nueva.arte, nueva.hechos, nueva.citas, nueva.error = None, None, [], [], None
    nueva.estado = "pendiente"
    l = nueva.libros[0]
    return nueva, (f"(Libro cambiado a «{l.titulo_propuesto}», de {', '.join(l.autores[:2])}, verificado. La pieza queda "
                   "pendiente: pulsa «Proceder» para escribirla de nuevo con ese libro.)")


def _friso(llm: LLM, cfg: Config, nueva: Pieza, ar, a: AccionImagen, dir_fecha) -> tuple[Pieza | None, str]:
    """Dibuja de nuevo el friso de las tres fichas de «Tres libros», con la escena que se pida o una nueva del
    ilustrador, o lo quita (2/11). Sin tope diario: lo pide quien edita, una vez cada vez (25 créditos)."""
    from folio import arte as direccion
    from folio.imagenes import editorial, friso
    if a.escena.strip().lower() in ("ninguno", "ninguna", "quitar", "sin"):
        if not ar.friso:
            return None, "(La pieza no lleva friso.)"
        ar.friso = ar.friso_idea = None
        return nueva, "(Quitado el friso de las fichas.)"
    if not direccion.lleva_friso(cfg, nueva, ar.tono):
        return None, "(El friso solo va en «Tres libros» con sus tres diapositivas de libro, y nunca en piezas graves.)"
    if a.escena.strip():
        escena, motivo = editorial.validar_escena(a.escena, editorial.nombres_de_pieza(nueva), max_palabras=friso.MAX_PALABRAS)
        idea = ""
    else:
        escena, idea, motivo = direccion.escena_friso(llm, cfg, nueva)
    if not escena:
        return None, f"(La escena del friso no vale: {motivo}.)"
    img, descartes = friso.generar_limpio(llm, cfg, nueva.id, dir_fecha, escena)
    if not img:
        return None, f"(El friso salió con {'; '.join(descartes)}: no lo pongo. Pide otro.)"
    ar.friso, ar.friso_idea = escena, idea or ar.friso_idea
    return nueva, f"(Friso nuevo en las tres fichas{': ' + idea if idea else ''}.)"


def _cubierta(cfg: Config, nueva: Pieza, a: AccionImagen, dir_fecha) -> tuple[Pieza | None, str]:
    """La cubierta de otra edición en castellano de un libro de la pieza (2/11, a petición del usuario: «pon la portada
    de la edición de Random House/Mondadori, en lugar de la extranjera»). La edición la dan Open Library o Google Books
    (editorial, año, ISBN) y pasa también a la ficha y al colofón: nunca datos del modelo."""
    from folio.guion import ajustar_libros
    from folio.imagenes import cubiertas
    from folio.verificacion_texto import normalizar
    if not (a.editorial.strip() or a.isbn.strip()):
        return None, "(Para cambiar la cubierta necesito la editorial o el ISBN de la edición.)"
    buscado = normalizar(a.libro)
    candidatos = [l for l in nueva.libros if buscado and (buscado in normalizar(l.titulo_propuesto) or normalizar(l.titulo_propuesto) in buscado)]
    if not candidatos and len(nueva.libros) == 1:
        candidatos = nueva.libros
    if len(candidatos) != 1:
        return None, f"(No sé de qué libro de la pieza es la cubierta «{a.libro}».)"
    libro = candidatos[0]
    ruta, ed, nota = cubiertas.de_edicion(libro, dir_fecha.parent, editorial=a.editorial, isbn=a.isbn,
                                          clave_gb=cfg.google_books_api_key)
    if not ruta:
        return None, f"({nota})"
    previa = libro.edicion_es_detalle
    if previa and ed and not ed.titulo:
        ed.titulo = previa.titulo
    libro.edicion_es, libro.edicion_es_detalle = "si", ed
    if ed and ed.isbn and ed.isbn not in libro.isbn13:
        libro.isbn13 = [ed.isbn, *libro.isbn13]
    if nueva.guion:
        ajustar_libros(nueva.guion, nueva.libros)
    datos = ", ".join(x for x in (ed.editorial, ed.anio, f"ISBN {ed.isbn}" if ed.isbn else None) if x)
    return nueva, (f"(Cubierta y ficha de «{libro.titulo_propuesto}» cambiadas a la edición de {datos}. "
                   "Si el texto nombra la editorial de antes, cámbialo también.)")


def _formato(nueva: Pieza, ar, a: AccionImagen) -> tuple[Pieza | None, str]:
    """Destacado del titular, antetítulo y color de la pieza (2/11, a petición del usuario: «si pido edits de formato,
    no me deja»). Lo que no casa (un destacado que no está en el titular) no se aplica y se dice."""
    from folio import arte as direccion
    notas, cambios = [], 0
    titular = nueva.guion.diapositivas[0].texto if nueva.guion and nueva.guion.diapositivas else ""
    quitar = lambda v: v.strip().lower() in ("ninguno", "ninguna", "quitar", "sin")
    if a.destacado.strip():
        if quitar(a.destacado):
            ar.remate, cambios = None, cambios + 1
            notas.append("sin destacado en el titular")
        else:
            r = direccion.validar_remate(a.destacado, titular, en_cualquier_sitio=True)
            if r:
                ar.remate, cambios = r, cambios + 1
                notas.append(f"«{r}» destacado en el titular")
            else:
                notas.append(f"«{a.destacado.strip()}» no está tal cual en el titular (o es todo él): no lo destaco")
    if a.antetitulo.strip():
        nuevo = None if quitar(a.antetitulo) else direccion.validar_antetitulo(a.antetitulo)
        if nuevo or quitar(a.antetitulo):
            ar.antetitulo, cambios = nuevo, cambios + 1
            notas.append(f"antetítulo «{nuevo}»" if nuevo else "sin antetítulo")
        else:
            notas.append("el antetítulo tiene que tener de 1 a 3 palabras")
    if a.acento.strip():
        v = a.acento.strip().lower()
        if quitar(v):
            ar.acento, cambios = None, cambios + 1
            if ar.portada == "neon":
                ar.portada = "sangre"
            notas.append("sin color de pieza")
        elif v in ("pluma", "marcador"):
            if ar.tono == "grave":
                notas.append("una pieza grave va sin color")
            else:
                ar.acento, cambios = v, cambios + 1
                notas.append(f"color de la pieza: {'rojo (pluma)' if v == 'pluma' else 'amarillo (marcador)'}")
        else:
            notas.append("el color de la pieza es pluma (rojo) o marcador (amarillo)")
    texto = "(" + "; ".join(notas or ["no hay ningún cambio de formato que aplicar"]) + ".)"
    return (nueva if cambios else None), texto


def aplicar_imagen(llm: LLM, cfg: Config, p: Pieza, a: AccionImagen) -> tuple[Pieza | None, str]:
    """Aplica un cambio de imagen pedido en el chat. Devuelve (pieza nueva o None si no se pudo, nota)."""
    from folio import arte as direccion
    from folio.imagenes import editorial, libres
    from folio.modelos import Arte, Infografia, PropuestaArte, SinFoto
    dir_fecha = cfg.dir_cache(p.fecha)
    nueva = p.model_copy(deep=True)
    ar = nueva.arte or Arte(tono="sereno", recurso="foto")
    nueva.arte = ar
    retrato = libres.de_pieza(f"{p.id}-retrato", dir_fecha)
    archivo = libres.de_pieza(p.id, dir_fecha)
    if a.tipo == "formato":
        return _formato(nueva, ar, a)
    if a.tipo == "cubierta":
        return _cubierta(cfg, nueva, a, dir_fecha)
    if a.tipo == "friso":
        return _friso(llm, cfg, nueva, ar, a, dir_fecha)
    if a.tipo == "cambiar_libro":
        return _cambiar_libro(cfg, llm, nueva, a)
    if a.tipo == "encuadre":
        usa_retrato = retrato and ar.registro in ("foto_autor", "retrato_ia", None) and ar.portada != "panorama"
        img, clave = (retrato, f"{p.id}-retrato") if usa_retrato else (archivo, p.id)
        if not img:
            return None, "(No hay imagen que reencuadrar.)"
        img.enfoque = (max(0, min(100, a.enfoque_x)), max(0, min(100, a.enfoque_y)))
        libres.guardar_metadatos(img, clave, dir_fecha)
        return nueva, f"(Imagen reencuadrada: {img.enfoque[0]} % en horizontal, {img.enfoque[1]} % en vertical.)"
    if a.tipo == "composicion":
        if a.composicion not in cfg.pipeline.arte.portadas:
            return None, f"(La composición «{a.composicion}» no existe; hay {', '.join(cfg.pipeline.arte.portadas)}.)"
        if a.composicion == "neon" and not ar.acento:
            return None, "(La portada neón necesita el color de la pieza, y esta no lo lleva.)"
        ar.portada = a.composicion
        return nueva, f"(Portada en composición «{a.composicion}».)"
    if a.tipo == "usar_foto_autor":
        if not retrato:
            return None, "(Esta pieza no tiene foto del autor.)"
        ar.registro = "foto_autor"
        if ar.portada == "panorama":
            ar.portada = cfg.pipeline.arte.portadas[0]
        return nueva, "(La portada lleva ahora la foto del autor.)"
    if a.tipo == "usar_archivo":
        if not archivo or archivo.archivo == editorial.CLAVE:
            return None, "(No hay imagen de archivo para esta pieza; pide que busque una.)"
        ar.registro = "archivo"
        if ar.portada == "panorama":
            ar.portada = cfg.pipeline.arte.portadas[0]
        return nueva, "(La portada lleva ahora la imagen de archivo.)"
    if a.tipo == "buscar_archivo":
        consultas = [" ".join(c.split()) for c in a.consultas if 1 <= len(c.split()) <= 3][:4]
        if not consultas:
            return None, "(Hacen falta búsquedas de 1 a 3 palabras para buscar otra imagen.)"
        grave = ar.tono == "grave"
        propuesta = PropuestaArte(tono=ar.tono, portada=ar.portada if ar.portada in cfg.pipeline.arte.portadas else "sangre",
                                  suceso_con_victimas=grave, recurso="foto", consultas=consultas,
                                  evitar=["personas reconocibles"] if grave else [], por_que="pedida en el chat de edición",
                                  sin_foto=SinFoto(recurso="golpe"), infografia=Infografia(tipo="ninguna"))
        antes = (ar.imagen, list(ar.avisos))
        usadas = {archivo.archivo} if archivo else set()
        # Copia de la imagen actual: la búsqueda la borra antes de elegir, y si no encuentra otra se devuelve
        copia = _copiar_imagenes(dir_fecha, p.id)
        try:
            direccion._imagen_de_archivo(llm, cfg, nueva, direccion._bloque_pieza(nueva, None), propuesta, ar, usadas, dir_fecha)
        except Exception:
            _restaurar_imagenes(dir_fecha, copia)
            raise
        if not ar.imagen or ar.imagen == antes[0]:
            _restaurar_imagenes(dir_fecha, copia)
            return None, "(No he encontrado otra imagen libre a la altura con esas búsquedas.)"
        ar.registro, ar.recurso = "archivo", "foto"
        if ar.portada == "panorama":
            ar.portada = cfg.pipeline.arte.portadas[0]
        return nueva, f"(Nueva imagen de archivo: {ar.credito}.)"
    if a.tipo == "buscar_retrato":
        return _buscar_retrato(cfg, p, nueva, ar, a, dir_fecha)
    if a.tipo == "retrato_ilustrado":
        return _retrato_ilustrado(cfg, nueva, ar, a, retrato, dir_fecha)
    if a.tipo == "usar_material":
        from folio import materiales
        return materiales.usar(cfg, p, nueva, ar, a.material, a.como)
    if a.tipo == "ilustrar":
        escena, motivo = editorial.validar_escena(a.escena, editorial.nombres_de_pieza(p))
        ie = cfg.pipeline.arte.ilustracion_editorial
        if not escena:
            return None, f"(No puedo dibujar esa escena: {motivo}.)"
        if not ie.activo:
            return None, "(La ilustración editorial está desactivada.)"
        if ar.tono == "grave":
            return None, "(En piezas graves no se ilustra.)"
        if direccion._del_dia(editorial.del_dia, cfg, p, dir_fecha) >= ie.max_por_dia:
            return None, f"(Ya hay {ie.max_por_dia} ilustraciones hoy, el máximo del día.)"
        try:
            img, descartes = editorial.generar_limpia(llm, cfg, p.id, dir_fecha, escena)
        except Exception as exc:
            return None, f"(No se pudo dibujar: {exc}.)"
        if not img:
            return None, f"(Las {len(descartes)} que dibujó Magnific salieron con letras o manchas: {'; '.join(descartes)}. Prueba otra escena.)"
        ar.imagen, ar.credito, ar.escena = img.archivo, img.credito, escena
        ar.recurso, ar.portada, ar.registro = "ilustracion", "panorama", "ilustracion"
        return nueva, "(Nueva ilustración editorial, en panorámica entre la portada y la noticia.)"
    return None, ""
