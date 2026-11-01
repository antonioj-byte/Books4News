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

from typing import Literal

from pydantic import BaseModel, Field

from folio import guion as guionista
from folio.config import Config
from folio.llm import LLM, cargar_prompt
from folio.modelos import GuionLLM, Pieza
from folio.verificacion_texto import normalizar

AVISO_CHAT = "Editada con el chat: comprueba los datos nuevos (no se han vuelto a cotejar con las fuentes)"


class AccionImagen(BaseModel):
    """Un cambio en la imagen de la pieza, que aplica el código."""
    tipo: Literal["encuadre", "composicion", "usar_foto_autor", "usar_archivo", "buscar_archivo", "ilustrar",
                  "buscar_retrato", "retrato_ilustrado", "usar_material"] = Field(
        description="encuadre: mover el punto de interés de la imagen de portada; composicion: sangre, banda, caja o neon; "
                    "usar_foto_autor / usar_archivo: qué imagen va en la portada; buscar_archivo: otra imagen de archivo con "
                    "nuevas búsquedas; ilustrar: una ilustración editorial nueva con una escena (sin personas reales); "
                    "buscar_retrato: buscar la foto libre de una persona real (autor o protagonista) para la portada; "
                    "retrato_ilustrado: pasar esa foto a ilustración en un estilo de la casa; "
                    "usar_material: poner en la pieza una foto que ha subido quien edita")
    enfoque_x: int = Field(description="Solo encuadre: 0–100, dónde está lo importante en horizontal (50 = centro)")
    enfoque_y: int = Field(description="Solo encuadre: 0–100, en vertical (0 = arriba; para ver una cara entera, 20–35)")
    composicion: str = Field(description="Solo composicion: sangre, banda, caja o neon; si no, vacío")
    consultas: list[str] = Field(description="Solo buscar_archivo: 3 o 4 búsquedas de 1 a 3 palabras, en inglés; si no, vacía")
    escena: str = Field(description="Solo ilustrar: la metáfora visual en inglés, de 12 a 70 palabras, sin nombres propios, cifras ni comillas; si no, vacío")
    persona: str = Field(description="Solo buscar_retrato: nombre completo de la persona real (el autor del libro o quien protagoniza la historia); si no, vacío")
    estilo: str = Field(description="Solo retrato_ilustrado: low_poly, voxel, render_2000 o dithering (vacío: el que va con el tono); si no, vacío")
    material: str = Field(description="Solo usar_material: el id del material (la foto subida); si no, vacío")
    como: str = Field(description="Solo usar_material: «portada» (la imagen de la portada) o «retrato» (la foto del autor o protagonista); si no, vacío")


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
    if p.libros and direccion.autor_principal(p) and persona.lower() != direccion.autor_principal(p).lower():
        return None, f"(El retrato de la portada es el del autor del libro, {direccion.autor_principal(p)}; no se pone la cara de otra persona.)"
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
    extra = materiales.bloques(cfg, p)          # lo que ha subido quien edita (2/11), como datos delimitados
    ultimo = [*extra, {"type": "text", "text": mensaje}] if extra else mensaje
    mensajes = [{"role": "user", "content": sistema}, {"role": "assistant", "content": "Entendido. ¿Qué cambiamos?"},
                *mensajes, {"role": "user", "content": ultimo}]
    avisos: list[str] = []
    previos = set(validar(cfg, p, p.guion))
    for intento in range(cfg.pipeline.guion.reintentos + 1):
        r, contenido = llm.estructurado(f"chat:{p.id}:{intento + 1}", mensajes, RespuestaChat, etapa_modelo="chat")
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


def _imagen_sin_romper(llm: LLM, cfg: Config, p: Pieza, a: AccionImagen) -> tuple[Pieza | None, str]:
    """El cambio de imagen, sin que un fallo de Europeana, Commons o Magnific tumbe el turno del chat."""
    try:
        return aplicar_imagen(llm, cfg, p, a)
    except Exception as exc:
        return None, f"(No se pudo cambiar la imagen: {type(exc).__name__}: {str(exc)[:160]}.)"


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
