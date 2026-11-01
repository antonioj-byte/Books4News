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
    tipo: Literal["encuadre", "composicion", "usar_foto_autor", "usar_archivo", "buscar_archivo", "ilustrar"] = Field(
        description="encuadre: mover el punto de interés de la imagen de portada; composicion: sangre, banda, caja o neon; "
                    "usar_foto_autor / usar_archivo: qué imagen va en la portada; buscar_archivo: otra imagen de archivo con "
                    "nuevas búsquedas; ilustrar: una ilustración editorial nueva con una escena")
    enfoque_x: int = Field(description="Solo encuadre: 0–100, dónde está lo importante en horizontal (50 = centro)")
    enfoque_y: int = Field(description="Solo encuadre: 0–100, en vertical (0 = arriba; para ver una cara entera, 20–35)")
    composicion: str = Field(description="Solo composicion: sangre, banda, caja o neon; si no, vacío")
    consultas: list[str] = Field(description="Solo buscar_archivo: 3 o 4 búsquedas de 1 a 3 palabras, en inglés; si no, vacía")
    escena: str = Field(description="Solo ilustrar: la metáfora visual en inglés, de 12 a 70 palabras, sin nombres propios, cifras ni comillas; si no, vacío")


class RespuestaChat(BaseModel):
    respuesta: str = Field(description="Lo que contestas a quien edita: breve, en español")
    guion: GuionLLM | None = Field(default=None, description="El guion completo revisado, solo si hay que cambiar algo; null si no")
    imagen: AccionImagen | None = Field(default=None, description="Un cambio en la imagen, solo si lo piden; null si no")


def _citas_ok(p: Pieza) -> frozenset[str]:
    return frozenset(normalizar(c.texto) for c in p.citas)


def validar(cfg: Config, p: Pieza, g: GuionLLM) -> list[str]:
    return guionista.validar(cfg, g, p.libros, p.fuentes, _citas_ok(p))


def editar_diapositiva(cfg: Config, p: Pieza, n: int, texto: str, subtitulo: str | None = None) -> tuple[Pieza, list[str]]:
    """La pieza con la diapositiva n cambiada a mano y los avisos (reglas que no cumple)."""
    nueva = p.model_copy(deep=True)
    d = nueva.guion.diapositivas[n - 1]
    d.texto = " ".join(texto.split())
    if d.tipo == "portada":
        d.subtitulo = " ".join((subtitulo or "").split()) or None
    guionista.corregir_mecanico(nueva.guion)
    return nueva, validar(cfg, nueva, nueva.guion)


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
    mensajes = [{"role": "user", "content": sistema}, {"role": "assistant", "content": "Entendido. ¿Qué cambiamos?"},
                *mensajes, {"role": "user", "content": mensaje}]
    avisos: list[str] = []
    previos = set(validar(cfg, p, p.guion))
    for intento in range(cfg.pipeline.guion.reintentos + 1):
        r, contenido = llm.estructurado(f"chat:{p.id}:{intento + 1}", mensajes, RespuestaChat, etapa_modelo="chat")
        if r.guion is None:
            if r.imagen is None:
                return r.respuesta, None, avisos
            nueva, nota = aplicar_imagen(llm, cfg, p, r.imagen)
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
                con_imagen, nota = aplicar_imagen(llm, cfg, nueva, r.imagen)
                return f"{r.respuesta} {nota}".strip(), con_imagen or nueva, avisos
            return r.respuesta, nueva, avisos
        avisos.append(f"Intento {intento + 1} rechazado: " + " | ".join(errores))
        mensajes += [{"role": "assistant", "content": json.dumps(r.model_dump(mode="json"), ensure_ascii=False)},
                     {"role": "user", "content": "El guion no cumple estas condiciones:\n" + "\n".join(f"- {e}" for e in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    return ("No he podido hacer ese cambio sin romper las reglas de Folio: " + "; ".join(errores)), None, avisos


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
        direccion._imagen_de_archivo(llm, cfg, nueva, direccion._bloque_pieza(nueva, None), propuesta, ar, usadas, dir_fecha)
        if not ar.imagen or ar.imagen == antes[0]:
            return None, "(No he encontrado otra imagen libre a la altura con esas búsquedas.)"
        ar.registro, ar.recurso = "archivo", "foto"
        if ar.portada == "panorama":
            ar.portada = cfg.pipeline.arte.portadas[0]
        return nueva, f"(Nueva imagen de archivo: {ar.credito}.)"
    if a.tipo == "ilustrar":
        escena, motivo = editorial.validar_escena(a.escena)
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
            img = editorial.generar(cfg, p.id, dir_fecha, escena)
        except Exception as exc:
            return None, f"(No se pudo dibujar: {exc}.)"
        ar.imagen, ar.credito, ar.escena = img.archivo, img.credito, escena
        ar.recurso, ar.portada, ar.registro = "ilustracion", "panorama", "ilustracion"
        return nueva, "(Nueva ilustración editorial, en panorámica entre la portada y la noticia.)"
    return None, ""
