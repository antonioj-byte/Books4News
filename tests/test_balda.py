"""La balda (2/11): libros reales de la misma balda para las propuestas de actualidad; el jefe vuelve a elegir."""

from folio import balda
from folio.modelos import HistoriaElegida, LibroCandidato, SeleccionJefe


def _e(formato="lateral", hid="h1"):
    return HistoriaElegida(formato=formato, historia_id=hid, titular="Un meme deja a LaLiga sin tele en China",
                           de_que_se_habla="D", cuestion_de_fondo="La censura china y el deporte", gancho_libro="viejo",
                           libros_candidatos=[LibroCandidato(titulo="Apple in China", autor="Patrick McGee")], por_que="P")


class LLM:
    def __init__(self, cfg):
        self.cfg, self.pasos = cfg, []

    def con_busqueda(self, paso, prompt, **k):
        self.pasos.append(paso)
        assert "La censura china y el deporte" in prompt and "[pegar" not in prompt
        return "texto con libros", set()

    def estructurado(self, paso, mensajes, esquema, **k):
        self.pasos.append(paso)
        if esquema is balda.Balda:
            return balda.Balda(libros=[balda.LibroBalda(titulo="El gran cortafuegos", autor="Ana Ruiz", editorial="Debate",
                                                        anio="2025", tesis="China exporta su censura con su mercado")]), ""
        assert "El gran cortafuegos (Ana Ruiz, Debate, 2025): China exporta" in mensajes[0]["content"]
        return balda.Eleccion(libros_candidatos=[LibroCandidato(titulo="El gran cortafuegos", autor="Ana Ruiz")],
                              gancho_libro="Ruiz explica cómo China exporta su censura con su mercado"), ""


def test_la_balda_cambia_los_libros_de_las_de_actualidad(cfg):
    llm = LLM(cfg)
    sel = SeleccionJefe(elegidas=[_e(), _e("edicion", "h2")])
    nueva, avisos = balda.mejorar(llm, cfg, sel, 2024)
    assert [l.titulo for l in nueva.elegidas[0].libros_candidatos] == ["El gran cortafuegos"]
    assert nueva.elegidas[0].gancho_libro.startswith("Ruiz explica")
    assert nueva.elegidas[1] == sel.elegidas[1]                    # el mundo del libro no pasa por la balda
    assert any("entran El gran cortafuegos" in a for a in avisos)


def test_si_falla_siguen_los_libros_del_jefe(cfg):
    class Roto:
        def __init__(self, cfg):
            self.cfg = cfg

        def con_busqueda(self, *a, **k):
            raise RuntimeError("sin red")
    sel = SeleccionJefe(elegidas=[_e()])
    nueva, avisos = balda.mejorar(Roto(cfg), cfg, sel, 2024)
    assert nueva.elegidas == sel.elegidas and "no se pudo" in avisos[0]
