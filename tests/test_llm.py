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
        texto = json.dumps({"titular_es": "T", "resumen_es": "R", "seccion": "economia", "sobre_libros": False})
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


def test_reutilizar_sirve_peticiones_identicas_sin_llamar(cfg):
    capturas = []
    llm = LLM(cfg, cliente=_cliente(capturas), reutilizar=True)
    msg = [{"role": "user", "content": "hola"}]
    r1, _ = llm.estructurado("a", msg, ResumenHistoria, etapa_modelo="ingesta")
    r2, contenido = llm.estructurado("b", msg, ResumenHistoria, etapa_modelo="ingesta")
    assert len(capturas) == 1 and r1 == r2
    assert llm.trazas[1].coste_usd == 0 and "caché local" in llm.trazas[1].nota
    assert contenido and isinstance(contenido[0], dict)
    # Otra petición (otro mensaje) sí llama
    llm.estructurado("c", [{"role": "user", "content": "adiós"}], ResumenHistoria, etapa_modelo="ingesta")
    assert len(capturas) == 2


def test_perfil_dev_usa_el_modelo_barato_en_todo(cfg):
    from folio import config
    dev = config.perfil_dev(cfg)
    assert set(dev.pipeline["modelos"].values()) == {"claude-haiku-5-5"}
    assert set(dev.pipeline["esfuerzo"].values()) == {"low"}
    assert cfg.pipeline["modelos"]["guion"] == "claude-opus-5-5"  # la original no cambia


def test_clave_con_salto_de_linea_se_limpia(monkeypatch, tmp_path):
    from folio import config
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("FOLIO_ANTHROPIC_API_KEY", "  sk-ant-prueba\n")
    raiz = tmp_path / "r"
    (raiz / "config").mkdir(parents=True)
    for nombre in ("pipeline.yaml", "fuentes.yaml"):
        (raiz / "config" / nombre).write_text((config.RAIZ / "config" / nombre).read_text(encoding="utf-8"), encoding="utf-8")
    assert config.cargar(raiz).anthropic_api_key == "sk-ant-prueba"


def test_fallo_de_conexion_dice_la_causa(cfg):
    def manejar(req):
        raise httpx.ConnectError("Name or service not known", request=req)
    cliente = anthropic.Anthropic(api_key="x", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(manejar)))
    llm = LLM(cfg, cliente=cliente)
    with pytest.raises(ErrorLLM, match="no se pudo conectar.*ConnectError: Name or service not known"):
        llm.estructurado("resumen:h1", [{"role": "user", "content": "hola"}], ResumenHistoria, etapa_modelo="ingesta")


def test_cache_al_final_marca_solo_el_ultimo_bloque_de_una_copia():
    """Ronda 2 de mejora: las correcciones del guionista y los turnos del chat leen de la caché todo lo anterior."""
    from folio.llm import cache_al_final
    fijo = {"type": "text", "text": "instrucciones", "cache_control": {"type": "ephemeral"}}
    mensajes = [{"role": "user", "content": [fijo, {"type": "text", "text": "datos"}]}]
    marcados = cache_al_final(mensajes)
    assert marcados[0]["content"][1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in mensajes[0]["content"][1]             # el original no se toca
    mensajes += [{"role": "assistant", "content": [{"type": "text", "text": "{}"}]},
                 {"role": "user", "content": "Corrígelo"}]
    marcados = cache_al_final(mensajes)
    puntos = [b for m in marcados if isinstance(m["content"], list) for b in m["content"] if "cache_control" in b]
    assert len(puntos) == 2 and marcados[1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert marcados[-1] == mensajes[-1] and "cache_control" not in mensajes[1]["content"][-1]   # la corrección, igual


def test_el_guionista_marca_el_final_de_cada_turno(cfg):
    from datos import ELECCION, FUENTES, LIBRO, guion_valido
    from folio import guion as guionista
    from folio.llm import LLM

    class Falso(LLM):
        def __init__(self):
            super().__init__(cfg, cliente=object())
            self.vistos = []

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            self.vistos.append(mensajes)
            return guion_valido(), []

    llm = Falso()
    cfg.pipeline.guion.lector_sin_contexto = False
    guionista.escribir(llm, "p", ELECCION, [(FUENTES[0], "Texto de la noticia aquí.")], [LIBRO])
    unico = llm.vistos[0][-1]["content"]           # el primer turno: el único mensaje, con la noticia y los textos
    assert isinstance(unico, list) and unico[-1].get("cache_control") == {"type": "ephemeral"}


def test_con_hasta_cero_el_punto_se_queda_en_el_primer_mensaje():
    from folio.llm import cache_al_final
    m = [{"role": "user", "content": "datos"}, {"role": "assistant", "content": "{}"}, {"role": "user", "content": "Corrígelo"}]
    marcados = cache_al_final(m, hasta=0)
    assert marcados[0]["content"][-1]["cache_control"] == {"type": "ephemeral"} and marcados[1:] == m[1:]
