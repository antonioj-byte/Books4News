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


def test_plantilla_de_evaluacion_y_copia_si_esta_rellenada(cfg, tmp_path):
    from datetime import datetime, timezone

    from folio import informe
    from folio.modelos import InformeDiario, Pieza

    from datos import ELECCION, guion_valido
    pieza = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                  eleccion=ELECCION, n_medios=3, guion=guion_valido())
    inf = InformeDiario(fecha="2026-10-30", generado_en=datetime.now(timezone.utc), stats={},
                        top_historias=[], piezas=[pieza])
    _, md = informe.escribir(inf, tmp_path)
    texto = md.read_text()
    assert "<!-- evaluacion:2026-10-30-1 -->" in texto and "- Voz (1–5): " in texto
    assert not informe.evaluacion_rellenada(texto)

    md.write_text(texto.replace("- Voz (1–5): ", "- Voz (1–5): 4"))
    informe.escribir(inf, tmp_path)
    copias = list(tmp_path.glob("informe.evaluado-*.md"))
    assert len(copias) == 1 and "- Voz (1–5): 4" in copias[0].read_text()
