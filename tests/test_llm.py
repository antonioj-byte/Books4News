"""La petición que sale hacia la API de Anthropic (sin red: transporte simulado)."""

import json

import anthropic
import httpx2 as httpx
import pytest

from folio.llm import LLM, ErrorLLM, cargar_prompt
from folio.modelos import ResumenHistoria


def _cliente(capturas, stop_reason="end_turn"):
    def manejar(req: httpx.Request):
        capturas.append(req)
        cuerpo = json.loads(req.content)
        texto = json.dumps({"titular_es": "T", "resumen_es": "R", "seccion": "economia"})
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": cuerpo["model"],
            "content": [{"type": "text", "text": texto}], "stop_reason": stop_reason,
            "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 200},
        })
    return anthropic.Anthropic(api_key="x", http_client=httpx.Client(transport=httpx.MockTransport(manejar)))


def test_peticion_opus_con_fallback_esfuerzo_y_esquema(cfg):
    capturas = []
    llm = LLM(cfg, cliente=_cliente(capturas))
    r, _ = llm.estructurado("prueba", [{"role": "user", "content": "hola"}], ResumenHistoria, etapa_modelo="seleccion")
    assert r.seccion == "economia"
    req = capturas[0]
    cuerpo = json.loads(req.content)
    assert cuerpo["model"] == "claude-opus-5-5"
    assert cuerpo["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    assert cuerpo["output_config"]["effort"] == "high"
    assert cuerpo["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in cuerpo and "thinking" not in cuerpo
    assert llm.trazas[0].coste_usd == pytest.approx(1000 / 1e6 * 4 + 200 / 1e6 * 20)


def test_haiku_sin_fallback(cfg):
    capturas = []
    LLM(cfg, cliente=_cliente(capturas)).estructurado(
        "p", [{"role": "user", "content": "x"}], ResumenHistoria, etapa_modelo="ingesta")
    cuerpo = json.loads(capturas[0].content)
    assert cuerpo["model"] == "claude-haiku-5-5" and "fallbacks" not in cuerpo
    assert cuerpo["output_config"]["effort"] == "low"


def test_rechazo_lanza_error(cfg):
    llm = LLM(cfg, cliente=_cliente([], stop_reason="refusal"))
    with pytest.raises(ErrorLLM, match="rechazó"):
        llm.estructurado("p", [{"role": "user", "content": "x"}], ResumenHistoria, etapa_modelo="seleccion")


def test_prompts_reales_tienen_sus_marcadores(cfg):
    assert "<h>" in cargar_prompt(cfg, "jefe_cultura", {"[pegar lista]": "<h>"})
    p = cargar_prompt(cfg, "guionista", {"[pegar]": "<n>", "[pegar o «propón tú»]": "<l>"})
    assert "<n>" in p and "<l>" in p
    with pytest.raises(ErrorLLM):
        cargar_prompt(cfg, "guionista", {"[no existe]": ""})
