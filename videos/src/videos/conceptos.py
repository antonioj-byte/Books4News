"""Paso 2: del libro a cinco conceptos conversacionales.

1. Opus lee el libro entero (con caché de una hora) y propone doce candidatos con su pasaje.
2. El código comprueba que cada pasaje está letra por letra en el libro; si faltan buenos, se le pide una vez que los
   corrija en la misma conversación (el libro sale de la caché).
3. Un crítico independiente, que no escribió los candidatos, elige los cinco mejores con sus propias notas.
4. Un juez aparte puntúa cada gancho y lo reescribe si saca menos de 8 o pasa de 7 palabras (dos veces como mucho).
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from videos import almacen, fuente
from videos import libro as lib
from videos.config import Config
from videos.llm import LLM, ErrorLLM, bloque_libro
from videos.modelos import (Concepto, ConceptoLLM, CriticaLLM, JuezGanchoLLM, JuicioGancho, MensajeChat,
                            Notas, Pasaje, RespuestaChatConceptosLLM, SalidaLibroLLM, ahora)
from videos.prompts import cargar

log = logging.getLogger(__name__)
CANDIDATOS = 12
ELEGIDOS = 5
NOTA_GANCHO = 8
MAX_PALABRAS_GANCHO = 7
REESCRITURAS_GANCHO = 2


def mensajes_con_libro(texto_libro: str, instrucciones: str) -> list[dict]:
    """El libro primero (bloque cacheado, idéntico en todas las llamadas del proyecto) y después las instrucciones."""
    return [{"role": "user", "content": [bloque_libro(texto_libro), {"type": "text", "text": instrucciones}]}]


def cache_caliente(libro_en_cache: str | None) -> bool:
    if not libro_en_cache:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(libro_en_cache) < timedelta(minutes=55)


def _conceptos_de(s: SalidaLibroLLM) -> list[ConceptoLLM]:
    if not s.conceptos:
        raise ErrorLLM("La editora de ideas no devolvió ningún concepto.")
    return s.conceptos


def _verificar(libro: lib.Libro, c: ConceptoLLM) -> tuple[lib.Referencia | None, str]:
    n = lib.palabras(c.pasaje)
    if "…" in c.pasaje or "..." in c.pasaje:
        return None, "lleva puntos suspensivos (tiene que ser un fragmento seguido)"
    if not 12 <= n <= 70:
        return None, f"tiene {n} palabras (de 15 a 60)"
    ref = lib.buscar_literal(libro, c.pasaje)
    return (ref, "") if ref else (None, "no aparece letra por letra en el libro")


def _ronda(p, indicaciones: str) -> str:
    partes = []
    if p.conceptos:
        ya = "\n".join(f"- {c.titulo}: {c.idea}" for c in p.conceptos)
        partes.append(f"## Ya propuestos\n\nEn rondas anteriores se propusieron estos conceptos. No los repitas ni propongas variantes de ellos:\n\n{ya}")
    if indicaciones.strip():
        partes.append(f"## Lo que pide quien edita para esta ronda\n\n<indicaciones>\n{indicaciones.strip()}\n</indicaciones>")
    return "\n\n".join(partes)


def juzgar_gancho(cfg: Config, llm: LLM, gancho: str, idea: str) -> tuple[str, JuicioGancho]:
    """Puntúa el gancho y lo reescribe mientras saque menos de 8 o pase de 7 palabras. Devuelve el mejor."""
    original, actual, historial = gancho, gancho, []
    mejor: tuple[int, str, str] | None = None
    for intento in range(REESCRITURAS_GANCHO + 1):
        prompt, _ = cargar(cfg, "juez_gancho", gancho=actual, idea=idea)
        j, _ = llm.estructurado("juez-gancho", [{"role": "user", "content": prompt}], JuezGanchoLLM,
                                modelo=cfg.modelo_gancho, esfuerzo="medium", max_tokens=4000)
        largo = lib.palabras(actual)
        historial.append({"gancho": actual, "nota": j.nota, "palabras": largo, "motivo": j.motivo})
        valida = largo <= MAX_PALABRAS_GANCHO
        if valida and (mejor is None or j.nota > mejor[0]):
            mejor = (j.nota, actual, j.motivo)
        if valida and j.nota >= NOTA_GANCHO:
            break
        siguiente = j.reescritura.strip().strip("«»\"")
        if not siguiente or siguiente == actual:
            break
        actual = siguiente
    if mejor is None:       # ninguno cabe en 7 palabras: se queda el último con su nota
        mejor = (historial[-1]["nota"], actual, historial[-1]["motivo"])
    nota, texto, motivo = mejor
    return texto, JuicioGancho(original=original, nota=nota, motivo=motivo, intentos=len(historial), historial=historial)


def proponer(cfg: Config, llm: LLM, pid: str, indicaciones: str = "", anunciar=lambda _: None) -> list[Concepto]:
    p = almacen.cargar(cfg, pid)
    libro = almacen.libro(cfg, pid)
    ronda = max((c.ronda for c in p.conceptos), default=0) + 1
    desc = fuente.descripcion(p.libro.tipo, p.libro.titulo, p.libro.autor)
    instrucciones, version = cargar(cfg, "conceptos", cuantos=str(fuente.candidatos(p.libro.caracteres)),
                                    ronda=_ronda(p, indicaciones), fuente=desc)
    mensajes = mensajes_con_libro(lib.texto_para_modelo(libro), instrucciones)

    anunciar("La editora de ideas lee la fuente")
    cands, contenido = llm.estructurado("conceptos", mensajes, SalidaLibroLLM, modelo=cfg.modelo_conceptos,
                                        esfuerzo="high", max_tokens=20000)
    cands = _conceptos_de(cands)
    with almacen.editar(cfg, pid) as q:
        q.libro_en_cache = ahora()
    verificados = [(c, *_verificar(libro, c)) for c in cands]
    fallidos = [(i, c, motivo) for i, (c, ref, motivo) in enumerate(verificados) if ref is None]
    if fallidos and len(verificados) - len(fallidos) < min(ELEGIDOS + 2, len(verificados)):
        anunciar("Corrigiendo los pasajes que no son literales")
        errores = "\n".join(f"- Candidato {i} («{c.titulo}»): el pasaje {m}." for i, c, m in fallidos)
        correccion, _ = cargar(cfg, "correccion_pasajes", errores=errores, cuantos=str(len(cands)))
        mensajes2 = mensajes + [{"role": "assistant", "content": contenido}, {"role": "user", "content": correccion}]
        cands, _ = llm.estructurado("conceptos-pasajes", mensajes2, SalidaLibroLLM, modelo=cfg.modelo_conceptos,
                                    esfuerzo="medium", max_tokens=20000)
        cands = _conceptos_de(cands)
        verificados = [(c, *_verificar(libro, c)) for c in cands]
    validos = [(c, ref) for c, ref, _ in verificados if ref is not None]
    descartados = [f"«{c.titulo}»: el pasaje {m}" for c, ref, m in verificados if ref is None]
    if not validos:
        raise ErrorLLM("Ningún concepto trae un pasaje literal del libro. " + "; ".join(descartados[:3]))

    anunciar("El crítico elige los mejores")
    lista = [{"indice": i, "titulo": c.titulo, "idea": c.idea, "gancho": c.gancho, "por_que": c.por_que,
              "pasaje": c.pasaje, "notas": c.notas.model_dump()} for i, (c, _) in enumerate(validos)]
    critica_prompt, _ = cargar(cfg, "critico_conceptos", cuantos=str(min(ELEGIDOS, len(validos))), fuente=desc,
                               candidatos=json.dumps(lista, ensure_ascii=False, indent=1))
    critica, _ = llm.estructurado("critico", [{"role": "user", "content": critica_prompt}], CriticaLLM,
                                  modelo=cfg.modelo_critico, esfuerzo="high", max_tokens=12000)
    elegidos, vistos = [], set()
    for v in critica.valoraciones:
        if v.veredicto == "elegido" and 0 <= v.indice < len(validos) and v.indice not in vistos:
            vistos.add(v.indice)
            elegidos.append(v)
    elegidos = elegidos[:ELEGIDOS]
    if not elegidos:
        raise ErrorLLM("El crítico no ha dado por bueno ningún concepto: pide otra ronda con otras indicaciones.")

    anunciar("El juez revisa los ganchos")
    with ThreadPoolExecutor(max_workers=3) as ex:
        juicios = list(ex.map(lambda v: juzgar_gancho(cfg, llm, validos[v.indice][0].gancho, validos[v.indice][0].idea), elegidos))

    nuevos = []
    for k, (v, (gancho, juicio)) in enumerate(zip(elegidos, juicios), 1):
        c, ref = validos[v.indice]
        nuevos.append(Concepto(
            id=f"r{ronda}c{k}", ronda=ronda, titulo=c.titulo, idea=c.idea, gancho=gancho, por_que=c.por_que,
            pasaje=Pasaje(texto=c.pasaje, capitulo=ref.capitulo, titulo_capitulo=ref.titulo, pagina=ref.pagina, verificado=True),
            notas=Notas(**_acotar(c.notas.model_dump())), notas_critico=Notas(**_acotar(v.notas.model_dump())),
            motivo_critico=v.motivo, juicio_gancho=juicio, prompt=version))
    with almacen.editar(cfg, pid) as q:
        q.conceptos.extend(nuevos)
        q.etapas["conceptos"].estado = "propuesta"
        q.etapas["conceptos"].actualizado = ahora()
        q.etapas["conceptos"].error = None
        if descartados:
            log.info("%s: descartados por el pasaje: %s", pid, descartados)
    return nuevos


def _acotar(n: dict) -> dict:
    return {k: max(1, min(10, int(v))) for k, v in n.items()}


def chat(cfg: Config, llm: LLM, pid: str, mensaje: str, anunciar=lambda _: None) -> str:
    """Una pregunta o una petición sobre los conceptos. Si pide otros, lanza otra ronda con esas indicaciones."""
    p = almacen.cargar(cfg, pid)
    resumen = "\n".join(f"- [{c.id}] {c.titulo} — {c.idea} (gancho: «{c.gancho}»)" for c in p.conceptos)
    prompt, _ = cargar(cfg, "conceptos_chat", fuente=fuente.descripcion(p.libro.tipo, p.libro.titulo, p.libro.autor),
                       conceptos=resumen or "(todavía ninguno)", mensaje=mensaje)
    r, _ = llm.estructurado("conceptos-chat", [{"role": "user", "content": prompt}], RespuestaChatConceptosLLM,
                            modelo=cfg.modelo_critico, esfuerzo="medium", max_tokens=4000)
    with almacen.editar(cfg, pid) as q:
        q.chat.append(MensajeChat(rol="usuario", texto=mensaje, etapa="conceptos"))
        q.chat.append(MensajeChat(rol="asistente", texto=r.respuesta, etapa="conceptos"))
    if r.otra_ronda:
        proponer(cfg, llm, pid, r.indicaciones or mensaje, anunciar)
    return r.respuesta


def elegir(cfg: Config, pid: str, cid: str) -> None:
    with almacen.editar(cfg, pid) as p:
        if p.concepto(cid) is None:
            raise ValueError("Ese concepto no existe")
        if p.etapas["guion"].estado == "bloqueado" and p.concepto_elegido != cid:
            raise ValueError("El guion ya está aprobado: desbloquéalo antes de cambiar de concepto")
        p.concepto_elegido = cid
        p.etapas["conceptos"].estado = "aprobada"
        p.etapas["conceptos"].actualizado = ahora()
        if p.guion_actual is None:
            p.etapas["guion"].estado = "pendiente"
