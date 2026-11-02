"""Pautas al 66 % (cita textual, idea rompehielos) y portada de reportaje en «Tres libros» (2/11, a petición del
usuario). Sin red ni gasto."""

from folio import guion
from folio.modelos import Diapositiva

from datos import ELECCION, FUENTES, LIBRO, guion_valido


def test_el_sorteo_es_estable_y_ronda_el_66(cfg):
    assert guion.pautas_de_pieza(cfg, "2026-11-02-3") == guion.pautas_de_pieza(cfg, "2026-11-02-3")
    ids = [f"2026-11-{d:02d}-{n}" for d in range(1, 31) for n in range(1, 11)]
    for nombre in ("cita", "rompehielos"):
        parte = sum(guion.pautas_de_pieza(cfg, i)[nombre] for i in ids) / len(ids)
        assert 0.58 < parte < 0.74, (nombre, parte)
    combinaciones = {tuple(guion.pautas_de_pieza(cfg, i).values()) for i in ids}
    assert len(combinaciones) == 4                    # las dos, una, la otra y ninguna: no es una serie


def test_las_pautas_van_en_los_datos_de_la_pieza(cfg):
    p = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO], pautas={"cita": True, "rompehielos": False})
    datos = p[p.index("<noticia>"):]
    assert "lleva una cita textual destacada" in datos and "nunca inventes una cita" in datos
    assert "más reposada" in datos
    sin = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto")], [LIBRO], pautas={"cita": False, "rompehielos": True})
    assert "va sin cita destacada" in sin and "rompehielos" in sin


def _libro(titulo, autor):
    return LIBRO.model_copy(update={"titulo": titulo, "titulo_propuesto": titulo, "autores": [autor]})


def test_tres_libros_el_subtitulo_anticipa_el_metodo(cfg):
    libros = [LIBRO, _libro("La condición humana", "Mary Beard"), _libro("Sapiens", "Yuval Noah Harari")]

    def errores(subtitulo):
        g = guion_valido()
        g.diapositivas[0] = Diapositiva(n=1, tipo="portada", texto="El año en que dejamos de fiarnos de lo que vemos",
                                        subtitulo=subtitulo)
        return " ".join(guion.validar(cfg, g, libros, FUENTES, frozenset(), frozenset(), "balda"))

    assert "anticipa el método" in errores("Arendt lo explicó hace décadas, y otros dos libros lo confirman hoy")
    assert "anticipa el método" not in errores("Tres ensayos recientes lo cuentan desde la cámara, el algoritmo y el juzgado")
