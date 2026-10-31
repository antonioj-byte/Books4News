from io import BytesIO

import httpx
import pytest
from PIL import Image

from folio import arte, config
from folio.imagenes import libres, retrato_generado as rg, retratos
from folio.modelos import Arte, Pieza

from datos import ELECCION, LIBRO, guion_valido

CLAVE = "clave-de-prueba-123"
PIEZA = "2026-10-30-1"


def _jpeg(color=(200, 120, 90), tam=(300, 400)) -> bytes:
    salida = BytesIO()
    Image.new("RGB", tam, color).save(salida, format="JPEG")
    return salida.getvalue()


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    monkeypatch.setattr(rg, "ESPERA_S", 0)
    rg.reiniciar()
    yield
    rg.reiniciar()


@pytest.fixture
def cfg_rg(cfg):
    cfg.magnific_api_key = CLAVE
    return cfg


def _fijar_foto(cfg, pieza_id=PIEZA, foto=None) -> libres.ImagenLibre:
    """Un retrato de Commons ya fijado para la pieza, como lo deja folio.imagenes.retratos."""
    dir_fecha = cfg.dir_cache("2026-10-30")
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pieza_id}-retrato.jpg").write_bytes(foto or _jpeg())
    img = libres.ImagenLibre(archivo="commons:File:Ana.jpg", pagina="", url="", ancho=300, alto=400,
                             licencia="CC BY-SA 4.0", licencia_url=None, autor="Ana Pérez", descripcion="",
                             libre=True, motivo="", local=f"{pieza_id}-retrato.jpg")
    libres.guardar_metadatos(img, f"{pieza_id}-retrato", dir_fecha)
    return img


class Servidor:
    """La API de Magnific simulada: POST → tarea, GET → estados, y el CDN con la imagen."""

    def __init__(self, estados=("IN_PROGRESS", "COMPLETED"), post=(), imagen=None):
        self.estados, self.post, self.imagen = list(estados), list(post), imagen or _jpeg((30, 30, 30))
        self.peticiones: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.peticiones.append(req)
        if req.url.host == "cdn.example":
            assert "x-magnific-api-key" not in req.headers          # la clave no sale de la API
            return httpx.Response(200, content=self.imagen)
        assert req.headers["x-magnific-api-key"] == CLAVE
        if req.method == "POST":
            if self.post:
                return self.post.pop(0)
            return httpx.Response(200, json={"data": {"task_id": "t1", "status": "CREATED", "generated": []}})
        estado = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        generadas = ["https://cdn.example/r.jpg"] if estado == "COMPLETED" else []
        return httpx.Response(200, json={"data": {"task_id": "t1", "status": estado, "generated": generadas,
                                                  "error": "fallo del modelo" if estado == "FAILED" else None}})

    def cliente(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def test_prompt_de_cada_estilo(cfg):
    for estilo in rg.ESTILOS:
        texto = rg.prompt(cfg, estilo)
        assert "exact likeness" in texto and "No text" in texto
    assert "low-poly" in rg.prompt(cfg, "low_poly") and "cubes" in rg.prompt(cfg, "voxel")
    assert "early-2000s" in rg.prompt(cfg, "render_2000")
    with pytest.raises(ValueError, match="## pixel"):
        rg.prompt(cfg, "pixel")


def test_genera_el_retrato_y_guarda_el_original_al_lado(cfg_rg):
    _fijar_foto(cfg_rg)
    srv = Servidor()
    img = rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "low_poly", srv.cliente())
    carpeta = libres.dir_imagenes(cfg_rg.dir_cache("2026-10-30"))
    assert img.local == f"{PIEZA}-retrato.jpg" and (carpeta / img.local).read_bytes() == srv.imagen
    assert (carpeta / f"{PIEZA}-retrato-original.jpg").read_bytes() == _jpeg()
    assert img.generado["estilo"] == "low_poly" and img.generado["task_id"] == "t1"
    assert img.credito == "Ana Pérez · CC BY-SA 4.0 (obra derivada) · Wikimedia Commons; retrato low-poly generado con IA (Magnific)"
    assert libres.de_pieza(f"{PIEZA}-retrato", cfg_rg.dir_cache("2026-10-30")).generado   # lo que lee el render
    post = srv.peticiones[0]
    assert post.url.path == rg.RUTA and b'"aspect_ratio": "traditional_3_4"' in post.content.replace(b'":"', b'": "')


