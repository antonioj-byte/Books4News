"""Acceso a los modelos de Anthropic y carga de prompts.

Los prompts viven en prompts/*.md y se usan tal cual: el código solo sustituye los
marcadores de posición ([pegar lista], [pegar]…) por los datos del día, delimitados con
etiquetas para que el modelo los trate como datos y no como instrucciones.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from folio.config import Config
from folio.modelos import Traza

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Modelos con fallback server-side ante rechazos del clasificador de seguridad.
_CON_FALLBACK = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
_BETA_FALLBACK = "server-side-fallback-2026-07-01"


class ErrorLLM(RuntimeError):
    pass


def cargar_prompt(cfg: Config, nombre: str, reemplazos: dict[str, str]) -> str:
    """Carga prompts/<nombre>.md y sustituye cada marcador exacto. Falla si falta alguno."""
    texto = (cfg.dir_prompts / f"{nombre}.md").read_text(encoding="utf-8")
    for marcador, valor in reemplazos.items():
        if marcador not in texto:
            raise ErrorLLM(f"El prompt {nombre}.md no contiene el marcador {marcador!r}")
        texto = texto.replace(marcador, valor)
    return texto


class LLM:
    def __init__(self, cfg: Config, cliente: anthropic.Anthropic | None = None):
        self.cfg = cfg
        self._cliente = cliente
        self.trazas: list[Traza] = []

    @property
    def cliente(self) -> anthropic.Anthropic:
        if self._cliente is None:
            if not self.cfg.anthropic_api_key:
                raise ErrorLLM("Falta ANTHROPIC_API_KEY (ponla en .env)")
            self._cliente = anthropic.Anthropic(api_key=self.cfg.anthropic_api_key, max_retries=4)
        return self._cliente

    def _coste(self, modelo: str, entrada: int, salida: int) -> float:
        precios = self.cfg.pipeline.get("precios", {}).get(modelo)
        if not precios:
            return 0.0
        return round(entrada / 1e6 * precios[0] + salida / 1e6 * precios[1], 5)

    def estructurado(
        self,
        paso: str,
        mensajes: list[dict],
        esquema: type[T],
        *,
        etapa_modelo: str,
        max_tokens: int = 16000,
    ) -> tuple[T, list]:
        """Llamada con salida estructurada validada por Pydantic.

        `etapa_modelo` es la clave en config (ingesta, seleccion, guion) de la que salen
        modelo y esfuerzo. Devuelve el objeto validado y el contenido bruto de la respuesta
        (para poder continuar la conversación en un reintento).
        """
        modelo = self.cfg.modelo(etapa_modelo)
        extra = {}
        if modelo in _CON_FALLBACK:
            extra = {"fallbacks": "default", "betas": [_BETA_FALLBACK]}
        resp = self.cliente.beta.messages.parse(
            model=modelo,
            max_tokens=max_tokens,
            messages=mensajes,
            output_format=esquema,
            output_config={"effort": self.cfg.esfuerzo(etapa_modelo)},
            **extra,
        )
        modelo_real = getattr(resp, "model", None) or modelo
        traza = Traza(
            paso=paso,
            modelo=modelo_real,
            tokens_entrada=resp.usage.input_tokens,
            tokens_salida=resp.usage.output_tokens,
            coste_usd=self._coste(modelo_real, resp.usage.input_tokens, resp.usage.output_tokens),
        )
        if modelo_real != modelo:
            traza.nota = f"respondió el modelo de respaldo ({modelo_real})"
        self.trazas.append(traza)

        if resp.stop_reason == "refusal":
            raise ErrorLLM(f"{paso}: el modelo rechazó la petición ({getattr(resp, 'stop_details', None)})")
        if resp.stop_reason == "max_tokens":
            raise ErrorLLM(f"{paso}: respuesta cortada por max_tokens")
        if resp.parsed_output is None:
            raise ErrorLLM(f"{paso}: la respuesta no se pudo validar contra {esquema.__name__}")
        return resp.parsed_output, resp.content
