from io import BytesIO

from PIL import Image

from folio import arte
from folio.modelos import Pieza, PropuestaArte

from datos import ELECCION, LIBRO, guion_valido


def _pieza():
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())


def _propuesta(**cambios):
    datos = dict(tono="sereno", suceso_con_victimas=False, recurso="foto", consultas=["court"], evitar=[],
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
