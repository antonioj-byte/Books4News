"""La voz de Folio y el pase de estilo (2/11, a petición del usuario: «escribe bastante mal»)."""

from folio import estilo, guion
from folio.modelos import Traza

from datos import ELECCION, FUENTES, LIBRO, guion_valido


def test_la_voz_sustituye_la_linea_de_tono(cfg):
    normal = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    con = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO], voz=True)
    assert guion.TONO in normal and guion.TONO not in con
    assert "Voz de Folio" in con and "Carsonmanía" in con and "[pegar" not in con


class LLMEstilo:
    def __init__(self, cfg, cambio):
        self.cfg, self.cambio, self.trazas = cfg, cambio, []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        assert "Voz de Folio" in mensajes[0]["content"] and "[pegar" not in mensajes[0]["content"]
        self.trazas.append(Traza(paso=paso, modelo="x", coste_usd=0.05))
        g = guion_valido()
        self.cambio(g)
        return g, []


def test_el_pase_de_estilo_se_queda_si_cumple_y_se_descarta_si_inventa(cfg):
    def mejor(g):
        g.diapositivas[1].texto = "Un tribunal juzga hoy a un funcionario que se limitaba a firmar las órdenes."
    nuevo, avisos = estilo.pulir(LLMEstilo(cfg, mejor), cfg, "p", guion_valido(), [LIBRO], FUENTES, [], "lateral")
    assert "firmar las órdenes" in nuevo.diapositivas[1].texto and avisos == ["Pase de estilo aplicado"]

    def inventa(g):
        g.diapositivas[1].texto = "Un tribunal juzga a 12 funcionarios que firmaban órdenes."
    viejo, avisos = estilo.pulir(LLMEstilo(cfg, inventa), cfg, "p", guion_valido(), [LIBRO], FUENTES, [], "lateral")
    assert viejo.diapositivas[1].texto == guion_valido().diapositivas[1].texto
    assert "cifras que no estaban: 12" in avisos[0]
