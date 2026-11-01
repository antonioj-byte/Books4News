"""Lectura periódica de los RSS (folio.ingesta.lecturas) y su lanzador en la API. Sin red ni gasto."""

from datetime import datetime, timedelta, timezone

from folio.ingesta import lecturas, rss
from folio.modelos import Articulo

AHORA = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def _art(i, publicado=None, carril="actualidad"):
    return Articulo(id=f"a{i}", medio="El País", url=f"https://x/{i}", titulo=f"Noticia {i}", idioma="es", acceso="abierto",
                    publicado_en=publicado, carril=carril)


def test_guarda_la_primera_lectura_y_recupera_lo_que_salio_del_rss(cfg, monkeypatch):
    monkeypatch.setattr(rss, "ingerir", lambda cfg, ahora=None: ([_art(1), _art(2)], []))
    assert lecturas.leer(cfg, AHORA - timedelta(hours=6))[:2] == (2, 2)
    monkeypatch.setattr(rss, "ingerir", lambda cfg, ahora=None: ([_art(2), _art(3)], ["feed caído"]))
    nuevos, total, errores = lecturas.leer(cfg, AHORA - timedelta(hours=2))
    assert (nuevos, total, errores) == (1, 3, ["feed caído"])
    # A la hora de la ejecución el RSS solo trae la 3 y una nueva: la 1 y la 2 vuelven, con su primera lectura
    juntos = {a.id: a for a in lecturas.juntar(cfg, [_art(3), _art(4)], AHORA)}
    assert set(juntos) == {"a1", "a2", "a3", "a4"}
    assert juntos["a1"].visto_en == AHORA - timedelta(hours=6) and juntos["a3"].visto_en == AHORA - timedelta(hours=2)
    assert juntos["a4"].visto_en is None
    # Lo que se leyó fuera de la ventana no vuelve
    ventana = cfg.pipeline.ingesta.ventana_horas
    assert "a1" not in {a.id for a in lecturas.juntar(cfg, [], AHORA + timedelta(hours=ventana))}


def test_el_jefe_ve_desde_cuando_circula_la_historia():
    from folio import seleccion
    from folio.modelos import Historia
    a = _art(1, publicado=AHORA).model_copy(update={"visto_en": AHORA - timedelta(days=2)})
    h = Historia(id="h", articulos=[a], medios=["El País"], n_medios=1)
    assert seleccion._desde(h) == (AHORA - timedelta(days=2)).strftime("%Y-%m-%d %H:%M UTC")


def test_el_lector_no_choca_con_una_ejecucion_en_marcha(tmp_path):
    import sys
    import time
    from folio_api.ejecutor import Ejecutor
    from folio_api.programador import Lector
    ej = Ejecutor(tmp_path)
    assert ej.lanzar([[sys.executable, "-c", "import time; time.sleep(0.5)"]])
    lanzadas = []
    assert not Lector(ej, 120, lambda: lanzadas.append(1) or 0).una_vuelta() and lanzadas == []
    while ej.ocupado():
        time.sleep(0.05)
    assert Lector(ej, 120, lambda: lanzadas.append(1) or 0).una_vuelta() and lanzadas == [1]


def test_con_la_lectura_a_medias_no_se_lanza_la_diaria(tmp_path):
    """Ronda 3 de mejora: la diaria (o «Lanzar») no arranca mientras folio leer reescribe lecturas.json; la
    programada lo reintenta en la vuelta siguiente y la web dice por qué. Al acabar la lectura, se puede."""
    import sys
    from folio_api.ejecutor import Ejecutor
    from folio_api.programador import Lector
    ej = Ejecutor(tmp_path)
    vistos = []

    def leer():
        vistos.append((ej.lanzar([[sys.executable, "-c", "pass"]]), ej.motivo_ocupado()))
        return 0
    assert Lector(ej, 120, leer).una_vuelta()
    assert vistos == [(False, "Se están leyendo las noticias (lectura periódica); prueba en unos minutos")]
    assert ej.motivo_ocupado() is None and ej.lanzar([[sys.executable, "-c", "pass"]])

    def falla():
        raise RuntimeError("se cayó")
    while ej.ocupado():
        pass
    try:
        Lector(ej, 120, falla).una_vuelta()
    except RuntimeError:
        pass
    assert ej.motivo_ocupado() is None                       # una lectura que falla no deja el turno cogido


def test_lecturas_se_escriben_de_forma_atomica(cfg, monkeypatch):
    from folio.ingesta import lecturas
    monkeypatch.setattr(rss, "ingerir", lambda cfg, ahora: ([_art(1, publicado=AHORA)], []))
    lecturas.leer(cfg, AHORA)
    assert list(lecturas._cargar(cfg)) and not list(lecturas.ruta(cfg).parent.glob(".lecturas.*.tmp"))


