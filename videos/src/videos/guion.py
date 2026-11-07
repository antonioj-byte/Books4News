"""Paso 3: el guion por planos del concepto elegido, sus reglas, la edición por chat o a mano y el bloqueo.

Las reglas se comprueban en código (`validar`); si el guionista las rompe, se le devuelven en la misma conversación
(el libro sale de la caché) como mucho dos veces. Una versión con avisos se guarda igual, para arreglarla por chat o
a mano, pero no se puede aprobar.
"""
from __future__ import annotations

import json
import re

from videos import almacen, fuente
from videos import libro as lib
from videos.conceptos import cache_caliente, mensajes_con_libro
from videos.config import Config
from videos.llm import LLM, ErrorLLM
from videos.modelos import (Cita, GuionLLM, MensajeChat, Plano, Proyecto, RespuestaChatLLM, SalidaLibroLLM, VersionGuion,
                            ahora)
from videos.prompts import cargar

ORDEN = ["gancho", "tension", "desarrollo", "giro", "cierre"]
MIN_PALABRAS, MAX_PALABRAS = 75, 150          # 30–60 s de voz a ~2,5 palabras por segundo
MIN_PLANOS, MAX_PLANOS = 8, 18
MAX_PALABRAS_PLANO = 12
MAX_PALABRAS_GANCHO = 7
MAX_PALABRAS_PANTALLA = 8
CITA_MIN, CITA_MAX = 4, 25
CORRECCIONES = 2
_RE_COMILLAS = re.compile(r"[«\"“]([^»\"”]{3,})[»\"”]")


def validar(planos: list[Plano], libro: lib.Libro, autor: str = "", titulo: str = "") -> list[str]:
    """Las reglas del guion. Devuelve los errores en frases que entiende el guionista (y quien edita)."""
    e: list[str] = []
    if not MIN_PLANOS <= len(planos) <= MAX_PLANOS:
        e.append(f"Tiene {len(planos)} planos; tienen que ser entre {MIN_PLANOS} y {MAX_PLANOS}.")
    if not planos:
        return e
    if planos[0].rol != "gancho":
        e.append("El primer plano tiene que ser el gancho.")
    if planos[-1].rol != "cierre":
        e.append("El último plano tiene que ser el cierre.")
    if sum(p.rol == "gancho" for p in planos) > 1:
        e.append("Solo el primer plano es gancho.")
    indices = [ORDEN.index(p.rol) for p in planos]
    if indices != sorted(indices):
        e.append("Los roles van en orden: gancho → tensión → desarrollo → giro → cierre.")
    for rol in ("tension", "desarrollo", "giro"):
        if rol not in {p.rol for p in planos}:
            e.append(f"Falta al menos un plano de {rol.replace('tension', 'tensión')}.")
    total = sum(lib.palabras(p.locucion) for p in planos)
    if not MIN_PALABRAS <= total <= MAX_PALABRAS:
        e.append(f"La locución suma {total} palabras; tiene que estar entre {MIN_PALABRAS} y {MAX_PALABRAS} (30–60 s).")
    g = lib.palabras(planos[0].locucion)
    if g > MAX_PALABRAS_GANCHO:
        e.append(f"El gancho (plano 1) tiene {g} palabras; como mucho {MAX_PALABRAS_GANCHO} (2 segundos).")
    for p in planos:
        n = lib.palabras(p.locucion)
        if n > MAX_PALABRAS_PLANO:
            e.append(f"{p.id}: la locución tiene {n} palabras; como mucho {MAX_PALABRAS_PLANO}. Pártelo en dos planos.")
        if n == 0:
            e.append(f"{p.id}: no tiene locución.")
        if lib.palabras(p.pantalla) > MAX_PALABRAS_PANTALLA:
            e.append(f"{p.id}: el texto en pantalla pasa de {MAX_PALABRAS_PANTALLA} palabras.")
        if not p.visual.strip():
            e.append(f"{p.id}: falta la descripción visual.")
        if not p.movimiento.strip():
            e.append(f"{p.id}: falta el movimiento de cámara o la animación.")
    citas = [p for p in planos if p.cita and p.cita.texto.strip()]
    if len(citas) > 1:
        e.append(f"Hay {len(citas)} citas; como mucho una.")
    for p in citas:
        n = lib.palabras(p.cita.texto)
        if not CITA_MIN <= n <= CITA_MAX:
            e.append(f"{p.id}: la cita tiene {n} palabras; de {CITA_MIN} a {CITA_MAX}.")
        if lib.buscar_literal(libro, p.cita.texto) is None:
            e.append(f"{p.id}: la cita «{p.cita.texto[:60]}…» no aparece letra por letra en el libro.")
    cita_norm = lib.normalizar(citas[0].cita.texto) if citas else ""
    for p in planos:
        for campo in (p.locucion, p.pantalla):
            for m in _RE_COMILLAS.finditer(campo):
                if not cita_norm or lib.normalizar(m.group(1)) not in cita_norm:
                    e.append(f"{p.id}: «{m.group(1)[:50]}» va entre comillas y no es la cita literal del libro.")
    if titulo or autor:
        pantallas = lib.normalizar(" ".join(p.pantalla for p in planos))
        apellido = lib.normalizar(autor.split()[-1]) if autor.strip() else ""
        if not ((titulo and lib.normalizar(titulo) in pantallas) or (apellido and apellido in pantallas)):
            e.append("El título del libro o el autor tienen que salir en el texto en pantalla de algún plano.")
    return e


