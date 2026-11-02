"""Los modelos saben qué día es y cuándo se publicó cada fuente (2/11: la detención de Durov, de agosto de 2024,
salía en el pie como si fuera de ayer). Sin red ni gasto."""

from folio import guion, hechos
from folio.modelos import FuenteNoticia

from datos import ELECCION, LIBRO, guion_valido


def test_fecha_larga_y_de_pieza():
    assert guion.fecha_larga("2026-11-02") == "2 de noviembre de 2026"
    assert guion.fecha_de_pieza("2026-11-01-9") == "2026-11-01"
    assert guion.fecha_de_pieza("tema-3")                                  # sin fecha en el id: la de hoy


def test_el_guionista_y_el_comprobador_ven_la_fecha(cfg):
    f = FuenteNoticia(medio="Le Monde", titulo="Durov", url="https://x", acceso="abierto", publicado="2024-08-25")
    p = guion.construir_prompt(cfg, ELECCION, [(f, "Texto")], [LIBRO], fecha="2026-11-02")
    assert "Hoy es 2 de noviembre de 2026." in p and 'publicado="2024-08-25"' in p
    assert "El tiempo de la noticia" in p
    assert 'publicado="2024-08-25"' in hechos._bloque_fuentes([(f, "Texto")])
    sin = FuenteNoticia(medio="X", titulo="t", url="https://y", acceso="abierto")
    assert "publicado" not in hechos._bloque_fuentes([(sin, "Texto")])
