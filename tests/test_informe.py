from folio.informe import _edicion_es_guion
from folio.modelos import LibroGuion

from datos import LIBRO


def _lg(editorial):
    return LibroGuion(titulo="Eichmann en Jerusalén", autor="Hannah Arendt", editorial_espanola=editorial,
                      traductor=None, edicion_original="inglés, Viking, 1963")


def test_ficha_del_guion_refleja_la_edicion_verificada():
    assert _edicion_es_guion(_lg("Debolsillo"), [LIBRO]) == "sí, Debolsillo"
    # Edición española verificada pero sin editorial en la fuente: no es «no consta»
    assert _edicion_es_guion(_lg(None), [LIBRO]) == "sí (editorial no consta)"
    assert _edicion_es_guion(_lg(None), [LIBRO.model_copy(update={"edicion_es": "no", "edicion_es_detalle": None})]) == "no"
    assert _edicion_es_guion(_lg(None), [LIBRO.model_copy(update={"edicion_es": "desconocido",
                                                                  "edicion_es_detalle": None})]) == "no consta"
