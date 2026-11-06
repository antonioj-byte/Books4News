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


def test_un_429_no_se_reintenta_y_es_un_error_llm(cfg, sin_esperas):
    l = m.LLM(cfg)
    with pytest.raises(m.LimiteLLM):
        l._con_paciencia("guion", lambda: (_ for _ in ()).throw(_error(429)))
    with pytest.raises(m.PeticionInvalida):
        l._con_paciencia("guion", lambda: (_ for _ in ()).throw(_error(400)))
    assert sin_esperas == []
    assert issubclass(m.LimiteLLM, m.ErrorLLM) and issubclass(m.PeticionInvalida, m.ErrorLLM)


def test_el_sdk_no_reintenta_por_su_cuenta(cfg):
    cfg.anthropic_api_key = cfg.anthropic_api_key or "x"
    assert m.LLM(cfg).cliente.max_retries == 0


def test_un_corte_de_red_se_reintenta(cfg, sin_esperas):
    l = m.LLM(cfg)
    fallos = [anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))]
    assert l._con_paciencia("x", lambda: (_ for _ in ()).throw(fallos.pop()) if fallos else "ok") == "ok"


def _sin_respuesta():
    return anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def test_sin_respuesta_un_reintento_y_sale_bien(cfg, sin_esperas):
    """6/11: «no me explico cómo puede tardar 20 minutos»: sin respuesta, un reintento y no cuatro."""
    l = m.LLM(cfg)
    fallos = [_sin_respuesta()]
    assert l._con_paciencia("jefe", lambda: (_ for _ in ()).throw(fallos.pop()) if fallos else "ok") == "ok"
    assert sin_esperas == []


def test_sin_respuesta_dos_veces_para(cfg, sin_esperas):
    l = m.LLM(cfg)
    llamadas = []
    def nunca():
        llamadas.append(1)
        raise _sin_respuesta()
    with pytest.raises(m.ErrorLLM, match="no respondió en 6 minutos, dos veces"):
        l._con_paciencia("jefe", nunca)
    assert len(llamadas) == 2


def test_el_cliente_no_espera_diez_minutos(cfg):
    cfg.anthropic_api_key = cfg.anthropic_api_key or "x"
    assert m.LLM(cfg).cliente.timeout == m.TIEMPO_MAXIMO_S
