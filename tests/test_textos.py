from datetime import datetime, timezone

from folio import textos
from folio.modelos import Articulo, Historia

URL = "https://example.com/"


def _art(id_, medio, acceso="abierto"):
    return Articulo(id=id_, medio=medio, url=URL + id_, titulo=id_, idioma="es", acceso=acceso,
                    publicado_en=datetime.now(timezone.utc))


def _historia(arts):
    return Historia(id="h", articulos=arts, medios=sorted({a.medio for a in arts}), n_medios=len({a.medio for a in arts}))


def test_uno_por_medio_el_mas_cercano_al_hecho(cfg):
    arts = [_art("forenses", "Europa Press"), _art("audios", "Europa Press"),
            _art("video", "Al Jazeera"), _art("analisis", "Al Jazeera"),
            _art("guardian", "The Guardian"), _art("bbc", "BBC")]
    p = {"forenses": 0.80, "audios": 0.93, "video": 0.70, "analisis": 0.90, "guardian": 0.91, "bbc": 0.89}
    elegidos = [a.id for a in textos.elegir_articulos(cfg, _historia(arts), p)]
    assert elegidos == ["audios", "guardian", "analisis", "bbc"]


def test_abierto_desempata_y_margen_con_minimo(cfg):
    arts = [_art("muro", "FT", "muro"), _art("abierto", "BBC"), _art("lejos1", "DW"), _art("lejos2", "France 24"),
            _art("lejos3", "Le Monde", "parcial")]
    p = {"muro": 0.92, "abierto": 0.915, "lejos1": 0.70, "lejos2": 0.69, "lejos3": 0.60}
    elegidos = [a.id for a in textos.elegir_articulos(cfg, _historia(arts), p)]
    # El abierto pasa por delante del de muro por el extra de acceso; los lejanos se descartan
    # salvo para llegar al mínimo de 3
    assert elegidos == ["abierto", "muro", "lejos1"]


def test_maximo_de_textos(cfg):
    arts = [_art(f"a{i}", f"Medio {i}") for i in range(8)]
    p = {f"a{i}": 0.9 - i * 0.001 for i in range(8)}
    assert len(textos.elegir_articulos(cfg, _historia(arts), p)) == cfg.pipeline["guion"]["max_textos"]


def test_sin_puntuaciones_ordena_por_acceso(cfg):
    arts = [_art("muro", "FT", "muro"), _art("parcial", "El País", "parcial"), _art("abierto", "BBC")]
    assert [a.id for a in textos.elegir_articulos(cfg, _historia(arts))] == ["abierto", "parcial", "muro"]
