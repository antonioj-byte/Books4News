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


def test_el_lector_no_choca_con_una_ejecucion_en_marcha():
    from folio_api.programador import Lector

    class Ej:
        def __init__(self, ocupado): self._o = ocupado
        def ocupado(self): return self._o
    lanzadas = []
    assert not Lector(Ej(True), 120, lambda: lanzadas.append(1) or 0).una_vuelta() and lanzadas == []
    assert Lector(Ej(False), 120, lambda: lanzadas.append(1) or 0).una_vuelta() and lanzadas == [1]


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
