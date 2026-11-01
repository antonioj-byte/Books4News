"""Acciones de imagen del chat de edición (folio.edicion.aplicar_imagen). Sin red ni gasto."""

from io import BytesIO

from PIL import Image

from folio import arte as direccion
from folio import edicion
from folio.edicion import AccionImagen
from folio.imagenes import editorial, libres
from folio.modelos import Arte, Pieza

from datos import ELECCION, LIBRO, guion_valido


def _accion(tipo, **k):
    datos = dict(tipo=tipo, enfoque_x=50, enfoque_y=50, composicion="", consultas=[], escena="")
    return AccionImagen(**(datos | k))


def _pieza(**arte):
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1", eleccion=ELECCION,
                 n_medios=3, libros=[LIBRO], guion=guion_valido(), arte=Arte(tono="sereno", recurso="foto", **arte))


def _fijar(cfg, clave, archivo="europeana:/1"):
    d = cfg.dir_cache("2026-10-30")
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    b = BytesIO()
    Image.new("RGB", (1200, 1500)).save(b, "JPEG")
    (libres.dir_imagenes(d) / f"{clave}.jpg").write_bytes(b.getvalue())
    libres.guardar_metadatos(libres.ImagenLibre(archivo=archivo, pagina="", url="", ancho=1200, alto=1500, licencia="CC0",
                                                licencia_url=None, autor="A", descripcion="", libre=True, motivo="",
                                                local=f"{clave}.jpg"), clave, d)


def test_encuadre_de_la_foto_del_autor_o_de_la_de_archivo(cfg):
    _fijar(cfg, "2026-10-30-1")
    _fijar(cfg, "2026-10-30-1-retrato", "commons:File:A.jpg")
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(registro="foto_autor"), _accion("encuadre", enfoque_y=25))
    assert nueva and libres.de_pieza("2026-10-30-1-retrato", cfg.dir_cache("2026-10-30")).enfoque == (50, 25)
    edicion.aplicar_imagen(None, cfg, _pieza(registro="archivo"), _accion("encuadre", enfoque_x=120, enfoque_y=-5))
    assert libres.de_pieza("2026-10-30-1", cfg.dir_cache("2026-10-30")).enfoque == (100, 0)   # dentro de 0–100


def test_composicion_y_que_imagen_va_en_la_portada(cfg):
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("composicion", composicion="banda"))
    assert nueva.arte.portada == "banda"
    assert edicion.aplicar_imagen(None, cfg, _pieza(), _accion("composicion", composicion="marco"))[0] is None
    assert edicion.aplicar_imagen(None, cfg, _pieza(), _accion("composicion", composicion="neon"))[0] is None   # sin color
    assert edicion.aplicar_imagen(None, cfg, _pieza(), _accion("usar_foto_autor"))[0] is None                 # no hay foto
    _fijar(cfg, "2026-10-30-1")
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(portada="panorama"), _accion("usar_archivo"))
    assert nueva.arte.registro == "archivo" and nueva.arte.portada == "sangre"


def test_buscar_otra_imagen_de_archivo(cfg, monkeypatch):
    def elegir(llm, cfg, pieza, datos, propuesta, ar, usadas, d):
        assert propuesta.consultas == ["printing press", "old library"]
        ar.imagen, ar.credito = "europeana:/2", "B · CC0 · Europeana"
    monkeypatch.setattr(direccion, "_imagen_de_archivo", elegir)
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("buscar_archivo", consultas=["printing press", "old library", "una búsqueda demasiado larga aquí"]))
    assert nueva.arte.imagen == "europeana:/2" and nueva.arte.registro == "archivo" and "B · CC0" in nota


def test_ilustrar_con_escena_valida_y_tope_del_dia(cfg, monkeypatch):
    assert "nombres propios" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena="Madrid at night " * 5))[1]
    llamadas = []
    monkeypatch.setattr(editorial, "generar", lambda cfg, pid, d, escena: llamadas.append(escena) or libres.ImagenLibre(
        archivo=editorial.CLAVE, pagina="", url="", ancho=1, alto=1, licencia="ilustración generada con IA (Magnific)",
        licencia_url=None, autor="Folio", descripcion=escena, libre=True, motivo="", fuente=""))
    escena = "a vast quiet suburban block at dusk where every house is a hollow stage set propped up by wooden beams"
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))
    assert nueva.arte.portada == "panorama" and nueva.arte.registro == "ilustracion" and llamadas
    cfg.pipeline.arte.ilustracion_editorial.max_por_dia = 0
    assert "máximo del día" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))[1]
    assert "graves" in edicion.aplicar_imagen(None, cfg, _pieza().model_copy(update={"arte": Arte(tono="grave", recurso="foto")}),
                                              _accion("ilustrar", escena=escena))[1]
