"""Encuadre de los retratos en la cara (2/11, regla de la Memoria: «solo queda la frente»). Sin red ni gasto."""

from io import BytesIO

from PIL import Image

from folio.imagenes import cara, libres


class LLMCara:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.pasos = []

    def estructurado(self, paso, mensajes, esquema, **k):
        self.pasos.append(paso)
        assert mensajes[0]["content"][0]["type"] == "image"
        return self.respuesta, []


def _retrato(cfg, clave="2026-11-01-1-retrato"):
    d = cfg.dir_cache("2026-11-01")
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    b = BytesIO()
    Image.new("RGB", (800, 1200)).save(b, "JPEG")
    (libres.dir_imagenes(d) / f"{clave}.jpg").write_bytes(b.getvalue())
    img = libres.ImagenLibre(archivo="commons:File:x.jpg", pagina="", url="", ancho=800, alto=1200, licencia="CC BY",
                             licencia_url=None, autor="A", descripcion="", libre=True, motivo="", local=f"{clave}.jpg",
                             fuente="", enfoque=(50, 28), persona="Steven Pinker")
    libres.guardar_metadatos(img, clave, d)
    return d


def test_el_retrato_se_encuadra_en_el_centro_de_la_cara(cfg):
    d = _retrato(cfg)
    llm = LLMCara(cara.CaraLLM(hay_cara=True, x0=40, y0=50, x1=60, y1=70))
    assert cara.encuadrar(llm, cfg, "2026-11-01-1-retrato", d) is None
    img = libres.de_pieza("2026-11-01-1-retrato", d)
    assert tuple(img.enfoque) == (50, 60) and tuple(img.cara) == (40, 50, 60, 70)


def test_sin_cara_se_queda_el_encuadre(cfg):
    d = _retrato(cfg)
    aviso = cara.encuadrar(LLMCara(cara.CaraLLM(hay_cara=False, x0=0, y0=0, x1=0, y1=0)), cfg, "2026-11-01-1-retrato", d)
    assert aviso and tuple(libres.de_pieza("2026-11-01-1-retrato", d).enfoque) == (50, 28)
    assert cara.encuadrar(None, cfg, "2026-11-01-1-retrato", d) is None        # sin modelo, nada


def test_la_noticia_no_se_queda_sin_imagen():
    """2/11, regla de la Memoria: la diapositiva de la noticia lleva foto o ilustración."""
    from folio import arte as direccion
    from folio.modelos import Arte
    assert direccion.noticia_tiene_imagen(Arte(tono="sereno", recurso="ilustracion", portada="panorama", imagen="x"), False)
    assert direccion.noticia_tiene_imagen(Arte(tono="sereno", recurso="foto", registro="foto_autor", imagen="x"), True)
    assert not direccion.noticia_tiene_imagen(Arte(tono="sereno", recurso="foto", registro="archivo", imagen="x"), False)
    assert direccion.noticia_tiene_imagen(Arte(tono="sereno", recurso="foto", registro="archivo", imagen="x", imagen_noticia="y"), False)
    assert not direccion.noticia_tiene_imagen(Arte(tono="sereno", recurso="foto", registro="foto_autor"), True)


def test_titulares_alternativos_se_limpian():
    """2/11, regla de la Memoria: cinco titulares para elegir; fuera los largos, las preguntas y el repetido."""
    from folio.guion import _con_alternativos
    from datos import guion_valido
    g = guion_valido()
    g.titulares_alternativos = [g.diapositivas[0].texto, "Uno corto", "¿Y esto?", " ".join(["palabra"] * 13),
                                "Dos", "Tres", "Cuatro", "Cinco", "Seis"]
    assert _con_alternativos(g).titulares_alternativos == ["Uno corto", "Dos", "Tres", "Cuatro", "Cinco"]
