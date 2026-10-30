import re

import pytest

from folio import render
from folio.modelos import Pieza

from datos import ELECCION, LIBRO, guion_valido


@pytest.fixture
def pieza():
    from folio.guion import ajustar_libros
    g = guion_valido()
    ajustar_libros(g, [LIBRO])  # como en el pipeline: la ficha con los datos verificados
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=g)


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_tokens_a_variables_css():
    css = render.css_tokens({"colores": {"papel": "#fff", "tinta_suave": "#666"}, "logotipo": "<svg/>"})
    assert "--colores-papel: #fff;" in css and "--colores-tinta-suave: #666;" in css
    assert "svg" not in css


def test_texto_escapado_y_cursivas():
    assert str(render.texto_html("En *La peste* <b>x</b> & y")) == "En <em>La peste</em> &lt;b&gt;x&lt;/b&gt; &amp; y"


def test_plantillas_solo_usan_variables_de_los_tokens(cfg_diseno):
    """Cambiar el design system es cambiar diseno/tokens.yaml, no las plantillas (también en las propuestas)."""
    carpetas = [render.dir_diseno(cfg_diseno)] + [render.dir_diseno(cfg_diseno, d) for d in render.direcciones(cfg_diseno)]
    for archivo in (a for c in carpetas for a in (c / "plantillas").iterdir()):
        texto = archivo.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", texto), f"color a fuego en {archivo.name}"
        assert not re.search(r"font-family:\s*(?!var\()['\"A-Za-z]", texto), f"fuente a fuego en {archivo.name}"


def test_html_de_cada_diapositiva(cfg_diseno, pieza):
    p = render.Plantillas(cfg_diseno)
    portada = p.html_diapositiva(pieza, 1, base_url="/diseno/")
    assert '<base href="/diseno/">' in portada and "diapositiva--portada" in portada and "1 / 5" in portada
    assert "--colores-papel" in portada and 'class="logotipo"' in portada
    cierre = p.html_diapositiva(pieza, 5)
    # Firma el logotipo: la firma del texto no se repite; la ficha lleva los datos verificados
    assert "Léelo." in cierre and "Léelo. Folio" not in cierre
    assert "Debolsillo, 2014" in cierre and "ficha__libro" in cierre


def test_render_png_de_1080x1350(cfg_diseno, pieza, tmp_path):
    pytest.importorskip("playwright")
    from PIL import Image
    try:
        archivos, avisos = render.renderizar(cfg_diseno, [pieza], tmp_path)
    except Exception as exc:  # sin navegador en este entorno
        pytest.skip(f"Chromium no disponible: {exc}")
    assert [a.name for a in archivos] == ["01-portada.png", "02-actualidad.png", "03-libro.png", "04-idea.png", "05-cierre.png"]
    assert all(Image.open(a).size == (1080, 1350) for a in archivos) and avisos == []


def test_propuestas_de_diseno(cfg_diseno, pieza):
    """Cada propuesta pinta todas las diapositivas; las que usan imagen y cubierta las ponen si las hay."""
    assert {"suplemento", "revista", "lomo"} <= set(render.direcciones(cfg_diseno))
    imagen = {pieza.id: {"src": "file:///tmp/foto.jpg", "credito": "Autor · Museo · Dominio público · Europeana"}}
    for d in render.direcciones(cfg_diseno):
        p = render.Plantillas(cfg_diseno, d, imagen)
        p._cubierta = lambda libro: "file:///tmp/cubierta.jpg"
        p.cubiertas = True
        htmls = [p.html_diapositiva(pieza, n) for n in range(1, len(pieza.guion.diapositivas) + 1)]
        assert all("--colores-papel" in h for h in htmls)
        if d == "revista":
            assert "file:///tmp/foto.jpg" in htmls[0] and "Dominio público" in htmls[0]
            assert "file:///tmp/cubierta.jpg" in htmls[-1]
        if d == "lomo":
            assert "--tela:" in htmls[0]


def test_libro_de_la_diapositiva(pieza):
    libros = render.ficha_libros(pieza)
    assert render.libro_de_diapositiva(libros, pieza, "Arendt vio en *Eichmann en Jerusalén* a un hombre corriente.")["autor"]
    assert render.libro_de_diapositiva(libros, pieza, "Nada que ver") is None