def test_otro_estilo_parte_del_original_y_la_cache_no_vuelve_a_pagar(cfg_rg):
    _fijar_foto(cfg_rg)
    dir_fecha = cfg_rg.dir_cache("2026-10-30")
    rg.aplicar(cfg_rg, PIEZA, dir_fecha, "low_poly", Servidor().cliente())
    srv = Servidor()
    rg.aplicar(cfg_rg, PIEZA, dir_fecha, "voxel", srv.cliente())
    assert b"cubes" in srv.peticiones[0].content                        # pidió el vóxel sobre la foto
    sin_red = Servidor(post=[httpx.Response(500)])
    img = rg.aplicar(cfg_rg, PIEZA, dir_fecha, "low_poly", sin_red.cliente())
    assert sin_red.peticiones == [] and img.generado["desde_cache"]


def test_dithering_se_fuerza_a_1_bit(cfg_rg):
    _fijar_foto(cfg_rg)
    srv = Servidor(imagen=_jpeg((40, 60, 200)))                        # el modelo dejó color
    img = rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "dithering", srv.cliente())
    ruta = libres.dir_imagenes(cfg_rg.dir_cache("2026-10-30")) / img.local
    assert ruta.suffix == ".png"
    with Image.open(ruta) as im:
        assert im.mode == "1"


@pytest.mark.parametrize("estados, mensaje", [(["FAILED"], "falló"), (["IN_PROGRESS"], "no terminó")])
def test_tarea_fallida_o_eterna_deja_la_foto(cfg_rg, estados, mensaje):
    _fijar_foto(cfg_rg)
    if estados == ["IN_PROGRESS"]:
        cfg_rg.pipeline.arte.retrato_generado.espera_max_s = 0
    with pytest.raises(rg.ErrorMagnific, match=mensaje):
        rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "voxel", Servidor(estados).cliente())
    carpeta = libres.dir_imagenes(cfg_rg.dir_cache("2026-10-30"))
    assert (carpeta / f"{PIEZA}-retrato.jpg").read_bytes() == _jpeg()
    assert not list(carpeta.glob("*-original.*"))


@pytest.mark.parametrize("codigo", [401, 403, 429])
def test_bloqueo_no_reintenta_y_desactiva_la_ejecucion(cfg_rg, codigo):
    _fijar_foto(cfg_rg)
    srv = Servidor(post=[httpx.Response(codigo, text=f"bad key {CLAVE}")])
    with pytest.raises(rg.ErrorMagnific) as exc:
        rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "voxel", srv.cliente())
    assert exc.value.bloqueo and len(srv.peticiones) == 1
    assert CLAVE not in str(exc.value) and "***" in str(exc.value)
    otro = Servidor()
    with pytest.raises(rg.ErrorMagnific, match="desactivada"):
        rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "voxel", otro.cliente())
    assert otro.peticiones == []


def test_503_se_reintenta_una_sola_vez(cfg_rg):
    _fijar_foto(cfg_rg)
    srv = Servidor(post=[httpx.Response(503)])
    rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "voxel", srv.cliente())
    assert [r.method for r in srv.peticiones][:2] == ["POST", "POST"]
    rg.reiniciar()
    _fijar_foto(cfg_rg, "2026-10-30-2", _jpeg((90, 90, 200)))      # otra foto: no sale de la caché
    srv = Servidor(post=[httpx.Response(503), httpx.Response(503)])
    with pytest.raises(rg.ErrorMagnific, match="503") as exc:
        rg.aplicar(cfg_rg, "2026-10-30-2", cfg_rg.dir_cache("2026-10-30"), "voxel", srv.cliente())
    assert not exc.value.bloqueo and len(srv.peticiones) == 2


def test_sin_clave_o_sin_foto_no_se_llama(cfg_rg):
    srv = Servidor()
    with pytest.raises(ValueError, match="no tiene retrato"):
        rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "voxel", srv.cliente())
    _fijar_foto(cfg_rg)
    cfg_rg.magnific_api_key = None
    with pytest.raises(rg.ErrorMagnific, match="MAGNIFIC_API_KEY"):
        rg.aplicar(cfg_rg, PIEZA, cfg_rg.dir_cache("2026-10-30"), "voxel", srv.cliente())
    assert srv.peticiones == []


def test_estilo_del_dia_alterna_y_respeta_el_tope(cfg_rg):
    dir_fecha = cfg_rg.dir_cache("2026-10-30")
    estilos = cfg_rg.pipeline.arte.retrato_generado.estilos
    for i in (1, 2):
        _fijar_foto(cfg_rg, f"2026-10-30-{i}")
    primero, _ = rg.estilo_del_dia(cfg_rg, "2026-10-30-1", dir_fecha)
    siguiente = estilos[(estilos.index(primero) + 1) % len(estilos)]
    rg.aplicar(cfg_rg, "2026-10-30-1", dir_fecha, primero, Servidor().cliente())
    assert rg.estilo_del_dia(cfg_rg, "2026-10-30-2", dir_fecha) == (siguiente, 1)
    assert rg.estilo_del_dia(cfg_rg, "2026-10-30-1", dir_fecha) == (primero, 0)   # no se cuenta a sí misma
    cfg_rg.pipeline.arte.retrato_generado.max_por_dia = 1
    assert rg.estilo_del_dia(cfg_rg, "2026-10-30-2", dir_fecha) == (None, 1)


