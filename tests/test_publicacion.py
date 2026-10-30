import httpx
import pytest

from folio.publicacion import enlaces, instagram as ig_mod
from folio.publicacion.instagram import ErrorInstagram, Instagram

TOKEN = "IGAAtoken-secreto-123"
RUTA = "2026-10-30/2026-10-30-1/02.jpg"


@pytest.fixture(autouse=True)
def sin_espera(monkeypatch):
    monkeypatch.setattr(ig_mod, "ESPERA_S", 0)


# --- Enlaces firmados -----------------------------------------------------------

def test_enlace_firmado_vale_hasta_que_caduca():
    url = enlaces.firmar("https://folio.example/", "clave", RUTA, 3600, ahora=1000)
    _, resto = url.split("/api/publico/")
    caduca, firma, ruta = resto.split("/", 2)
    assert url.startswith("https://folio.example/api/publico/4600/") and ruta == RUTA
    assert enlaces.valida("clave", int(caduca), firma, ruta, ahora=4599)
    assert not enlaces.valida("clave", int(caduca), firma, ruta, ahora=4601)          # caducado
    assert not enlaces.valida("otra", int(caduca), firma, ruta, ahora=2000)           # otra clave
    assert not enlaces.valida("clave", int(caduca) + 1, firma, ruta, ahora=2000)       # caducidad alterada
    assert not enlaces.valida("", int(caduca), firma, ruta, ahora=2000)               # sin clave, nada
    with pytest.raises(ValueError):
        enlaces.firmar("https://x", "clave", "2026-10-30/../../folio.db")


# --- Cliente de Instagram ---------------------------------------------------------

class Graph:
    """graph.instagram.com simulado: contenedores, estados, carrusel, publicación y permalink."""

    def __init__(self, error=None, estados=("IN_PROGRESS", "FINISHED")):
        self.error, self.estados = error, list(estados)
        self.peticiones: list[httpx.Request] = []
        self.n = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.peticiones.append(req)
        if self.error:
            return self.error
        ruta = req.url.path.removeprefix("/v26.0/")
        datos = dict(httpx.QueryParams(req.content.decode())) if req.method == "POST" else dict(req.url.params)
        assert datos["access_token"] == TOKEN
        if ruta == "me":
            return httpx.Response(200, json={"user_id": "1789", "username": "folio", "account_type": "BUSINESS"})
        if ruta == "1789/content_publishing_limit":
            return httpx.Response(200, json={"data": [{"quota_usage": 3, "config": {"quota_total": 100}}]})
        if ruta == "1789/media":
            self.n += 1
            return httpx.Response(200, json={"id": f"c{self.n}"})
        if ruta == "1789/media_publish":
            return httpx.Response(200, json={"id": "m1"})
        if datos.get("fields") == "status_code":
            estado = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
            return httpx.Response(200, json={"status_code": estado})
        if ruta == "m1":
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/abc/"})
        return httpx.Response(404, json={"error": {"message": "?"}})

    def ig(self):
        return Instagram(TOKEN, cliente=httpx.Client(transport=httpx.MockTransport(self)))

    def posts(self):
        return [(r.url.path, dict(httpx.QueryParams(r.content.decode()))) for r in self.peticiones if r.method == "POST"]


def test_cuenta_y_limite():
    g = Graph()
    ig = g.ig()
    assert ig.cuenta()["username"] == "folio" and ig.usuario == "1789"
    assert ig.limite() == (3, 100)


def test_publica_un_carrusel_con_la_portada_en_video():
    g = Graph()
    medios = [("video", "https://f/01.mp4"), ("imagen", "https://f/02.jpg"), ("imagen", "https://f/03.jpg")]
    assert g.ig().publicar_carrusel(medios, "Pie con *La peste*") == {"id": "m1", "permalink": "https://www.instagram.com/p/abc/"}
    posts = g.posts()
    assert posts[0][1]["media_type"] == "VIDEO" and posts[0][1]["video_url"] == "https://f/01.mp4"
    assert posts[0][1]["is_carousel_item"] == "true" and posts[1][1]["image_url"] == "https://f/02.jpg"
    carrusel = posts[3][1]
    assert carrusel["media_type"] == "CAROUSEL" and carrusel["children"] == "c1,c2,c3" and carrusel["caption"] == "Pie con *La peste*"
    assert posts[4][0].endswith("/media_publish") and posts[4][1]["creation_id"] == "c4"


@pytest.mark.parametrize("respuesta, bloqueo, texto", [
    (httpx.Response(403, json={"error": {"message": "nope"}}), True, "403"),
    (httpx.Response(429, text="slow down"), True, "429"),
    (httpx.Response(400, json={"error": {"message": "limit", "code": 4}}), True, "código 4"),
    (httpx.Response(400, json={"error": {"message": f"bad {TOKEN}", "code": 190}}), True, "caducado"),
    (httpx.Response(400, json={"error": {"message": "image too big", "code": 100}}), False, "image too big"),
])
def test_errores_paran_sin_reintentar_y_sin_el_token(respuesta, bloqueo, texto):
    g = Graph(error=respuesta)
    with pytest.raises(ErrorInstagram) as exc:
        g.ig().cuenta()
    assert exc.value.bloqueo is bloqueo and texto in str(exc.value)
    assert TOKEN not in str(exc.value) and len(g.peticiones) == 1


