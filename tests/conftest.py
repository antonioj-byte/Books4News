from pathlib import Path

import httpx
import pytest

from folio import config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Los reintentos de las APIs bibliográficas esperan entre llamadas; en los tests, no."""
    from folio.libros.fuentes import GoogleBooks, OpenLibrary
    monkeypatch.setattr(GoogleBooks, "ESPERA_S", 0)
    monkeypatch.setattr(OpenLibrary, "ESPERA_S", 0)


@pytest.fixture(autouse=True)
def sin_bloqueos():
    """Los bloqueos (403/429) se recuerdan durante la ejecución; cada test empieza sin ninguno."""
    from folio.imagenes import retratos
    retratos.reiniciar()
    yield
    retratos.reiniciar()


@pytest.fixture
def cfg(tmp_path):
    """Config real del repo, pero con datos e informes en un directorio temporal."""
    c = config.cargar()
    c.anthropic_api_key = "test"
    c.pipeline.guion.lector_sin_contexto = False   # los modelos simulados de los tests no lo atienden (tiene su test)
    c.pipeline.seleccion.buscar_balda = False      # ni la búsqueda de la balda (tiene su test)
    c.google_books_api_key = None
    raiz_tmp = tmp_path / "repo"
    raiz_tmp.mkdir()
    (raiz_tmp / "prompts").symlink_to(c.raiz / "prompts")
    c.raiz = raiz_tmp
    return c


def transporte_openlibrary():
    """MockTransport que sirve las respuestas grabadas de Open Library."""
    def manejar(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/search.json":
            q = req.url.params.get("q", "")
            nombre = "ol_search_arendt.json" if "Eichmann" in q else "ol_search_inexistente.json"
            return httpx.Response(200, content=(FIXTURES / nombre).read_bytes())
        if req.url.path == "/works/OL1386647W/editions.json":
            return httpx.Response(200, content=(FIXTURES / "ol_editions_OL1386647W.json").read_bytes())
        return httpx.Response(404)
    return httpx.MockTransport(manejar)
