"""Acceso a los modelos de Anthropic y carga de prompts.

Los prompts viven en prompts/*.md y se usan tal cual: el código solo sustituye los
marcadores de posición ([pegar lista], [pegar]…) por los datos del día, delimitados con
etiquetas para que el modelo los trate como datos y no como instrucciones.
"""

from __future__ import annotations

import hashlib
import json
import time
import logging
import re
from pathlib import Path
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


_MARCADOR = re.compile(r"\[(?:pegar[^\]]*|articulos)\]")
# El mínimo cacheable (512 tokens en los modelos 5.5) cuenta todo el prefijo, esquema de salida
# incluido; por debajo, la API no cachea y no cobra nada extra. Basta con que haya parte fija.
_MIN_CACHE_CARACTERES = 200


def con_cache(cfg: Config, nombre: str, texto: str) -> str | list[dict]:
    """Parte el prompt ya rellenado en dos bloques: el texto fijo de prompts/<nombre>.md hasta el
    primer marcador, marcado para la caché de prompts, y el resto (los datos del día).

    Así las llamadas seguidas con el mismo prompt (los tres guiones, los resúmenes) leen las
    instrucciones de la caché. Si la parte fija es demasiado corta, se devuelve el texto tal cual.
    """
    plantilla = (cfg.dir_prompts / f"{nombre}.md").read_text(encoding="utf-8")
    m = _MARCADOR.search(plantilla)
    fijo = plantilla[: m.start()] if m else plantilla
    if len(fijo) < _MIN_CACHE_CARACTERES or not texto.startswith(fijo) or len(texto) == len(fijo):
        return texto
    return [
        {"type": "text", "text": fijo, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": texto[len(fijo):]},
    ]


class LLM:
    def __init__(self, cfg: Config, cliente: anthropic.Anthropic | None = None, reutilizar: bool = False):
        """Con `reutilizar`, cada respuesta se guarda en data/cache/llm/ y una petición idéntica
        (modelo, esfuerzo, mensajes y esquema) se sirve de ahí sin llamar a la API: depurar el
        código que va después de un modelo no cuesta nada."""
        self.cfg = cfg
        self._cliente = cliente
        self.trazas: list[Traza] = []
        self.reutilizar = reutilizar

    def _ruta_cache(self, modelo: str, esfuerzo: str, max_tokens: int, mensajes: list, esquema: type) -> Path:
        clave = json.dumps({"modelo": modelo, "esfuerzo": esfuerzo, "max_tokens": max_tokens,
                            "esquema": esquema.model_json_schema(), "mensajes": mensajes},
                           sort_keys=True, ensure_ascii=False, default=str)
        return self.cfg.dir_datos / "cache" / "llm" / f"{hashlib.sha256(clave.encode()).hexdigest()}.json"

    @property
    def cliente(self) -> anthropic.Anthropic:
        if self._cliente is None:
            if not self.cfg.anthropic_api_key:
                raise ErrorLLM("Falta ANTHROPIC_API_KEY o FOLIO_ANTHROPIC_API_KEY (ponla en .env)")
            self._cliente = anthropic.Anthropic(api_key=self.cfg.anthropic_api_key, max_retries=4)
        return self._cliente

    def _coste(self, modelo: str, entrada: int, salida: int, escritura: int = 0, lectura: int = 0) -> float:
        """`entrada` es la entrada no cacheada; la escritura en caché cuesta 1,25 veces la entrada
        (caché de 5 minutos) y la lectura, el tercer precio de config (o el 10 % de la entrada)."""
        precios = self.cfg.pipeline.precios.get(modelo)
        if not precios:
            return 0.0
        lectura_precio = precios[2] if len(precios) > 2 else precios[0] * 0.1
        return round((entrada * precios[0] + escritura * precios[0] * 1.25
                      + lectura * lectura_precio + salida * precios[1]) / 1e6, 5)

    def con_busqueda(self, paso: str, prompt: str, *, etapa_modelo: str, max_busquedas: int = 6,
                     max_tokens: int = 8000) -> tuple[str, set[str]]:
        """Llamada con la herramienta de búsqueda web del servidor (2/11, la nevera del cajón). Devuelve el texto
        de la respuesta y las URLs que salieron en los resultados de búsqueda (para no aceptar URLs inventadas).
        Cada búsqueda cuesta aparte (`gasto.busqueda_web_usd`) y se apunta en la traza y el panel de gasto."""
        modelo = self.cfg.modelo(etapa_modelo)
        # La versión con filtrado dinámico solo la tienen Opus y Sonnet; Haiku usa la básica
        tipo = "web_search_20250305" if "haiku" in modelo else "web_search_20260209"
        mensajes = [{"role": "user", "content": prompt}]
        texto, urls, entrada, salida, busquedas = [], set(), 0, 0, 0
        inicio = time.monotonic()
        for _ in range(3):                       # pause_turn: se reenvía tal cual y el servidor sigue
            try:
                r = self.cliente.messages.create(model=modelo, max_tokens=max_tokens, messages=mensajes,
                                                 tools=[{"type": tipo, "name": "web_search", "max_uses": max_busquedas}],
                                                 output_config={"effort": self.cfg.esfuerzo(etapa_modelo)})
            except anthropic.APIConnectionError as exc:
                raise ErrorLLM(f"{paso}: no se pudo conectar con la API de Anthropic ({exc.__cause__})") from exc
            entrada += r.usage.input_tokens + (getattr(r.usage, "cache_read_input_tokens", 0) or 0)
            salida += r.usage.output_tokens
            uso = getattr(r.usage, "server_tool_use", None)
            busquedas += (getattr(uso, "web_search_requests", 0) or 0) if uso else 0
            for b in r.content:
                if b.type == "text":
                    texto.append(b.text)
                elif b.type == "web_search_tool_result" and isinstance(b.content, list):
                    urls |= {x.url for x in b.content if getattr(x, "url", None)}
            if r.stop_reason != "pause_turn":
                break
            mensajes = [mensajes[0], {"role": "assistant", "content": r.content}]
        if r.stop_reason == "refusal":
            raise ErrorLLM(f"{paso}: el modelo rechazó la petición")
        coste = round(self._coste(modelo, entrada, salida) + busquedas * self.cfg.pipeline.gasto.busqueda_web_usd, 5)
        self.trazas.append(Traza(paso=paso, modelo=modelo, tokens_entrada=entrada, tokens_salida=salida, coste_usd=coste,
                                 segundos=round(time.monotonic() - inicio, 1), nota=f"{busquedas} búsquedas web"))
        from folio import gastos
        gastos.apuntar(self.cfg, "anthropic", paso.split(":")[0], coste, "USD", unidades=entrada + salida, modelo=modelo,
                       detalle=f"{paso} · {busquedas} búsquedas")
        return "\n".join(texto).strip(), urls

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
        esfuerzo = self.cfg.esfuerzo(etapa_modelo)
        ruta_cache = self._ruta_cache(modelo, esfuerzo, max_tokens, mensajes, esquema) if self.reutilizar else None
        if ruta_cache and ruta_cache.exists():
            guardado = json.loads(ruta_cache.read_text(encoding="utf-8"))
            self.trazas.append(Traza(paso=paso, modelo=modelo, nota="respuesta reutilizada de la caché local (0 $)"))
            return esquema.model_validate(guardado["salida"]), guardado["contenido"]
        extra = {}
        if modelo in _CON_FALLBACK:
            extra = {"fallbacks": "default", "betas": [_BETA_FALLBACK]}
        inicio = time.monotonic()
        try:
            resp = self._llamar(modelo, max_tokens, mensajes, esquema, esfuerzo, extra)
        except anthropic.APIConnectionError as exc:
            # El SDK resume como «Connection error» fallos muy distintos: red, DNS o una clave con un
            # salto de línea (cabecera inválida). La causa real va en el mensaje.
            causa = exc.__cause__
            raise ErrorLLM(f"{paso}: no se pudo conectar con la API de Anthropic ({type(causa).__name__ if causa else 'sin causa'}: "
                           f"{causa})") from exc
        return self._procesar(paso, modelo, resp, esquema, ruta_cache, time.monotonic() - inicio)

    def _llamar(self, modelo, max_tokens, mensajes, esquema, esfuerzo, extra):
        return self.cliente.beta.messages.parse(
            model=modelo,
            max_tokens=max_tokens,
            messages=mensajes,
            output_format=esquema,
            output_config={"effort": esfuerzo},
            **extra,
        )

    def _procesar(self, paso, modelo, resp, esquema, ruta_cache, segundos: float = 0.0):
        modelo_real = getattr(resp, "model", None) or modelo
        traza = Traza(
            paso=paso,
            modelo=modelo_real,
            tokens_entrada=resp.usage.input_tokens,
            tokens_salida=resp.usage.output_tokens,
            tokens_cache_escritura=getattr(resp.usage, "cache_creation_input_tokens", None) or 0,
            tokens_cache_lectura=getattr(resp.usage, "cache_read_input_tokens", None) or 0,
            coste_usd=self._coste(modelo_real, resp.usage.input_tokens, resp.usage.output_tokens,
                                  getattr(resp.usage, "cache_creation_input_tokens", None) or 0,
                                  getattr(resp.usage, "cache_read_input_tokens", None) or 0),
            segundos=round(segundos, 1),
        )
        if modelo_real != modelo:
            traza.nota = f"respondió el modelo de respaldo ({modelo_real})"
        self.trazas.append(traza)
        from folio import gastos
        gastos.apuntar(self.cfg, "anthropic", paso.split(":")[0], traza.coste_usd, "USD",
                       unidades=traza.tokens_entrada + traza.tokens_salida + traza.tokens_cache_escritura + traza.tokens_cache_lectura,
                       modelo=modelo_real, detalle=paso)

        if resp.stop_reason == "refusal":
            raise ErrorLLM(f"{paso}: el modelo rechazó la petición ({getattr(resp, 'stop_details', None)})")
        if resp.stop_reason == "max_tokens":
            raise ErrorLLM(f"{paso}: respuesta cortada por max_tokens")
        if resp.parsed_output is None:
            raise ErrorLLM(f"{paso}: la respuesta no se pudo validar contra {esquema.__name__}")
        if ruta_cache:
            ruta_cache.parent.mkdir(parents=True, exist_ok=True)
            ruta_cache.write_text(json.dumps({
                "salida": resp.parsed_output.model_dump(mode="json"),
                "contenido": [bloque_reenviable(b) for b in resp.content],
            }, ensure_ascii=False), encoding="utf-8")
        return resp.parsed_output, resp.content


def bloque_reenviable(b) -> dict:
    """Bloque de contenido de una respuesta como dict reenviable (sin la salida ya validada)."""
    d = b if isinstance(b, dict) else b.model_dump(mode="json", exclude_none=True)
    return {k: v for k, v in d.items() if k != "parsed_output"}
