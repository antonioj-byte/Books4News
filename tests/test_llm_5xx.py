"""Errores pasajeros de Anthropic (2/11: «Proceder» falló con un 500): espera y reintenta; si sigue, un ErrorLLM claro.
Sin red ni gasto."""

import anthropic
import httpx
import pytest

from folio import llm as m


def _error(codigo):
    r = httpx.Response(codigo, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    cuerpo = {"type": "error", "error": {"type": "api_error", "message": "Unable to complete this request right now."}}
    return anthropic.APIStatusError("x", response=r, body=cuerpo)


@pytest.fixture
def sin_esperas(monkeypatch):
    esperas = []
    monkeypatch.setattr(m.time, "sleep", esperas.append)
    return esperas


def test_un_500_se_reintenta_y_sale_bien(cfg, sin_esperas):
    l = m.LLM(cfg)
    fallos = [_error(500)]
    assert l._con_paciencia("guion", lambda: (_ for _ in ()).throw(fallos.pop()) if fallos else "ok") == "ok"
    assert sin_esperas == [m.ESPERAS_5XX[0]]


def test_si_sigue_fallando_dice_que_es_pasajero(cfg, sin_esperas):
    l = m.LLM(cfg)
    with pytest.raises(m.ErrorLLM, match="fallo pasajero de Anthropic.*vuelve a intentarlo"):
        l._con_paciencia("guion", lambda: (_ for _ in ()).throw(_error(529)))
    assert sin_esperas == list(m.ESPERAS_5XX)


def test_un_429_no_se_reintenta(cfg, sin_esperas):
    l = m.LLM(cfg)
    with pytest.raises(anthropic.APIStatusError):
        l._con_paciencia("guion", lambda: (_ for _ in ()).throw(_error(429)))
    assert sin_esperas == []
