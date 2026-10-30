from folio.config import Fuente
from folio.ingesta.rss import normalizar_url, parsear

from conftest import FIXTURES


def test_parsear_feed_real():
    f = Fuente(medio="Europa Press", url="x", idioma="es", acceso="abierto")
    arts = parsear((FIXTURES / "rss_europapress.xml").read_bytes(), f)
    assert len(arts) >= 5
    a = arts[0]
    assert a.medio == "Europa Press" and a.titulo and a.url.startswith("http")
    assert "<" not in a.entradilla
    assert len({x.id for x in arts}) == len(arts)


def test_normalizar_url_quita_seguimiento():
    assert normalizar_url("https://WWW.ejemplo.com/a/b/?utm_source=rss#x") == "https://www.ejemplo.com/a/b"
