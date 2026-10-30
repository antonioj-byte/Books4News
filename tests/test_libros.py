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


def test_google_books_reintenta_y_repite_sin_intitle():
    item = {"id": "g1", "volumeInfo": {"title": "La peste", "authors": ["Albert Camus"], "language": "es"}}
    respuestas = iter([httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"totalItems": 0}),
                       httpx.Response(200, json={"items": [item]})])
    pedidas = []

    def manejar(req):
        pedidas.append(req.url.params["q"])
        return next(respuestas)

    gb = GoogleBooks(httpx.Client(transport=httpx.MockTransport(manejar)), "x")
    obras = gb.buscar("La peste", "Albert Camus")
    assert [o.id for o in obras] == ["g1"]
    assert pedidas[0].startswith("intitle:") and not pedidas[-1].startswith("intitle:")


def test_google_books_se_rinde_tras_los_reintentos():
    llamadas = []
    gb = GoogleBooks(httpx.Client(transport=httpx.MockTransport(lambda r: llamadas.append(r) or httpx.Response(503))), "x")
    with pytest.raises(httpx.HTTPStatusError):
        gb.buscar("La peste", "Albert Camus")
    assert len(llamadas) == GoogleBooks.INTENTOS


def test_verifica_con_el_titulo_original_si_el_espanol_no_esta(cfg):
    """Open Library no tiene «El viejo rey en su exilio», pero sí «Der alte König in seinem Exil»."""
    def manejar(req):
        if req.url.path == "/search.json":
            if "König" not in req.url.params["q"]:
                return httpx.Response(200, json={"docs": []})
            return httpx.Response(200, json={"docs": [{"key": "/works/OL2W", "title": "Der alte König in seinem Exil",
                                                       "author_name": ["Arno Geiger"], "language": ["ger"]}]})
        return httpx.Response(200, json={"entries": []})

    v = Verificador(cfg, httpx.Client(transport=httpx.MockTransport(manejar)))
    l = v.verificar(LibroCandidato(titulo="El viejo rey en su exilio", autor="Arno Geiger",
                                   titulo_original="Der alte König in seinem Exil", idioma_original="alemán"))
    assert l.olid == "OL2W" and l.titulo_propuesto == "El viejo rey en su exilio"


def test_edicion_original_no_es_un_audiolibro(cfg):
    def manejar(req):
        if req.url.path == "/search.json":
            return httpx.Response(200, json={"docs": [{"key": "/works/OL3W", "title": "Number Go Up",
                                                       "author_name": ["Zeke Faux"], "first_publish_year": 2023,
                                                       "language": ["eng"]}]})
        return httpx.Response(200, json={"entries": [
            {"title": "Number Go Up", "publishers": ["Random House Audio"], "publish_date": "2023",
             "languages": [{"key": "/languages/eng"}], "physical_format": "Audio CD"},
            {"title": "Number Go Up", "publishers": ["Currency"], "publish_date": "Sep 2023",
             "languages": [{"key": "/languages/eng"}], "physical_format": "Hardcover"},
        ]})

    v = Verificador(cfg, httpx.Client(transport=httpx.MockTransport(manejar)))
    assert v.verificar(LibroCandidato(titulo="Number Go Up", autor="Zeke Faux")).editorial_original == "Currency"


def _transporte_ol_ingles_y_gb(items_gb):
    def manejar(req):
        if req.url.host == "www.googleapis.com":
            return httpx.Response(200, json={"items": items_gb})
        if req.url.path == "/search.json":
            return httpx.Response(200, json={"docs": [{"key": "/works/OL1W", "title": "Some Book",
                                                       "author_name": ["Ann Writer"], "language": ["eng"]}]})
        return httpx.Response(200, json={"entries": [{"title": "Some Book", "publishers": ["X"],
                                                      "publish_date": "2001", "languages": [{"key": "/languages/eng"}]}]})
    return httpx.MockTransport(manejar)


def test_no_afirma_que_no_hay_edicion_si_google_books_no_encuentra_la_obra(cfg):
    cfg.google_books_api_key = "x"
    v = Verificador(cfg, httpx.Client(transport=_transporte_ol_ingles_y_gb([])))
    assert v.verificar(LibroCandidato(titulo="Some Book", autor="Ann Writer")).edicion_es == "desconocido"


def test_afirma_que_no_hay_edicion_si_ambas_fuentes_encuentran_la_obra(cfg):
    cfg.google_books_api_key = "x"
    item = {"id": "g1", "volumeInfo": {"title": "Some Book", "authors": ["Ann Writer"], "language": "en"}}
    v = Verificador(cfg, httpx.Client(transport=_transporte_ol_ingles_y_gb([item])))
    assert v.verificar(LibroCandidato(titulo="Some Book", autor="Ann Writer")).edicion_es == "no"
