"""Ronda 4 de mejora (seguridad): las descargas de URLs de fuera no llegan a direcciones internas."""

import httpx
import pytest

from folio import red, temas


def _transporte(pedidas):
    def manejar(req):
        pedidas.append(str(req.url))
        if req.url.host == "93.184.216.34" and req.url.path == "/redirige":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8000/api/dias"})
        return httpx.Response(200, text="<html><body><p>" + "Texto de la noticia. " * 40 + "</p></body></html>")
    return httpx.MockTransport(manejar)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.2", "169.254.169.254", "[::1]",
                                  "[fd12:3456::1]", "api.railway.internal", "0.0.0.0"])
def test_las_direcciones_internas_no_son_publicas(host):
    assert not red.es_publica(host)


def test_una_ip_publica_si():
    assert red.es_publica("93.184.216.34")


def test_la_redireccion_a_la_api_interna_se_corta_antes_de_pedirla():
    pedidas = []
    c = red.cliente_externo(transport=_transporte(pedidas), follow_redirects=True)
    fuente, motivo = temas.descargar("http://93.184.216.34/redirige", c)
    assert fuente is None and "DestinoNoPermitido" in motivo
    assert pedidas == ["http://93.184.216.34/redirige"]                 # la interna nunca se pidió
    assert temas.descargar("http://127.0.0.1:8000/api/dias", c)[0] is None and len(pedidas) == 1
    assert temas.descargar("http://93.184.216.34/noticia", c)[0] is not None   # lo de fuera, igual que antes


def test_el_error_es_un_fallo_de_descarga_normal():
    assert issubclass(red.DestinoNoPermitido, httpx.HTTPError)