def a_planos(g: GuionLLM, libro: lib.Libro) -> list[Plano]:
    planos = []
    for i, x in enumerate(g.planos, 1):
        cita = None
        if x.cita.strip():
            ref = lib.buscar_literal(libro, x.cita)
            cita = Cita(texto=x.cita.strip(), capitulo=ref.capitulo if ref else 0, pagina=ref.pagina if ref else None)
        planos.append(Plano(id=f"p{i:02d}", rol=x.rol, locucion=x.locucion.strip(), pantalla=x.pantalla.strip(),
                            visual=x.visual.strip(), movimiento=x.movimiento.strip(),
                            duracion_estimada=round(float(x.duracion_estimada), 1), cita=cita))
    return planos


def _guion_de(r: tuple[SalidaLibroLLM, list]) -> tuple[GuionLLM, list]:
    s, contenido = r
    if s.guion is None:
        raise ErrorLLM("La guionista no devolvió el guion.")
    return s.guion, contenido


def _chat(llm: LLM, paso: str, mensajes: list[dict], con_libro: bool, cfg: Config) -> tuple[RespuestaChatLLM, list]:
    """Con el libro, el esquema común (para leer la caché del libro); sin él, el de chat."""
    if con_libro:
        s, contenido = llm.estructurado(paso, mensajes, SalidaLibroLLM, modelo=cfg.modelo_guion, esfuerzo="medium",
                                        max_tokens=16000)
        return RespuestaChatLLM(respuesta=s.respuesta or "", guion=s.guion), contenido
    return llm.estructurado(paso, mensajes, RespuestaChatLLM, modelo=cfg.modelo_guion, esfuerzo="medium", max_tokens=16000)


def _a_json(v: VersionGuion) -> str:
    return json.dumps({"titulo": v.titulo, "planos": [
        {"rol": p.rol, "locucion": p.locucion, "pantalla": p.pantalla, "visual": p.visual, "movimiento": p.movimiento,
         "duracion_estimada": p.duracion_estimada, "cita": p.cita.texto if p.cita else ""} for p in v.planos]},
        ensure_ascii=False, indent=1)


def _guardar_version(cfg: Config, pid: str, origen: str, titulo: str, planos: list[Plano], avisos: list[str],
                     prompt: str = "") -> VersionGuion:
    with almacen.editar(cfg, pid) as p:
        if p.etapas["guion"].estado == "bloqueado":
            raise ValueError("El guion está aprobado y bloqueado: desbloquéalo para cambiarlo")
        v = VersionGuion(n=len(p.guion) + 1, concepto=p.concepto_elegido, origen=origen, titulo=titulo, planos=planos,
                         avisos=avisos, prompt=prompt)
        p.guion.append(v)
        p.etapas["guion"].estado = "propuesta"
        p.etapas["guion"].actualizado = ahora()
        p.etapas["guion"].error = None
    return v


