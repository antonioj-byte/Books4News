from ebooklib import epub

from videos import libro as lib
from conftest import CAPITULO_1


def test_txt_por_capitulos(libro_txt):
    l = lib.leer(libro_txt, "El descanso", "Ana Pérez")
    assert [c.titulo for c in l.capitulos] == ["Capítulo 1", "Capítulo 2"]
    assert l.titulo == "El descanso" and l.autor == "Ana Pérez"


def test_literal_tolera_mayusculas_tildes_y_signos(libro_txt):
    l = lib.leer(libro_txt)
    ref = lib.buscar_literal(l, "el cerebro que no hace nada se pone a rumiar y rumiar CANSA mas que trabajar")
    assert ref is not None and ref.capitulo == 1
    assert lib.buscar_literal(l, "el cerebro que no hace nada se pone a pensar en sus cosas") is None
    assert lib.buscar_literal(l, "corto") is None


def test_epub_con_marcas_de_pagina(tmp_path):
    e = epub.EpubBook()
    e.set_title("Libro EPUB")
    e.add_author("Autora")
    c1 = epub.EpubHtml(title="Uno", file_name="c1.xhtml", lang="es")
    c1.content = (f'<html><body><h1>Uno</h1><span epub:type="pagebreak" title="11"/><p>{CAPITULO_1[:300]}</p>'
                  f'<span epub:type="pagebreak" title="12"/><p>{CAPITULO_1[300:700]} Esta frase solo aparece en la página doce del libro.</p></body></html>')
    e.add_item(c1)
    e.toc = (epub.Link("c1.xhtml", "Uno", "c1"),)
    e.add_item(epub.EpubNcx())
    e.add_item(epub.EpubNav())
    e.spine = ["nav", c1]
    ruta = tmp_path / "l.epub"
    epub.write_epub(str(ruta), e)
    l = lib.leer(ruta)
    assert l.titulo == "Libro EPUB" and l.autor == "Autora"
    cap = next(c for c in l.capitulos if c.titulo == "Uno")
    assert [p for _, p in cap.paginas] == ["11", "12"]
    assert "\u0000" not in cap.texto
    ref = lib.buscar_literal(l, "esta frase solo aparece en la página doce")
    assert ref is not None and ref.pagina == "12"


def test_texto_para_modelo_no_mete_paginas_en_el_texto(libro_txt):
    t = lib.texto_para_modelo(lib.leer(libro_txt))
    assert t.count("<capitulo") == 2 and "PAG:" not in t
