"""Caché de prompts, coste con caché, reintentos registrados y correcciones mecánicas."""

from folio import guion
from folio.llm import LLM, con_cache
from folio.modelos import Diapositiva

from datos import ELECCION, FUENTES, LIBRO, guion_valido


def test_con_cache_parte_el_prompt_en_fijo_y_datos(cfg):
    texto = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto de la noticia")], [LIBRO])
    bloques = con_cache(cfg, "guionista", texto)
    assert isinstance(bloques, list) and len(bloques) == 2
    assert bloques[0]["cache_control"] == {"type": "ephemeral"}
    assert "<noticia>" not in bloques[0]["text"] and "<noticia>" in bloques[1]["text"]
    assert bloques[0]["text"] + bloques[1]["text"] == texto


def test_con_cache_sin_parte_fija_devuelve_el_texto(cfg, tmp_path):
    (cfg.raiz / "prompts").unlink()
    (cfg.raiz / "prompts").mkdir()
    (cfg.raiz / "prompts" / "corto.md").write_text("Resume: [pegar]", encoding="utf-8")
    assert con_cache(cfg, "corto", "Resume: hola") == "Resume: hola"


def test_coste_con_cache(cfg):
    llm = LLM(cfg, cliente=object())
    # Opus 5.5: 4 $ entrada, 20 $ salida, 0,20 $ lectura de caché; escritura = 1,25 × entrada
    assert llm._coste("claude-opus-5-5", 1_000_000, 0) == 4.0
    assert llm._coste("claude-opus-5-5", 0, 0, escritura=1_000_000) == 5.0
    assert llm._coste("claude-opus-5-5", 0, 0, lectura=1_000_000) == 0.2
    # Haiku sin tercer precio: lectura al 10 % de la entrada
    assert llm._coste("claude-haiku-5-5", 0, 0, lectura=1_000_000) == 0.01


class LLMGuiones:
    def __init__(self, cfg, guiones):
        self.cfg, self.guiones, self.mensajes = cfg, list(guiones), []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.mensajes.append(mensajes)
        return self.guiones.pop(0), []


def test_reintento_registra_por_que_se_rechazo(cfg):
    malo = guion_valido()
    malo.diapositivas[0].texto = "¿Quién obedece?"
    llm = LLMGuiones(cfg, [malo, guion_valido()])
    g, avisos = guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    assert any(a.startswith("Rechazado en el intento 1:") and "pregunta" in a for a in avisos)
    assert "Guion aceptado en el intento 2" in avisos
    # La primera petición lleva la parte fija marcada para la caché
    assert llm.mensajes[0][0]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_correcciones_mecanicas_sin_volver_a_llamar(cfg):
    g = guion_valido()
    for x in g.diapositivas:
        x.n += 10
    g.diapositivas[-1].texto = "«Eichmann en Jerusalén», de Hannah Arendt. Léelo"
    llm = LLMGuiones(cfg, [g])
    _, avisos = guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    assert len(llm.mensajes) == 1  # una sola llamada
    assert [x.n for x in g.diapositivas] == [1, 2, 3, 4, 5]
    assert g.diapositivas[-1].texto.endswith("Léelo. Folio.")
    assert any("numeración" in a and "firma" in a for a in avisos)


def test_corregir_mecanico_no_toca_un_guion_correcto():
    g = guion_valido()
    antes = g.model_dump()
    assert guion.corregir_mecanico(g) == [] and g.model_dump() == antes
