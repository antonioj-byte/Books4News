"""Cliente de Claude para la beta: salida estructurada validada con Pydantic, caché de prompts de una hora para el
libro (lo comparten conceptos, otra ronda y guion), reintentos ante fallos pasajeros y nada de reintentos ante un 429.
Cada respuesta se guarda en una caché local por huella de la petición: repetir lo mismo no se paga dos veces.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

import anthropic
import pydantic

from videos.config import PRECIOS, Config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=pydantic.BaseModel)
ESPERAS = (2, 8, 20)
TIEMPO_MAXIMO_S = 600


class ErrorLLM(RuntimeError):
    pass


class LimiteLLM(ErrorLLM):
    """429: no se reintenta."""


@dataclass
class Uso:
    paso: str
    modelo: str
    entrada: int = 0
    salida: int = 0
    cache_escritura: int = 0
    cache_lectura: int = 0
    usd: float = 0.0
    segundos: float = 0.0
    de_cache_local: bool = False


def coste(modelo: str, entrada: int, salida: int, escritura: int, lectura: int) -> float:
    pe, ps, pl = PRECIOS.get(modelo, (4.0, 20.0, 0.2))
    return round((entrada * pe + salida * ps + escritura * pe * 2 + lectura * pl) / 1_000_000, 4)


def bloque_libro(texto: str) -> dict:
    """El libro como primer bloque del primer mensaje, con caché de una hora: los turnos que empiezan igual lo leen
    de la caché a una vigésima parte del precio."""
    return {"type": "text", "text": texto, "cache_control": {"type": "ephemeral", "ttl": "1h"}}


@dataclass
class LLM:
    cfg: Config
    al_gastar: Callable[[Uso], None] | None = None
    usos: list[Uso] = field(default_factory=list)
    _cliente: anthropic.Anthropic | None = None

    @property
    def cliente(self) -> anthropic.Anthropic:
        if self._cliente is None:
            if not self.cfg.anthropic_api_key:
                raise ErrorLLM("Falta ANTHROPIC_API_KEY en el entorno (o en videos/.env).")
            self._cliente = anthropic.Anthropic(api_key=self.cfg.anthropic_api_key, max_retries=0, timeout=TIEMPO_MAXIMO_S)
        return self._cliente

    def estructurado(self, paso: str, mensajes: list[dict], esquema: type[T], *, modelo: str,
                     esfuerzo: str = "high", max_tokens: int = 16000) -> tuple[T, list]:
        """Devuelve el objeto validado y el contenido bruto de la respuesta (para seguir la conversación)."""
        huella = hashlib.sha256(json.dumps([modelo, esfuerzo, max_tokens, esquema.__name__,
                                            esquema.model_json_schema(), mensajes],
                                           ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        ruta = self.cfg.cache / "llm" / f"{huella}.json"
        if ruta.exists():
            g = json.loads(ruta.read_text(encoding="utf-8"))
            self._apuntar(Uso(paso, modelo, de_cache_local=True))
            return esquema.model_validate(g["salida"]), g["contenido"]
        inicio = time.monotonic()
        resp = self._con_paciencia(paso, lambda: self.cliente.beta.messages.parse(
            model=modelo, max_tokens=max_tokens, messages=mensajes, output_format=esquema,
            output_config={"effort": esfuerzo}))
        u = resp.usage
        uso = Uso(paso, getattr(resp, "model", modelo) or modelo, u.input_tokens, u.output_tokens,
                  u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0, segundos=round(time.monotonic() - inicio, 1))
        uso.usd = coste(modelo, uso.entrada, uso.salida, uso.cache_escritura, uso.cache_lectura)
        self._apuntar(uso)
        if resp.stop_reason == "max_tokens":
            raise ErrorLLM(f"{paso}: la respuesta se cortó por longitud (max_tokens={max_tokens}).")
        salida = resp.parsed_output
        if salida is None:
            raise ErrorLLM(f"{paso}: la respuesta no validó contra {esquema.__name__}.")
        contenido = [{k: v for k, v in b.model_dump(mode="json", exclude_none=True).items() if k != "parsed_output"}
                     for b in resp.content]
        contenido = [b for b in contenido if b.get("type") in ("text", "thinking", "redacted_thinking")]
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"salida": salida.model_dump(mode="json"), "contenido": contenido}, ensure_ascii=False),
                        encoding="utf-8")
        return salida, contenido

    def _apuntar(self, uso: Uso) -> None:
        self.usos.append(uso)
        if self.al_gastar:
            self.al_gastar(uso)

    def _con_paciencia(self, paso: str, llamada):
        for espera in (*ESPERAS, None):
            try:
                return llamada()
            except anthropic.APIStatusError as exc:
                if exc.status_code == 429:
                    raise LimiteLLM(f"{paso}: Anthropic ha puesto un límite (429). No se reintenta.") from exc
                if exc.status_code < 500 and exc.status_code not in (408, 409):
                    raise ErrorLLM(f"{paso}: Anthropic rechazó la petición ({exc.status_code}: {exc.message[:300]})") from exc
                if espera is None:
                    raise ErrorLLM(f"{paso}: Anthropic no respondió ({exc.status_code}) tras varios intentos.") from exc
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
                if espera is None:
                    raise ErrorLLM(f"{paso}: sin conexión con Anthropic ({type(exc).__name__}).") from exc
            except pydantic.ValidationError as exc:
                raise ErrorLLM(f"{paso}: la respuesta llegó incompleta o no validó.") from exc
            log.warning("%s: fallo pasajero de Anthropic; reintento en %s s", paso, espera)
            time.sleep(espera)
