"""Evaluador de puentes (2/11, «contenido muy pillado con pinzas»): fuera las forzadas y primera una sólida."""

from folio import puentes
from folio.modelos import HistoriaElegida, LibroCandidato, SeleccionJefe


def _e(i, formato="lateral", libros=True):
    return HistoriaElegida(formato=formato, historia_id=f"h{i}", titular=f"T{i}", de_que_se_habla="D", cuestion_de_fondo="C",
                           libros_candidatos=[LibroCandidato(titulo=f"L{i}", autor="A")] if libros else [], por_que="P")


class LLM:
    def __init__(self, cfg, puntos):
        self.cfg, self.puntos, self.prompts = cfg, puntos, []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.prompts.append(mensajes[0]["content"])
        assert etapa_modelo == "puente" and "[pegar" not in mensajes[0]["content"]
        return puentes.Notas(notas=[puentes.Nota(numero=i, puntuacion=p, por_que=f"motivo {i}") for i, p in enumerate(self.puntos, 1)]), []


def test_fuera_las_forzadas_y_primera_una_solida(cfg):
    sel = SeleccionJefe(elegidas=[_e(1), _e(2), _e(3), _e(4, "curiosidad", libros=False)])
    llm = LLM(cfg, [3, 2, 5, 1])                    # la curiosidad sin libro no se juzga aunque le pongan un 1
    nueva, notas, avisos = puentes.evaluar(llm, sel)
    assert [e.historia_id for e in nueva.elegidas] == ["h3", "h1", "h4"]
    assert notas["h2"] == (2, "motivo 2") and "h4" not in notas
    assert any("fuera «T2»" in a for a in avisos) and any("pasa a ser la primera" in a for a in avisos)
    assert "T1" in llm.prompts[0] and "L3 (A)" in llm.prompts[0]


def test_si_el_evaluador_falla_la_mesa_sigue(cfg):
    from folio.llm import ErrorLLM

    class Roto:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, *a, **k):
            raise ErrorLLM("caído")
    sel = SeleccionJefe(elegidas=[_e(1), _e(2)])
    nueva, notas, avisos = puentes.evaluar(Roto(cfg), sel)
    assert nueva.elegidas == sel.elegidas and notas == {} and "no se pudo" in avisos[0]