def test_contenedor_con_error_o_que_no_termina(monkeypatch):
    with pytest.raises(ErrorInstagram, match="ERROR"):
        Graph(estados=["ERROR"]).ig().publicar_carrusel([("imagen", "u1"), ("imagen", "u2")], "pie")
    ig = Graph(estados=["IN_PROGRESS"]).ig()
    ig.espera_max_s = 0
    with pytest.raises(ErrorInstagram, match="no terminó"):
        ig.publicar_carrusel([("imagen", "u1"), ("imagen", "u2")], "pie")


def test_limites_del_carrusel_y_del_pie():
    g = Graph()
    with pytest.raises(ErrorInstagram, match="de 2 a 20"):
        g.ig().publicar_carrusel([("imagen", "u")], "pie")
    with pytest.raises(ErrorInstagram, match="2200"):
        g.ig().publicar_carrusel([("imagen", "u1"), ("imagen", "u2")], "x" * 2201)
    assert g.peticiones == []
    with pytest.raises(ErrorInstagram, match="INSTAGRAM_TOKEN"):
        Instagram("")


# --- Pie, ruta pública y comando -----------------------------------------------------

def test_pie_con_los_creditos():
    from datos import ELECCION, LIBRO, guion_valido
    from folio.modelos import Arte, Pieza
    from folio.publicacion.preparar import pie_publicacion
    p = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="aprobada", historia_id="h1", eleccion=ELECCION,
              n_medios=3, libros=[LIBRO], guion=guion_valido(),
              arte=Arte(tono="sereno", recurso="foto", retrato="Ana · CC BY-SA 4.0 · Wikimedia Commons"))
    pie = pie_publicacion(p)
    assert pie.startswith(p.guion.pie_instagram) and pie.endswith(
        "\n\nRetrato: Ana · CC BY-SA 4.0 · Wikimedia Commons (la portada se publica con la misma licencia, CC BY-SA).")


def test_ruta_publica_solo_con_firma(cfg):
    from fastapi.testclient import TestClient
    from folio.almacen import Almacen
    from folio_api.main import crear_app
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    cfg.clave_enlaces = "clave-larga"
    archivo = cfg.dir_informes / "2026-10-30" / "publicar" / "2026-10-30-1" / "02.jpg"
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"\xff\xd8jpeg")
    c = TestClient(crear_app(cfg, Almacen(cfg.ruta_db), importar=False))
    url = enlaces.firmar("http://testserver", "clave-larga", RUTA)
    r = c.get(url)
    assert r.status_code == 200 and r.content == b"\xff\xd8jpeg" and r.headers["content-type"] == "image/jpeg"
    assert c.get(url.replace(RUTA, "2026-10-30/2026-10-30-1/03.jpg")).status_code == 404     # firma de otro archivo
    assert c.get(enlaces.firmar("http://testserver", "otra", RUTA)).status_code == 404
    assert c.get(enlaces.firmar("http://testserver", "clave-larga", RUTA, segundos=-10)).status_code == 404


def test_publicar_solo_aprobadas_y_sin_confirmar_no_publica(cfg, monkeypatch, tmp_path):
    from typer.testing import CliRunner
    from datos import ELECCION, LIBRO, guion_valido
    from folio import cli, config
    from folio.almacen import Almacen
    from folio.modelos import InformeDiario, Pieza, SeleccionJefe
    from folio.publicacion import preparar as prep
    from datetime import datetime, timezone
    pieza = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1", eleccion=ELECCION,
                  n_medios=3, libros=[LIBRO], guion=guion_valido())
    almacen = Almacen(cfg.ruta_db)
    eid = almacen.registrar(InformeDiario(fecha="2026-10-30", generado_en=datetime(2026, 10, 30, tzinfo=timezone.utc),
                                          stats={}, top_historias=[], seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]),
                                          piezas=[pieza]))
    cfg.instagram_token, cfg.url_publica, cfg.clave_enlaces = TOKEN, "https://folio.example", "clave"
    monkeypatch.setattr(config, "cargar", lambda: cfg)
    r = CliRunner().invoke(cli.app, ["instagram", "publicar", "2026-10-30-1"])
    assert r.exit_code == 1 and "solo se publican las aprobadas" in r.output

    almacen.cambiar_estado(eid, "2026-10-30-1", "aprobada")
    carpeta = tmp_path / "publicar"
    monkeypatch.setattr(prep, "preparar", lambda cfg, p, con_video=True: prep.Preparada(
        carpeta, [("video", "01.mp4"), ("imagen", "02.jpg")], prep.pie_publicacion(p), []))
    g = Graph()
    monkeypatch.setattr(ig_mod, "Instagram", lambda token, usuario=None: Instagram(
        token, usuario, cliente=httpx.Client(transport=httpx.MockTransport(g))))
    r = CliRunner().invoke(cli.app, ["instagram", "publicar", "2026-10-30-1"])
    assert r.exit_code == 0 and "no se ha publicado nada" in r.output and "@folio" in r.output
    assert g.posts() == [] and almacen.pieza(eid, "2026-10-30-1")[0].estado == "aprobada"

    carpeta.mkdir()
    r = CliRunner().invoke(cli.app, ["instagram", "publicar", "2026-10-30-1", "--confirmar"])
    assert r.exit_code == 0 and "https://www.instagram.com/p/abc/" in r.output
    assert almacen.pieza(eid, "2026-10-30-1")[0].estado == "publicada"
    urls = [d.get("video_url") or d.get("image_url") for _, d in g.posts()[:2]]
    assert all(u.startswith("https://folio.example/api/publico/") for u in urls) and urls[0].endswith("/2026-10-30-1/01.mp4")
    assert TOKEN not in r.output
