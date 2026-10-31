"""Fotos de autor de las páginas de las editoriales (folio.imagenes.prensa), con la web simulada."""

import httpx
import pytest
from PIL import Image
from io import BytesIO

from folio.imagenes import libres, prensa

LISTA = '<a href="/autor/enriquez-mariana-1418">Mariana Enriquez</a><a href="/autor/enriquez-juan-9">Juan</a>'
FICHA = ('<img class="x" src="https://cms.anagrama-ed.es/uploads/media/autores/0001/28/thumb_1_autores_big.jpeg" '
         'width="400" alt="Mariana Enriquez"><p>Fotograf\u00eda \u00a9 Sebasti\u00e1n Freire</p>')


def _jpeg(tam=(520, 507)):
    b = BytesIO()
    Image.new("RGB", tam, (90, 80, 70)).save(b, "JPEG")
    return b.getvalue()


def _cliente(estado=200, tam=(520, 507)):
    def responder(req):
        if estado != 200:
            return httpx.Response(estado)
        ruta = req.url.path
        if ruta.startswith("/autores/"):
            return httpx.Response(200, text=LISTA)
        if ruta.startswith("/autor/"):
            return httpx.Response(200, text=FICHA)
        return httpx.Response(200, content=_jpeg(tam))
    return httpx.Client(transport=httpx.MockTransport(responder))


def test_reconoce_la_editorial_con_o_sin_la_palabra_editorial():
    assert prensa.adaptador("Anagrama")[0] == prensa.adaptador("Editorial Anagrama")[0] == "Anagrama"
    assert prensa.adaptador("Planeta") is None and prensa.adaptador(None) is None


def test_fija_la_foto_con_el_credito_del_fotografo(tmp_path):
    img, motivo = prensa.buscar_y_fijar("Mariana Enríquez", "Anagrama", "p1", tmp_path, _cliente())
    assert motivo == "" and img.credito == "Sebastián Freire · cortesía de Anagrama" and prensa.es_de_prensa(img)
    assert img.persona == "Mariana Enríquez" and (libres.dir_imagenes(tmp_path) / "p1-retrato.jpg").exists()


def test_foto_pequena_o_bloqueo(tmp_path):
    img, motivo = prensa.buscar_y_fijar("Mariana Enriquez", "Anagrama", "p1", tmp_path, _cliente(tam=(200, 200)))
    assert img is None and "pequeña" in motivo
    with pytest.raises(prensa.BloqueoEditorial):
        prensa.buscar_y_fijar("Mariana Enriquez", "Anagrama", "p1", tmp_path, _cliente(estado=429))
