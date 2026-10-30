import httpx
import pytest

from folio.libros.fuentes import GoogleBooks, pais_isbn
from folio.libros.verificacion import NoVerificado, Verificador
from folio.modelos import LibroCandidato

from conftest import transporte_openlibrary


@pytest.fixture
def verificador(cfg):
    return Verificador(cfg, httpx.Client(transport=transporte_openlibrary()))


def test_libro_real_con_titulo_en_espanol(verificador):
    l = verificador.verificar(LibroCandidato(titulo="Eichmann en Jerusalén", autor="Hannah Arendt"))
    assert l.olid == "OL1386647W"
    assert l.titulo == "Eichmann in Jerusalem"
    assert l.edicion_es == "si"
    # La edición elegida es en español, no la gallega («Xerusalén»)
    assert "Jerusalén" in l.edicion_es_detalle.titulo
    assert l.edicion_es_detalle.pais == "España"
    assert l.idioma_original == "inglés"


def test_libro_inventado(verificador):
    with pytest.raises(NoVerificado, match="ninguna fuente"):
        verificador.verificar(LibroCandidato(titulo="El jardín de las máquinas tristes", autor="Laura Ferrán"))


def test_autor_equivocado(verificador):
    with pytest.raises(NoVerificado):
        verificador.verificar(LibroCandidato(titulo="Eichmann en Jerusalén", autor="Michel Foucault"))


def test_sin_google_books_no_afirma_que_no_hay_edicion(cfg):
    """Con una sola fuente, si no se encuentra edición española el valor es «desconocido», nunca «no»."""
    def manejar(req):
        if req.url.path == "/search.json":
            return httpx.Response(200, json={"docs": [{"key": "/works/OL1W", "title": "Some Book",
                                                       "author_name": ["Ann Writer"], "first_publish_year": 2001,
                                                       "language": ["eng"]}]})
        return httpx.Response(200, json={"entries": [{"title": "Some Book", "publishers": ["X"],
                                                      "publish_date": "2001", "languages": [{"key": "/languages/eng"}]}]})
    v = Verificador(cfg, httpx.Client(transport=httpx.MockTransport(manejar)))
    l = v.verificar(LibroCandidato(titulo="Some Book", autor="Ann Writer"))
    assert l.edicion_es == "desconocido"


def test_error_de_red_no_se_confunde_con_inexistente(cfg):
    v = Verificador(cfg, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    with pytest.raises(NoVerificado, match="no se pudo consultar"):
        v.verificar(LibroCandidato(titulo="La peste", autor="Albert Camus"))


def test_pais_isbn():
    assert pais_isbn("9788432320750") == "España"
    assert pais_isbn("9789879870143") == "Argentina"
    assert pais_isbn("9780140180206") is None


def test_error_de_google_books_no_filtra_la_clave(cfg):
    """El mensaje de error acaba en las notas del informe: no puede llevar la clave."""
    cfg.google_books_api_key = "CLAVE-SECRETA-123"
    pedidas = []

    def manejar(req):
        if req.url.host == "www.googleapis.com":
            pedidas.append(req.url)
            return httpx.Response(403)
        if req.url.path == "/search.json":
            return httpx.Response(200, json={"docs": [{"key": "/works/OL1W", "title": "Some Book",
                                                       "author_name": ["Ann Writer"], "language": ["eng"]}]})
        return httpx.Response(200, json={"entries": []})

    v = Verificador(cfg, httpx.Client(transport=httpx.MockTransport(manejar)))
    l = v.verificar(LibroCandidato(titulo="Some Book", autor="Ann Writer"))
    assert l.edicion_es == "desconocido"
    assert any("Google Books" in n for n in l.notas)
    assert "CLAVE-SECRETA-123" not in l.model_dump_json()
    # Sin país, Google Books responde 403 desde IPs que no sabe geolocalizar
    assert all(u.params.get("country") == "ES" for u in pedidas)


def test_google_books_reintenta_un_503(cfg):
    cfg.google_books_api_key = "x"
    respuestas = iter([httpx.Response(503), httpx.Response(200, json={"items": []})])
    gb = GoogleBooks(httpx.Client(transport=httpx.MockTransport(lambda r: next(respuestas))), "x")
    assert gb.buscar("La peste", "Albert Camus") == []
