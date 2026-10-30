import pytest

from folio import config


@pytest.fixture
def sin_claves(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FOLIO_ANTHROPIC_API_KEY", raising=False)
    # Evita que un .env local interfiera: cargar() lee el .env de la raíz indicada
    raiz = tmp_path / "repo"
    (raiz / "config").mkdir(parents=True)
    for nombre in ("pipeline.yaml", "fuentes.yaml"):
        (raiz / "config" / nombre).write_text((config.RAIZ / "config" / nombre).read_text(encoding="utf-8"), encoding="utf-8")
    return raiz


def test_clave_anthropic_prioriza_la_estandar(sin_claves, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "estandar")
    monkeypatch.setenv("FOLIO_ANTHROPIC_API_KEY", "folio")
    assert config.cargar(sin_claves).anthropic_api_key == "estandar"


def test_clave_anthropic_usa_folio_si_falta_la_estandar(sin_claves, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("FOLIO_ANTHROPIC_API_KEY", "folio")
    assert config.cargar(sin_claves).anthropic_api_key == "folio"


def test_clave_anthropic_ausente(sin_claves):
    assert config.cargar(sin_claves).anthropic_api_key is None