def _concepto(p: Proyecto):
    c = p.concepto(p.concepto_elegido or "")
    if c is None:
        raise ValueError("Elige antes un concepto")
    return c


def escribir(cfg: Config, llm: LLM, pid: str, anunciar=lambda _: None) -> VersionGuion:
    p = almacen.cargar(cfg, pid)
    c = _concepto(p)
    libro = almacen.libro(cfg, pid)
    ref = fuente.referencia(p.libro.tipo, c.pasaje.capitulo, c.pasaje.pagina, len(p.libro.capitulos) > 1) or "sin lugar"
    instrucciones, version = cargar(cfg, "guion", titulo=c.titulo, idea=c.idea, gancho=c.gancho, por_que=c.por_que,
                                    referencia=ref, pasaje=c.pasaje.texto,
                                    fuente=fuente.descripcion(p.libro.tipo, p.libro.titulo, p.libro.autor),
                                    min_palabras=str(MIN_PALABRAS), max_palabras=str(MAX_PALABRAS))
    mensajes = mensajes_con_libro(lib.texto_para_modelo(libro), instrucciones)
    anunciar("La guionista escribe los planos")
    g, contenido = _guion_de(llm.estructurado("guion", mensajes, SalidaLibroLLM, modelo=cfg.modelo_guion, esfuerzo="high",
                                              max_tokens=16000))
    with almacen.editar(cfg, pid) as q:
        q.libro_en_cache = ahora()
    planos = a_planos(g, libro)
    errores = validar(planos, libro, p.libro.autor, p.libro.titulo)
    for intento in range(CORRECCIONES):
        if not errores:
            break
        anunciar(f"Corrigiendo el guion ({len(errores)} reglas)")
        correccion, _ = cargar(cfg, "correccion_guion", errores="\n".join(f"- {x}" for x in errores))
        mensajes = mensajes + [{"role": "assistant", "content": contenido}, {"role": "user", "content": correccion}]
        g, contenido = _guion_de(llm.estructurado(f"guion-correccion-{intento + 1}", mensajes, SalidaLibroLLM,
                                                  modelo=cfg.modelo_guion, esfuerzo="medium", max_tokens=16000))
        planos = a_planos(g, libro)
        errores = validar(planos, libro, p.libro.autor, p.libro.titulo)
    return _guardar_version(cfg, pid, "guionista", g.titulo, planos, errores, version)


def chat(cfg: Config, llm: LLM, pid: str, mensaje: str, anunciar=lambda _: None) -> str:
    p = almacen.cargar(cfg, pid)
    c = _concepto(p)
    actual = p.guion_actual
    if actual is None:
        raise ValueError("Todavía no hay guion")
    if p.etapas["guion"].estado == "bloqueado":
        raise ValueError("El guion está aprobado y bloqueado: desbloquéalo para cambiarlo")
    libro = almacen.libro(cfg, pid)
    concepto = f"Título: {c.titulo}\nIdea: {c.idea}\nGancho: {c.gancho}\nPasaje (cap. {c.pasaje.capitulo}): «{c.pasaje.texto}»"
    instrucciones, version = cargar(cfg, "guion_chat", concepto=concepto, guion=_a_json(actual), mensaje=mensaje)
    # Con la caché del libro caliente, el chat lee el libro (por si pide algo de él); si no, va sin libro para no
    # volver a pagar la escritura de la caché por una edición
    con_libro = cache_caliente(p.libro_en_cache)
    mensajes = (mensajes_con_libro(lib.texto_para_modelo(libro), instrucciones) if con_libro
                else [{"role": "user", "content": instrucciones}])
    anunciar("La guionista revisa el guion")
    r, contenido = _chat(llm, "guion-chat", mensajes, con_libro, cfg)
    respuesta = r.respuesta
    if r.guion is not None:
        planos = a_planos(r.guion, libro)
        errores = validar(planos, libro, p.libro.autor, p.libro.titulo)
        nuevos = [x for x in errores if x not in actual.avisos]
        if nuevos:
            correccion, _ = cargar(cfg, "correccion_guion", errores="\n".join(f"- {x}" for x in nuevos))
            mensajes = mensajes + [{"role": "assistant", "content": contenido}, {"role": "user", "content": correccion}]
            r2, _ = _chat(llm, "guion-chat-correccion", mensajes, con_libro, cfg)
            if r2.guion is not None:
                planos = a_planos(r2.guion, libro)
                errores = validar(planos, libro, p.libro.autor, p.libro.titulo)
                respuesta = r2.respuesta or respuesta
        _guardar_version(cfg, pid, "chat", (r.guion.titulo or actual.titulo), planos, errores, version)
        if con_libro:
            with almacen.editar(cfg, pid) as q:
                q.libro_en_cache = ahora()
    with almacen.editar(cfg, pid) as q:
        q.chat.append(MensajeChat(rol="usuario", texto=mensaje, etapa="guion"))
        q.chat.append(MensajeChat(rol="asistente", texto=respuesta, etapa="guion"))
    return respuesta


