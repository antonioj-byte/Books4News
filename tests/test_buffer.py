"""Programación en Buffer (folio.publicacion.buffer), con la API simulada: sin red ni gasto."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import typer

from folio.cli import hora_de_publicacion
from folio.publicacion import enlaces
from folio.publicacion.buffer import Buffer, ErrorBuffer

CLAVE = "buffer-clave-secreta-123"
MADRID = ZoneInfo("Europe/Madrid")
MEDIOS = [("video", "https://f.example/01.mp4"), ("imagen", "https://f.example/02.jpg"), ("imagen", "https://f.example/03.jpg")]


class Api:
    """api.buffer.com simulada: cuenta, canales y createPost."""

    def __init__(self, estado=200, errores=None, canales=None, crear=None):
        self.estado, self.errores = estado, errores
        self.canales = canales if canales is not None else [
            {"id": "c-ig", "name": "folio", "service": "instagram"}, {"id": "c-li", "name": "Folio", "service": "linkedin"}]
        self.crear = crear or {"post": {"id": "p1", "dueAt": "2026-11-02T08:30:00.000Z", "assets": []}}
        self.peticiones: list[dict] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == f"Bearer {CLAVE}"
        cuerpo = json.loads(req.content)
        self.peticiones.append(cuerpo)
        if self.estado != 200 or self.errores:
            return httpx.Response(self.estado, json={"errors": self.errores or [{"message": f"fallo con {CLAVE}"}]})
        q = cuerpo["query"]
        if "organizations" in q:
            datos = {"account": {"id": "a", "organizations": [{"id": "o1", "name": "Folio"}]}}
        elif "channels" in q:
            datos = {"channels": self.canales}
        elif "__type" in q:
            datos = {"__type": {"enumValues": [{"name": "post"}, {"name": "story"}, {"name": "reel"}]}}
        else:
            datos = {"createPost": self.crear}
        return httpx.Response(200, json={"data": datos})


def _buffer(api: Api) -> Buffer:
    return Buffer(CLAVE, httpx.Client(transport=httpx.MockTransport(api)))


def test_programa_el_carrusel_a_una_hora_en_utc():
    api = Api()
    b = _buffer(api)
    canal = b.canal_instagram()
    post = b.programar(canal["id"], "Pie con *libro*.", MEDIOS, datetime(2026, 11, 2, 9, 30, tzinfo=MADRID))
    entrada = api.peticiones[-1]["variables"]["input"]
    assert post["id"] == "p1" and canal["id"] == "c-ig"
    assert entrada["mode"] == "customScheduled" and entrada["dueAt"] == "2026-11-02T08:30:00Z"      # 9:30 en Madrid
    assert entrada["schedulingType"] == "automatic" and entrada["metadata"]["instagram"]["type"] == "post"
    assert entrada["assets"] == [{"video": {"url": MEDIOS[0][1]}}, {"image": {"url": MEDIOS[1][1]}}, {"image": {"url": MEDIOS[2][1]}}]


def test_sin_hora_va_a_la_cola_y_comprueba_el_carrusel():
    assert Buffer.entrada("c", "pie", MEDIOS, None)["mode"] == "addToQueue"
    assert "saveToDraft" not in Buffer.entrada("c", "pie", MEDIOS, None)
    assert Buffer.entrada("c", "pie", MEDIOS, None, borrador=True)["saveToDraft"] is True
    with pytest.raises(ErrorBuffer, match="de 2 a 10"):
        Buffer.entrada("c", "pie", MEDIOS[:1], None)
    with pytest.raises(ErrorBuffer, match="2200"):
        Buffer.entrada("c", "x" * 2201, MEDIOS, None)
    with pytest.raises(ErrorBuffer, match="zona"):
        Buffer.entrada("c", "pie", MEDIOS, datetime(2026, 11, 2, 9, 30))


def test_bloqueos_paran_y_la_clave_no_sale_en_los_errores():
    for estado in (401, 403, 429):
        with pytest.raises(ErrorBuffer) as e:
            _buffer(Api(estado=estado)).organizaciones()
        assert e.value.bloqueo and CLAVE not in str(e.value)
    with pytest.raises(ErrorBuffer) as e:
        _buffer(Api(errores=[{"message": "Unknown field"}])).organizaciones()
    assert not e.value.bloqueo
    with pytest.raises(ErrorBuffer, match="no programó.*Media URL"):
        _buffer(Api(crear={"message": "Media URL not reachable"})).programar("c-ig", "pie", MEDIOS, None)
    with pytest.raises(ErrorBuffer, match="BUFFER_API_KEY"):
        Buffer(None)


def test_el_canal_de_instagram_tiene_que_ser_uno():
    assert _buffer(Api()).canal_instagram("c-li")["service"] == "linkedin"      # BUFFER_CHANNEL_ID manda
    with pytest.raises(ErrorBuffer, match="Hay 0"):
        _buffer(Api(canales=[])).canal_instagram()
    dos = [{"id": "a", "name": "x", "service": "instagram"}, {"id": "b", "name": "y", "service": "instagram"}]
    with pytest.raises(ErrorBuffer, match="BUFFER_CHANNEL_ID"):
        _buffer(Api(canales=dos)).canal_instagram()
    assert _buffer(Api()).valores("PostType") == ["post", "story", "reel"]


def test_hora_de_publicacion_en_madrid():
    ahora = datetime(2026, 11, 1, 10, 0, tzinfo=MADRID)
    assert hora_de_publicacion("09:30", "Europe/Madrid", ahora) == datetime(2026, 11, 2, 9, 30, tzinfo=MADRID)   # ya pasó hoy
    assert hora_de_publicacion("18:00", "Europe/Madrid", ahora) == datetime(2026, 11, 1, 18, 0, tzinfo=MADRID)
    assert hora_de_publicacion("2026-11-05 08:15", "Europe/Madrid", ahora) == datetime(2026, 11, 5, 8, 15, tzinfo=MADRID)
    with pytest.raises(typer.BadParameter):
        hora_de_publicacion("mañana", "Europe/Madrid", ahora)


def test_los_archivos_de_buffer_tienen_enlace_firmado_de_larga_duracion():
    ruta = "2026-10-30/2026-10-30-1-buffer/01.mp4"
    url = enlaces.firmar("https://folio.example", "clave", ruta, 5 * 86400, ahora=1000)
    caduca, firma, resto = url.split("/api/publico/")[1].split("/", 2)
    assert resto == ruta and enlaces.valida("clave", int(caduca), firma, ruta, ahora=1000 + 4 * 86400)


def test_el_boton_de_la_web_programa_la_pieza_aprobada(cfg, monkeypatch):
    """POST /buffer: solo aprobadas, con la hora de Madrid, y no dos veces sin «reemplazar»."""
    from fastapi.testclient import TestClient
    from folio import informe
    from folio.almacen import Almacen
    from folio.modelos import InformeDiario, Pieza, SeleccionJefe
    from folio.publicacion import programar as prog
    from folio.publicacion.preparar import Preparada
    from folio_api.main import crear_app
    from datos import ELECCION, LIBRO, guion_valido

    p = Pieza(id="2026-11-02-1", fecha="2026-11-02", estado="propuesta", historia_id="h1", eleccion=ELECCION,
              n_medios=3, libros=[LIBRO], guion=guion_valido())
    inf = InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=MADRID), stats={}, top_historias=[],
                        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]), piezas=[p], coste_total_usd=0)
    informe.escribir(inf, cfg.dir_informes / "2026-11-02")
    almacen = Almacen(cfg.ruta_db)
    almacen.importar_informes(cfg.dir_informes)
    eid = almacen.ultima_ejecucion("2026-11-02")
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    cfg.buffer_clave, cfg.url_publica, cfg.clave_enlaces = "clave", "https://folio.example", "firma"

    def preparar(cfg_, pieza, con_video=True, videos_de=None):
        carpeta = cfg_.dir_informes / pieza.fecha / "publicar" / pieza.id
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "01.mp4").write_bytes(b"v")
        (carpeta / "02.jpg").write_bytes(b"j")
        return Preparada(carpeta=carpeta, medios=[("video", "01.mp4"), ("image", "02.jpg")], pie="Pie con créditos", avisos=[])
    enviados = []

    class BufferFalso:
        def __init__(self, clave, cliente=None): pass
        def canal_instagram(self, canal=None): return {"id": "c1", "name": "folio_editorial"}
        def programar(self, canal, pie, medios, cuando, borrador):
            enviados.append((pie, medios, cuando, borrador))
            return {"id": "post1", "dueAt": cuando.isoformat() if cuando else None}
    monkeypatch.setattr(prog, "preparar", preparar)
    monkeypatch.setattr(prog, "Buffer", BufferFalso)
    c = TestClient(crear_app(cfg, almacen))
    url = f"/api/ejecuciones/{eid}/piezas/2026-11-02-1/buffer"
    assert c.get(url).json()["disponible"] and c.get(url).json()["programada"] is None
    r = c.post(url, json={"hora": "2099-01-05 09:30", "borrador": False, "reemplazar": False})
    assert r.status_code == 409 and "aprobadas" in r.json()["detail"]                      # aún no está aprobada
    c.patch(f"/api/ejecuciones/{eid}/piezas/2026-11-02-1/estado", json={"estado": "aprobada"})
    assert c.post(url, json={"hora": "mañana"}).status_code == 422
    r = c.post(url, json={"hora": "2099-01-05 09:30", "borrador": False, "reemplazar": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "Programada en folio_editorial" in d["mensaje"] and d["programada"]["hora"].startswith("2099-01-05T09:30")
    pie, medios, cuando, borrador = enviados[0]
    assert cuando == datetime(2099, 1, 5, 9, 30, tzinfo=MADRID) and not borrador
    assert medios[0][0] == "video" and "/2026-11-02-1-buffer/01.mp4" in medios[0][1]
    # Ya programada: no se repite sin «reemplazar»
    assert c.post(url, json={"borrador": True}).status_code == 409
    r = c.post(url, json={"borrador": True, "reemplazar": True})
    assert r.status_code == 200 and r.json()["programada"]["borrador"] and len(enviados) == 2
    # Desde un borrador se programa sin borrarlo antes, con aviso (2/11: «no funciona el botón»)
    r = c.post(url, json={"hora": "2099-01-06 10:00", "borrador": False, "reemplazar": False})
    assert r.status_code == 200, r.text
    assert "borrador anterior sigue en Buffer" in r.json()["mensaje"] and len(enviados) == 3
    assert not r.json()["programada"]["borrador"]
    # Y ya programada a una hora, otra vez hace falta «reemplazar»
    assert c.post(url, json={"borrador": True}).status_code == 409
