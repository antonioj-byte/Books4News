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


def _yaml(sin_claves, cambio):
    import yaml
    ruta = sin_claves / "config" / "pipeline.yaml"
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cambio(datos)
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")


def test_pipeline_yaml_tipado(sin_claves):
    cfg = config.cargar(sin_claves)
    assert cfg.pipeline.guion.max_textos == 5 and cfg.pipeline["guion"]["max_textos"] == 5
    assert cfg.pipeline.seleccion_textos.bonus_acceso["abierto"] == 0.02
    assert cfg.modelo("guion") == "claude-opus-5-5" and cfg.pipeline.ab.variantes["voz-estilo"].estilo


def test_clave_mal_escrita_falla_al_cargar(sin_claves):
    import pydantic
    _yaml(sin_claves, lambda d: d["guion"].update({"reintentoss": 2}))
    with pytest.raises(pydantic.ValidationError, match="reintentoss"):
        config.cargar(sin_claves)


def test_esfuerzo_invalido_o_que_falta(sin_claves):
    import pydantic
    _yaml(sin_claves, lambda d: d["esfuerzo"].update({"guion": "altísimo"}))
    with pytest.raises(pydantic.ValidationError, match="guion"):
        config.cargar(sin_claves)


def test_control_ab_tiene_que_existir(sin_claves):
    import pydantic
    _yaml(sin_claves, lambda d: d["ab"].update({"control": "inventada"}))
    with pytest.raises(pydantic.ValidationError, match="inventada"):
        config.cargar(sin_claves)
