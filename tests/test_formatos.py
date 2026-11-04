"""El registro de formatos (4/11): un formato nuevo empieza por su ficha, y lo que falte salta aquí."""
import importlib
from typing import get_args

from folio import formatos
from folio.modelos import Formato
from folio.render.plantillas import Plantillas


def test_cada_formato_del_esquema_tiene_su_ficha_y_al_reves():
    assert set(get_args(Formato)) == set(formatos.FORMATOS)


def test_los_propios_tienen_su_modulo_sus_plantillas_y_sus_reglas():
    for f in formatos.FORMATOS.values():
        if f.propio:
            modulo = importlib.import_module(f"folio.{f.propio}")
            assert modulo.FORMATO == f.id
            assert hasattr(Plantillas, f"_{f.propio}"), f"falta Plantillas._{f.propio}"
            assert not f.firma_folio                    # firman ellos, no la corrección mecánica


def test_lo_que_preguntan_los_demas():
    assert formatos.de("balda").libros == 3 and not formatos.de("balda").exige_novedad
    assert formatos.de("formato-viejo") == formatos.FORMATOS["lateral"]       # piezas de antes: como una lateral
    assert set(formatos.SIN_LIBRO_OBLIGATORIO) >= {"curiosidad", "radar", "noticia", "ensayo", "newsletter"}
    assert formatos.CARRIL_DEL_FORMATO == {"curiosidad": "cajon", "recomendado": "catalogo"}
    assert formatos.nombre("newsletter") == "La newsletter del jueves"
