from io import BytesIO

from PIL import Image

from folio import arte
from folio.modelos import Pieza, PropuestaArte

from datos import ELECCION, LIBRO, guion_valido


def _pieza():
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())


def _propuesta(**cambios):
    datos = dict(tono="sereno", portada="circulo", suceso_con_victimas=False, recurso="foto", consultas=["court"], evitar=[],
                 cifra=None, cifra_rotulo=None, por_que="x")
    return PropuestaArte(**(datos | cambios))


def test_cifra_literal_de_la_actualidad():
    # La diapositiva de actualidad dice: «Un tribunal juzga a un funcionario que firmaba órdenes.»
    p = _propuesta(cifra="tribunal", cifra_rotulo="juzga a un funcionario")
    assert arte.validar_cifra(p, _pieza()) == [] and p.cifra == "tribunal"


def test_cifra_inventada_o_con_victimas_se_descarta():
    p = _propuesta(cifra="500 millones", cifra_rotulo="de euros")
    assert "no está" in arte.validar_cifra(p, _pieza())[0] and p.cifra is None
    p = _propuesta(cifra="tribunal", suceso_con_victimas=True)
    assert "víctimas" in arte.validar_cifra(p, _pieza())[0] and p.cifra is None


def test_rotulo_con_palabras_de_mas_se_descarta():
    p = _propuesta(cifra="tribunal", cifra_rotulo="juzga a un ministro corrupto")
    assert "Rótulo" in arte.validar_cifra(p, _pieza())[0]
    assert p.cifra == "tribunal" and p.cifra_rotulo is None


def test_hoja_de_contactos():
    hoja = Image.open(BytesIO(arte.hoja_de_contactos([Image.new("RGB", (800, 600), "red")] * 4)))
    assert hoja.size == (3 * 360, 2 * 360)


def test_antetitulo():
    assert arte.validar_antetitulo(" prensa y poder. ") == "PRENSA Y PODER"
    assert arte.validar_antetitulo("una etiqueta demasiado larga") is None
    assert arte.validar_antetitulo(None) is None


def test_remate_literal_al_final_del_titular():
    t = "Nóvaya Gazeta apaga la luz y Rusia pierde a quien la anotaba."
    assert arte.validar_remate("a quien la anotaba.", t) == "a quien la anotaba"
    assert arte.validar_remate("pierde a quien", t) is None          # no es el final
    assert arte.validar_remate("anotaba", t) is None                 # una sola palabra
    assert arte.validar_remate(t, t) is None                         # el titular entero


def test_el_retrato_es_del_autor_del_libro_principal_del_guion():
    from folio.modelos import LibroGuion
    otro = LIBRO.model_copy(update={"titulo": "Ficciones", "titulo_propuesto": "Ficciones", "autores": ["Jorge Luis Borges"], "olid": "OL1W"})
    p = _pieza()
    p.libros = [otro, LIBRO]                       # verificados en otro orden
    assert arte.autor_principal(p) == "Hannah Arendt"   # el guion lleva Eichmann en Jerusalén como principal
    p.guion.libros = [LibroGuion(titulo="Ficciones", autor="Jorge Luis Borges", editorial_espanola=None, traductor=None, edicion_original="x")]
    assert arte.autor_principal(p) == "Jorge Luis Borges"