def test_el_primer_retrato_del_dia_cambia_de_estilo_cada_dia(cfg_rg):
    """Con la mesa del día solo se escribe sola la primera pieza: si la rotación empezara cada día por el
    mismo estilo, el retrato de la mañana saldría siempre igual (salía siempre en low-poly)."""
    estilos = cfg_rg.pipeline.arte.retrato_generado.estilos
    primeros = [rg.estilo_del_dia(cfg_rg, f"2026-11-0{d}-1", cfg_rg.dir_cache(f"2026-11-0{d}"))[0]
                for d in range(1, len(estilos) + 1)]
    assert sorted(primeros) == sorted(estilos)


# --- En la etapa de arte ---------------------------------------------------------

def _pieza():
    return Pieza(id=PIEZA, fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())


@pytest.fixture
def con_foto(cfg_rg, monkeypatch):
    def buscar_y_fijar(autor, pieza_id, dir_fecha, permitir_sa):
        return _fijar_foto(cfg_rg, pieza_id), ""
    monkeypatch.setattr(retratos, "buscar_y_fijar", buscar_y_fijar)
    return cfg_rg


def _retrato_y_estilo(cfg, pieza, a):
    """Lo que hace dirigir() cuando la portada es la foto del autor y toca retrato generado."""
    img = arte._retrato(cfg, pieza, a, cfg.dir_cache("2026-10-30"))
    if img and cfg.pipeline.arte.retrato_generado.activo:
        arte._retrato_generado(cfg, pieza, a, cfg.dir_cache("2026-10-30"))


def test_arte_usa_el_retrato_generado_y_lo_manda_a_revision(con_foto, monkeypatch):
    monkeypatch.setattr(rg, "generar", lambda *a, **k: (_jpeg((10, 10, 10)), "t9", 20.0))
    con_foto.pipeline.arte.retrato_generado.activo = True
    pieza, a = _pieza(), Arte(tono="sereno", recurso="foto")
    for _ in range(2):                                                  # relanzar no duplica el aviso
        _retrato_y_estilo(con_foto, pieza, a)
    assert "generado con IA (Magnific)" in a.retrato
    assert pieza.revision_humana.count(arte.AVISO_RETRATO_GENERADO) == 1


def test_arte_sin_generar_si_esta_desactivado_o_falla(con_foto, monkeypatch):
    llamadas = []

    def falla(*a, **k):
        llamadas.append(1)
        raise rg.ErrorMagnific("La tarea t1 falló")
    monkeypatch.setattr(rg, "generar", falla)
    con_foto.pipeline.arte.retrato_generado.activo = False
    pieza, a = _pieza(), Arte(tono="sereno", recurso="foto")
    _retrato_y_estilo(con_foto, pieza, a)
    assert llamadas == [] and a.retrato == "Ana Pérez · CC BY-SA 4.0 · Wikimedia Commons"
    con_foto.pipeline.arte.retrato_generado.activo = True
    a = Arte(tono="sereno", recurso="foto")
    _retrato_y_estilo(con_foto, pieza, a)
    assert llamadas == [1] and a.retrato == "Ana Pérez · CC BY-SA 4.0 · Wikimedia Commons"
    assert any("se usa la foto" in x for x in a.avisos) and arte.AVISO_RETRATO_GENERADO not in pieza.revision_humana


# --- Configuración -----------------------------------------------------------------

def test_configuracion_y_perfil_dev(cfg):
    assert cfg.pipeline.arte.retrato_generado.activo and cfg.pipeline.arte.retrato_generado.max_por_dia == 3
    assert cfg.pipeline.arte.retrato_generado.estilos == ["low_poly", "voxel", "render_2000"]     # los tres en 3D
    assert set(config.RetratoGenerado().estilos) == set(rg.ESTILOS)                     # cada estilo tiene nombre
    with pytest.raises(ValueError):
        config.RetratoGenerado(estilos=["pixel"])
    with pytest.raises(ValueError):
        config.RetratoGenerado(precio=1)
    cfg.pipeline.arte.retrato_generado.activo = True
    assert not config.perfil_dev(cfg).pipeline.arte.retrato_generado.activo
