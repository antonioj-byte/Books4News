from folio import hechos
from folio.modelos import HechoComprobado

from datos import FUENTES

TEXTOS = [(FUENTES[0], "Patrick Stewart died at his home in Los Angeles on Wednesday, aged 86, his family said.")]


def _h(evidencia, medio="The Guardian"):
    return HechoComprobado(afirmacion="murió a los 86 años", donde="diapositiva 2", tipo="cifra",
                           verificado=True, medio=medio, evidencia=evidencia)


def test_evidencia_literal_en_la_fuente():
    assert hechos._evidencia_en_fuente(_h("died at his home in Los Angeles on Wednesday, aged 86"), TEXTOS)
    # Mayúsculas y puntuación no importan
    assert hechos._evidencia_en_fuente(_h("Wednesday aged 86 his family said"), TEXTOS)


def test_evidencia_inventada_o_demasiado_corta():
    assert not hechos._evidencia_en_fuente(_h("died peacefully surrounded by music, aged 86"), TEXTOS)
    assert not hechos._evidencia_en_fuente(_h("aged 86"), TEXTOS)


def test_comprobar_rebaja_lo_que_no_se_sostiene(cfg):
    class LLMFalso:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            assert etapa_modelo == "comprobacion"
            assert "<guion>" in mensajes[0]["content"] and "<fuente" in mensajes[0]["content"]
            return esquema(hechos=[_h("died at his home in Los Angeles"), _h("died in a hospital in London")]), []

    from datos import guion_valido
    res = hechos.comprobar(LLMFalso(cfg), "p1", guion_valido(), TEXTOS)
    assert [h.verificado for h in res] == [True, False]
    assert "no aparece literalmente" in res[1].nota
