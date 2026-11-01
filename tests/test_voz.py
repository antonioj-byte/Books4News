"""La voz de Folio y el pase de estilo (2/11, a petición del usuario: «escribe bastante mal»)."""

from folio import estilo, guion
from folio.modelos import Traza

from datos import ELECCION, FUENTES, LIBRO, guion_valido


def test_la_voz_de_folio_va_en_produccion_y_se_cachea(cfg):
    """Ronda 1 de la voz (2/11): guionista.md incluye voz_folio.md; la caché de prompts la cubre como parte fija."""
    from folio.llm import con_cache
    normal = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    assert "Voz de Folio" in normal and "Carsonmanía" in normal and "[incluir" not in normal and "[pegar" not in normal
    assert guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO], voz=True) == normal
    bloques = con_cache(cfg, "guionista", normal)
    assert isinstance(bloques, list) and "Carsonmanía" in bloques[0]["text"]


def test_otra_version_de_la_voz_sustituye_a_la_de_produccion(cfg, tmp_path):
    (cfg.dir_prompts / "voz_folio.md")   # existe
    ruta = tmp_path / "voz_x.md"
    ruta.write_text("VOZ DE PRUEBA")
    con = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO], voz=str(ruta.with_suffix("")))
    assert "VOZ DE PRUEBA" in con and "Carsonmanía" not in con


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
