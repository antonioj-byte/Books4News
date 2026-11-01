"""El lector sin contexto: lo que no se entiende sin conocer la obra vuelve al guionista una vez. Sin red ni gasto."""

from folio import claridad, guion
from folio.modelos import GuionLLM

from datos import ELECCION, FUENTES, LIBRO, guion_valido


class LLMFalso:
    def __init__(self, cfg, guiones, lecturas):
        self.cfg, self.guiones, self.lecturas, self.pasos, self.ultimo = cfg, list(guiones), list(lecturas), [], None

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.pasos.append(paso)
        self.ultimo = mensajes[-1]["content"]
        if esquema is claridad.Lectura:
            return claridad.Lectura(problemas=self.lecturas.pop(0)), []
        return self.guiones.pop(0), [{"type": "text", "text": "x"}]


def _problema(frag):
    return [claridad.Problema(diapositiva=3, fragmento=frag, falta="quién fue")]


def test_lo_que_no_se_entiende_vuelve_al_guionista(cfg):
    cfg.pipeline.guion.lector_sin_contexto = True
    claro = guion_valido()
    llm = LLMFalso(cfg, [guion_valido(), claro], [_problema("escarmentado por Robert Moses"), []])
    g, avisos, _ = guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    assert g is claro and [p.split(":")[0] for p in llm.pasos] == ["guion", "claridad", "guion"]
    assert any("Lector sin contexto" in a and "Robert Moses" in a for a in avisos)
    assert "Robert Moses" in llm.ultimo and "presenta en pocas palabras" in llm.ultimo


def test_si_la_reescritura_rompe_una_regla_vale_la_anterior(cfg):
    cfg.pipeline.guion.lector_sin_contexto = True
    primero = guion_valido()
    roto = guion_valido(libros=[])                                   # sin libros: incumple una regla
    llm = LLMFalso(cfg, [primero, roto], [_problema("Penn Station")])
    g, avisos, _ = guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    assert g is primero and any("se queda la versión anterior" in a for a in avisos)


def test_sin_problemas_no_hay_turno_de_mas(cfg):
    cfg.pipeline.guion.lector_sin_contexto = True
    llm = LLMFalso(cfg, [guion_valido()], [[]])
    guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO])
    assert [p.split(":")[0] for p in llm.pasos] == ["guion", "claridad"]
