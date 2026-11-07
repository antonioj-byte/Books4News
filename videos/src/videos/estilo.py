"""Paso 4: la biblia de estilo. Tres predefinidos (`videos/estilos.json`) o uno propio que escribe Claude a partir de
lo que pide quien edita. Cada prompt de imagen es «prefijo: escena. sufijo. composición. prohibido», así que todos los
planos comparten técnica, paleta y luz.

El prefijo con la técnica va delante y el resto como sufijo: en Folio se vio que, con el estilo solo al final, una
escena larga y literal manda sobre el estilo (3/11).
"""
from __future__ import annotations

import json

from videos import almacen
from videos.config import RAIZ, Config
from videos.llm import LLM
from videos.modelos import Estilo, EstiloLLM, ahora
from videos.prompts import cargar

COMPOSICION = ("Vertical 9:16 composition, the main subject inside the central area of the frame, "
               "calm empty areas at the top and bottom")
PROHIBIDO_EN = "No text, no letters, no numbers, no logos, no signs, no captions, no watermark, no frame or border"


def predefinidos() -> dict[str, dict]:
    return json.loads((RAIZ / "estilos.json").read_text(encoding="utf-8"))


def prompt_imagen(estilo: Estilo, escena: str) -> str:
    return f"{estilo.prefijo}: {escena.strip().rstrip('.')}. {estilo.sufijo.strip().rstrip('.')}. {COMPOSICION}. {PROHIBIDO_EN}."


def _guardar(cfg: Config, pid: str, e: Estilo) -> Estilo:
    with almacen.editar(cfg, pid) as p:
        if p.etapas["guion"].estado != "bloqueado":
            raise ValueError("Aprueba antes el guion")
        cambia = p.estilo is not None and p.estilo.model_dump() != e.model_dump()
        p.estilo = e
        p.etapas["estilo"].estado = "hecha"
        p.etapas["estilo"].actualizado = ahora()
        if cambia:      # otro estilo deja desfasadas las imágenes ya hechas (se conservan para volver)
            for ip in p.imagenes.values():
                ip.prompt = prompt_imagen(e, ip.escena)
            if p.etapas["imagenes"].estado != "pendiente":
                p.etapas["imagenes"].estado = "desfasada"
    return e


def elegir(cfg: Config, pid: str, preset: str) -> Estilo:
    datos = predefinidos().get(preset)
    if datos is None:
        raise ValueError("Ese estilo no existe")
    return _guardar(cfg, pid, Estilo(id=preset, **datos))


def propio(cfg: Config, llm: LLM, pid: str, peticion: str, anunciar=lambda _: None) -> Estilo:
    p = almacen.cargar(cfg, pid)
    c = p.concepto(p.concepto_elegido or "")
    concepto = f"{c.titulo}: {c.idea}" if c else p.libro.titulo
    prompt, _ = cargar(cfg, "estilo", concepto=concepto, peticion=peticion)
    anunciar("La directora de arte escribe la biblia de estilo")
    r, _ = llm.estructurado("estilo", [{"role": "user", "content": prompt}], EstiloLLM, modelo=cfg.modelo_guion,
                            esfuerzo="medium", max_tokens=6000)
    prohibido = list(dict.fromkeys(r.prohibido + ["texto, letras y números", "logotipos", "caras reconocibles de personas reales"]))
    e = Estilo(id="propio", nombre=r.nombre, tecnica=r.tecnica, paleta=r.paleta[:5], luz=r.luz, encuadres=r.encuadres,
               prohibido=prohibido, prefijo=r.prefijo, sufijo=r.sufijo, musica=r.musica, descripcion=r.tecnica,
               peticion=peticion)
    return _guardar(cfg, pid, e)