def test_un_feed_que_bloquea_se_pausa_una_semana(cfg, monkeypatch):
    import httpx
    from folio.config import Fuente
    cfg.fuentes = [Fuente(medio="Asymptote", url="https://asymptote.example/feed", idioma="en", acceso="abierto", carril="editorial"),
                   Fuente(medio="Otro", url="https://otro.example/feed", idioma="es", acceso="abierto")]
    pedidas = []

    def manejar(req):
        pedidas.append(str(req.url))
        return httpx.Response(403) if "asymptote" in str(req.url) else httpx.Response(200, text="<rss><channel></channel></rss>")
    real = httpx.Client
    monkeypatch.setattr(rss.httpx, "Client", lambda **k: real(transport=httpx.MockTransport(manejar)))
    _, errores = rss.ingerir(cfg, AHORA)
    assert any("Asymptote" in e and "pausado" in e for e in errores)
    pedidas.clear()
    _, errores = rss.ingerir(cfg, AHORA + timedelta(hours=2))
    assert pedidas == ["https://otro.example/feed"] and any("en pausa" in e for e in errores)
    pedidas.clear()
    rss.ingerir(cfg, AHORA + timedelta(days=8))                        # pasada la semana, se vuelve a probar
    assert "https://asymptote.example/feed" in pedidas


def test_embeddings_de_dia_en_la_cache_comun(cfg, monkeypatch):
    """2/11: la lectura periódica calcula los embeddings de los artículos nuevos y la madrugada ya no los recalcula."""
    import numpy as np
    from folio.ingesta import agrupacion
    from folio.pipeline import Pipeline
    calculados = []

    class Motor:
        def embed(self, textos, batch_size=32):
            calculados.extend(textos)
            return [np.ones(4, dtype=np.float32) for _ in textos]

    monkeypatch.setattr(agrupacion.Embedder, "_cargar", lambda self: Motor())
    monkeypatch.setattr(rss, "ingerir", lambda cfg, ahora=None: ([_art(1), _art(2)], []))
    lecturas.leer(cfg, AHORA)
    assert lecturas.embeber(cfg) == (2, 2) and len(calculados) == 2
    assert lecturas.embeber(cfg) == (0, 2) and len(calculados) == 2          # la segunda vuelta no recalcula
    # La madrugada (otra fecha) lee de la misma caché: no carga el modelo para esos artículos
    monkeypatch.setattr(agrupacion.Embedder, "_cargar", lambda self: (_ for _ in ()).throw(AssertionError("no debe cargar")))
    v = Pipeline(cfg, "2026-11-03").vectores([_art(1), _art(2)])
    assert set(v) == {"a1", "a2"}


def test_nevera_y_memoria_de_dia_una_vez(cfg, monkeypatch):
    """2/11: la lectura periódica lanza la nevera una vez al día (aunque encuentre menos) y la Memoria si toca."""
    from typer.testing import CliRunner
    from folio import cli, config, memoria, nevera
    monkeypatch.setattr(config, "cargar", lambda *a, **k: cfg)
    monkeypatch.setattr(rss, "ingerir", lambda cfg, ahora=None: ([], []))
    monkeypatch.setattr(lecturas, "embeber", lambda cfg: (0, 0))
    llamadas = []
    monkeypatch.setattr(nevera, "buscar", lambda llm, cfg: llamadas.append("nevera") or ([], ["Nevera: nada nuevo"]))
    monkeypatch.setattr(memoria, "analizar", lambda llm, cfg, almacen, origen: llamadas.append(origen) or ([], "", 0))
    cfg.pipeline.seleccion.reparto = {"lateral": 1}                       # sin catálogo de fondo en el test
    for _ in range(2):
        r = CliRunner().invoke(cli.app, ["leer"])
        assert r.exit_code == 0, r.output
    assert llamadas.count("nevera") == 1 and "semanal" in llamadas      # dos vueltas, una sola nevera


def test_con_lectura_periodica_la_diaria_solo_hace_la_mesa(cfg, monkeypatch):
    from folio import render
    from folio.almacen import Almacen
    from folio_api import main
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    monkeypatch.setenv("FOLIO_LECTURA_CADA", "120")
    monkeypatch.setattr(main.Lector, "arrancar", lambda self: None)
    monkeypatch.setattr(main.Programador, "arrancar", lambda self: None)
    app = main.crear_app(cfg, Almacen(cfg.ruta_db), importar=False)
    diaria = app.state.folio.ejecutor.diaria
    assert len(diaria) == 2 and diaria[1][-2:] == ["render", "--video"]
