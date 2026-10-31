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
