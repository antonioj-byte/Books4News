"""El cliente único de Magnific (4/11): espera, descarga, caché, gasto y bloqueos en un solo sitio."""
from io import BytesIO

import httpx
import pytest
from PIL import Image

from folio.imagenes import magnific
from folio.imagenes import retrato_generado as rg


def _png():
    b = BytesIO()
    Image.new("RGB", (40, 30), (200, 10, 80)).save(b, "PNG")
    return b.getvalue()


class Magnific:
    """Responde como Magnific: la tarea va IN_PROGRESS → COMPLETED y la imagen se descarga del CDN."""
    def __init__(self, codigo_post=200, estados=("IN_PROGRESS", "COMPLETED")):
        self.codigo_post, self.estados, self.peticiones = codigo_post, list(estados), []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.peticiones.append((req.method, req.url.path))
        if req.url.host == "cdn.ejemplo":
            return httpx.Response(200, content=_png())
        assert req.headers["x-magnific-api-key"] == "clave-secreta"
        if req.method == "POST":
            if self.codigo_post != 200:
                return httpx.Response(self.codigo_post, text="límite clave-secreta")
            return httpx.Response(200, json={"data": {"task_id": "t1", "status": self.estados.pop(0)}})
        estado = self.estados.pop(0)
        return httpx.Response(200, json={"data": {"task_id": "t1", "status": estado,
                                                  "generated": ["https://cdn.ejemplo/i.png"] if estado == "COMPLETED" else []}})

    def cliente(self):
        return httpx.Client(transport=httpx.MockTransport(self))


@pytest.fixture
def cfg_m(cfg, monkeypatch):
    monkeypatch.setattr(rg, "ESPERA_S", 0)
    cfg.magnific_api_key = "clave-secreta"
    rg.reiniciar()                  # el bloqueo de Magnific dura la ejecución: cada test empieza sin él
    yield cfg
    rg.reiniciar()


def test_pide_espera_descarga_guarda_y_apunta_una_vez(cfg_m, monkeypatch):
    apuntes = []
    monkeypatch.setattr(magnific.gastos, "imagen_magnific", lambda cfg, *a, **k: apuntes.append((a, k)))
    m = Magnific()
    cache = cfg_m.dir_cache("x").parent / "ilustraciones" / "prueba.jpg"
    kw = dict(ruta=magnific.FLUX_2_PRO, cuerpo={"prompt": "p"}, cache=cache, pieza_id="2026-11-04-1", concepto="prueba",
              modelo="Flux 2 Pro", procesar=magnific.rgb)
    assert magnific.imagen(cfg_m, cliente=m.cliente(), **kw) == cache
    with Image.open(cache) as im:
        assert im.format == "JPEG" and im.size == (40, 30)
    assert len(apuntes) == 1 and [p for p in m.peticiones if p[0] == "GET"]       # esperó a que terminara
    # La misma petición, de la caché: ni se llama ni se paga otra vez
    otra = Magnific()
    magnific.imagen(cfg_m, cliente=otra.cliente(), **kw)
    assert otra.peticiones == [] and len(apuntes) == 1


@pytest.mark.parametrize("codigo", [401, 403, 429])
def test_un_bloqueo_no_se_reintenta_y_desactiva_magnific(cfg_m, codigo):
    m = Magnific(codigo_post=codigo)
    with pytest.raises(magnific.ErrorMagnific) as e:
        magnific.pedir("clave-secreta", magnific.FLUX_2_PRO, {"prompt": "p"}, 10, m.cliente())
    assert e.value.bloqueo and "clave-secreta" not in str(e.value) and len(m.peticiones) == 1
    assert rg.bloqueado()
    with pytest.raises(magnific.ErrorMagnific, match="bloqueado"):
        magnific.comprobar(cfg_m)


def test_tarea_fallida_o_sin_clave(cfg_m):
    with pytest.raises(magnific.ErrorMagnific, match="falló"):
        magnific.pedir("clave-secreta", magnific.FLUX_2_PRO, {"prompt": "p"}, 10, Magnific(estados=("IN_PROGRESS", "FAILED")).cliente())
    assert not rg.bloqueado()                       # un fallo de la tarea no es un bloqueo
    cfg_m.magnific_api_key = None
    with pytest.raises(magnific.ErrorMagnific, match="MAGNIFIC_API_KEY"):
        magnific.comprobar(cfg_m)
