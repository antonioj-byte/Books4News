"""Ante 403/429, Commons, Europeana, Open Library y Google Books paran sin reintentar (revisión general, 2/11). Sin red."""

import httpx
import pytest

from folio.imagenes import libres
from folio.libros import fuentes


def _cliente(codigos, pedidas):
    def manejar(req):
        pedidas.append(req.url)
        return httpx.Response(codigos.pop(0) if codigos else 200, json={"query": {"pages": {}}})
    return httpx.Client(transport=httpx.MockTransport(manejar))


def test_commons_para_ante_403_y_no_vuelve_a_llamar(monkeypatch):
    monkeypatch.setattr(libres, "_bloqueos", {})
    monkeypatch.setattr(libres.time, "sleep", lambda s: pytest.fail("no debería esperar"))
    pedidas = []
    c = _cliente([403], pedidas)
    with pytest.raises(libres.ServicioBloqueado):
        libres.buscar_commons("press", cliente=c)
    with pytest.raises(httpx.HTTPError):                      # los llamantes ya capturan httpx.HTTPError
        libres.buscar_commons("press", cliente=c)
    assert len(pedidas) == 1 and "Commons respondió 403" in libres.bloqueos()[0]


def test_commons_reintenta_un_5xx_una_vez(monkeypatch):
    monkeypatch.setattr(libres, "_bloqueos", {})
    monkeypatch.setattr(libres.time, "sleep", lambda s: None)
    pedidas = []
    assert libres.buscar_commons("press", cliente=_cliente([503], pedidas)) == [] and len(pedidas) == 2


def test_los_catalogos_no_reintentan_un_429(monkeypatch):
    monkeypatch.setattr(fuentes.time, "sleep", lambda s: None)
    codigos = [429]
    r = fuentes._reintentar(lambda: httpx.Response(codigos.pop(0) if codigos else 200), 4, 0)
    assert r.status_code == 429
    codigos = [503, 503]
    assert fuentes._reintentar(lambda: httpx.Response(codigos.pop(0) if codigos else 200), 4, 0).status_code == 200
