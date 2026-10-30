from folio import guion
from folio.modelos import Diapositiva, LibroGuion

from datos import ELECCION, FUENTES, LIBRO, guion_valido, pie


def errores(cfg, g):
    return guion.validar(cfg, g, [LIBRO], FUENTES)


def test_guion_valido(cfg):
    assert errores(cfg, guion_valido()) == []


def test_cita_entre_comillas_rechazada(cfg):
    g = guion_valido()
    g.diapositivas[2].texto = "Arendt escribió «la banalidad del mal es lo que nos rodea»."
    assert any("comillas" in e for e in errores(cfg, g))


def test_titulo_entre_comillas_permitido(cfg):
    g = guion_valido()
    g.diapositivas[2].texto = "En «Eichmann en Jerusalén» Arendt describe a un burócrata."
    assert errores(cfg, g) == []


def test_extension_y_estructura(cfg):
    g = guion_valido()
    g.diapositivas[0].texto = "Una portada demasiado larga que tiene bastante más de doce palabras en total aquí"
    g.diapositivas = g.diapositivas[:3]
    es = errores(cfg, g)
    assert any("entre 4 y 7" in e for e in es)
    assert any("máximo 12" in e for e in es)
    assert any("cierre" in e for e in es)


def test_portada_pregunta_y_frase_vetada(cfg):
    g = guion_valido()
    g.diapositivas[0].texto = "¿Quién obedece?"
    g.diapositivas[3].texto = "En un mundo donde todos obedecen, nadie decide."
    es = errores(cfg, g)
    assert any("pregunta" in e for e in es) and any("vetada" in e for e in es)


def test_libro_no_verificado(cfg):
    g = guion_valido(libros=[LibroGuion(titulo="El jardín de las máquinas tristes", autor="Laura Ferrán",
                                        editorial_espanola=None, traductor=None, edicion_original="x")])
    assert any("no está entre los verificados" in e for e in errores(cfg, g))


def test_fuente_inventada_y_pie(cfg):
    g = guion_valido(fuentes_noticia=["El País https://elpais.com/inventada"], pie_instagram=pie(30))
    es = errores(cfg, g)
    assert any("Fuente no reconocida" in e for e in es)
    assert any("entre 80 y 150" in e for e in es)


def test_ajustar_libros_usa_datos_verificados():
    g = guion_valido()
    avisos = guion.ajustar_libros(g, [LIBRO])
    assert g.libros[0].editorial_espanola == "Debolsillo"
    assert g.libros[0].traductor is None
    assert g.libros[0].edicion_original == "inglés, Viking, 1963"
    assert avisos


def test_prompt_contiene_datos_delimitados(cfg):
    p = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto de la noticia")], [LIBRO])
    assert "[pegar]" not in p and "<noticia>" in p and "<libros_verificados>" in p
    assert "Debolsillo" in p