CAMPOS_EDITABLES = ("locucion", "pantalla", "visual", "movimiento", "rol", "duracion_estimada", "cita")


def editar(cfg: Config, pid: str, cambios: dict[str, dict], quitar: list[str] | None = None,
           anadir_tras: str | None = None) -> VersionGuion:
    """Edición directa: `cambios` = {id de plano: {campo: valor}}; `quitar` borra planos; `anadir_tras` inserta uno
    vacío después de ese plano. Se guarda como versión «manual» aunque rompa reglas, con los avisos a la vista."""
    p = almacen.cargar(cfg, pid)
    actual = p.guion_actual
    if actual is None:
        raise ValueError("Todavía no hay guion")
    libro = almacen.libro(cfg, pid)
    planos = [x.model_copy(deep=True) for x in actual.planos]
    for x in planos:
        for campo, valor in (cambios.get(x.id) or {}).items():
            if campo not in CAMPOS_EDITABLES:
                raise ValueError(f"Campo no editable: {campo}")
            if campo == "cita":
                texto = str(valor or "").strip()
                ref = lib.buscar_literal(libro, texto) if texto else None
                x.cita = Cita(texto=texto, capitulo=ref.capitulo if ref else 0, pagina=ref.pagina if ref else None) if texto else None
            elif campo == "duracion_estimada":
                x.duracion_estimada = float(valor)
            else:
                setattr(x, campo, str(valor).strip())
    if quitar:
        planos = [x for x in planos if x.id not in set(quitar)]
    if anadir_tras:
        i = next((k for k, x in enumerate(planos) if x.id == anadir_tras), len(planos) - 1)
        base = planos[i]
        planos.insert(i + 1, Plano(id="nuevo", rol=base.rol, locucion="", visual="", movimiento="zoom lento hacia el centro",
                                   duracion_estimada=1.5))
    for k, x in enumerate(planos, 1):
        x.id = f"p{k:02d}"
    errores = validar(planos, libro, p.libro.autor, p.libro.titulo)
    return _guardar_version(cfg, pid, "manual", actual.titulo, planos, errores)


def aprobar(cfg: Config, pid: str) -> None:
    with almacen.editar(cfg, pid) as p:
        v = p.guion_actual
        if v is None:
            raise ValueError("Todavía no hay guion")
        libro = almacen.libro(cfg, pid)
        errores = validar(v.planos, libro, p.libro.autor, p.libro.titulo)
        if errores:
            raise ValueError("El guion aún no cumple: " + " ".join(errores[:3]))
        p.etapas["guion"].estado = "bloqueado"
        p.etapas["guion"].actualizado = ahora()


def desbloquear(cfg: Config, pid: str) -> None:
    with almacen.editar(cfg, pid) as p:
        if p.etapas["guion"].estado == "bloqueado":
            p.etapas["guion"].estado = "propuesta"
            p.etapas["guion"].actualizado = ahora()
            for k in ("estilo", "voz", "imagenes", "montaje"):
                if p.etapas[k].estado not in ("pendiente",):
                    p.etapas[k].estado = "desfasada"
