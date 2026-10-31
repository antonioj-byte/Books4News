"""Recurso gráfico de la diapositiva de actualidad sin foto ni cifra (folio.sin_foto)."""

import pytest

from folio import arte, render, sin_foto
from folio.modelos import Arte, Pieza, SinFoto
from folio.render.textos import texto_html

from datos import ELECCION, LIBRO, guion_valido
from test_arte import _pieza, _propuesta

TEXTO = ("Mariana Enriquez (Buenos Aires, 1973) ha presentado en Barcelona su ensayo sobre el miedo, nacido de "
         "entrevistas que Inti Soledad Bustos transcribió y editó. No tiene capítulos: tiene vértebras.")
TODOS = ["golpe", "gigante", "teletipo", "collage"]


def _sf(**cambios):
    datos = dict(recurso="golpe", golpe="No tiene capítulos: tiene vértebras.", golpe_remate="tiene vértebras",
                 palabra="vértebras", etiquetas=["Barcelona", "ensayo", "miedo"], numero="1973",
                 numero_rotulo="Buenos Aires", sello="No tiene capítulos")
    return SinFoto(**(datos | cambios))


def test_todo_lo_que_se_pinta_sale_literalmente_del_texto():
    sf, avisos = sin_foto.validar(_sf(), TEXTO, TODOS)
    assert avisos == [] and sf.recurso == "golpe" and sf.etiquetas == ["Barcelona", "ensayo", "miedo"]
    # Sin tildes ni mayúsculas también vale, pero no lo que no está en el texto
    sf, avisos = sin_foto.validar(_sf(sello="sin capítulos", palabra="VERTEBRAS", etiquetas=["Barcelona", "terror"]), TEXTO, TODOS)
    assert sf.sello is None and sf.palabra == "VERTEBRAS" and sf.etiquetas == ["Barcelona"]
    assert any("sello" in a for a in avisos) and any("etiqueta" in a for a in avisos)


def test_el_golpe_es_el_final_del_texto_y_su_remate_el_final_del_golpe():
    sf, _ = sin_foto.validar(_sf(golpe="No tiene capítulos"), TEXTO, TODOS)        # no es el final
    assert sf.golpe is None and sf.golpe_remate is None and sf.recurso == "gigante"   # pasa al siguiente con datos
    sf, _ = sin_foto.validar(_sf(golpe_remate="No tiene"), TEXTO, TODOS)
    assert sf.golpe and sf.golpe_remate is None
    sf, _ = sin_foto.validar(_sf(golpe=TEXTO), TEXTO, TODOS)                         # el texto entero, no
    assert sf.golpe is None


def test_con_victimas_no_hay_numero_y_sin_datos_no_hay_recurso():
    sf, _ = sin_foto.validar(_sf(recurso="teletipo"), TEXTO, TODOS, victimas=True)
    assert sf.recurso == "teletipo" and sf.numero is None and sf.numero_rotulo is None
    vacio = SinFoto(recurso="gigante", palabra="inventada")
    sf, avisos = sin_foto.validar(vacio, TEXTO, TODOS)
    assert sf is None and "solo con texto" in avisos[-1]
    # El recurso que no está en la configuración no se usa
    sf, avisos = sin_foto.validar(_sf(recurso="collage"), TEXTO, ["gigante"])
    assert sf.recurso == "gigante"


def test_marcar_el_final_sin_romper_cursivas():
    assert str(sin_foto.marcar("Hola *mundo* y tiene vértebras.", "tiene vértebras", texto_html)) == \
        'Hola <em>mundo</em> y <span class="marca">tiene vértebras.</span>'
    assert sin_foto.marcar("Lee *tiene vértebras*.", "vértebras", texto_html) is None      # cortaría la cursiva
    assert sin_foto.marcar("Otra cosa.", "tiene vértebras", texto_html) is None


def test_el_director_no_pone_collage_en_piezas_graves(cfg):
    pieza = _pieza()
    texto = pieza.guion.diapositivas[1].texto        # «Un tribunal juzga a un funcionario que firmaba órdenes.»
    propuesta = _propuesta(tono="grave", sin_foto=SinFoto(recurso="collage", palabra="tribunal", sello="firmaba órdenes",
                                                         golpe="a un funcionario que firmaba órdenes"))
    a = Arte(tono="grave", recurso="foto")
    arte._composicion(cfg, pieza, propuesta, a)
    assert a.sin_foto.recurso == "golpe" and texto.endswith("firmaba órdenes.")


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def _con_recurso(recurso: str, **arte) -> Pieza:
    p = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
              eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())
    p.guion.diapositivas[1].texto = TEXTO
    sf, _ = sin_foto.validar(_sf(recurso=recurso), TEXTO, TODOS)
    p.arte = Arte(tono="sereno", recurso="foto", sin_foto=sf, acento="pluma", **arte)
    return p


@pytest.mark.parametrize("recurso,se_ve", [
    ("golpe", ['class="titular golpe"', '<span class="remate">tiene vértebras.</span>', "golpe__antes"]),
    ("gigante", ['class="gigante"', "VÉRTEBRAS", '<span class="marca">tiene vértebras.</span>']),
    ("teletipo", ['class="etiqueta">BARCELONA', 'teletipo__numero" data-encajar>1973', "teletipo__rotulo\">Buenos Aires"]),
    ("collage", ['class="tira"', "<span>VÉRTEBRAS</span>", 'sello__arriba">NO TIENE', 'sello__palabra">capítulos']),
])
def test_la_actualidad_sin_foto_pinta_su_recurso(cfg_diseno, recurso, se_ve):
    html = render.Plantillas(cfg_diseno).html_diapositiva(_con_recurso(recurso), 2)
    assert f"sin-foto sin-foto--{recurso}" in html
    for trozo in se_ve:
        assert trozo in html


def test_con_cifra_o_texto_editado_sale_como_antes(cfg_diseno):
    p = render.Plantillas(cfg_diseno)
    con_cifra = _con_recurso("gigante", cifra="1973")
    assert "sin-foto" not in p.html_diapositiva(con_cifra, 2) and "cifra__numero" in p.html_diapositiva(con_cifra, 2)
    editada = _con_recurso("golpe")
    editada.guion.diapositivas[1].texto = "Otro texto, editado en la web, que ya no acaba igual."
    html = p.html_diapositiva(editada, 2)
    assert "sin-foto" not in html and "Otro texto" in html
    # Las demás diapositivas no llevan el recurso
    assert "sin-foto" not in p.html_diapositiva(_con_recurso("gigante"), 3)
