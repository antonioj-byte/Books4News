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
    datos = dict(tipo=tipo, enfoque_x=50, enfoque_y=50, composicion="", consultas=[], escena="", persona="", estilo="")
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
    monkeypatch.setattr(editorial, "generar_limpia", lambda llm, cfg, pid, d, escena: (llamadas.append(escena) or libres.ImagenLibre(
        archivo=editorial.CLAVE, pagina="", url="", ancho=1, alto=1, licencia="ilustración generada con IA (Magnific)",
        licencia_url=None, autor="Folio", descripcion=escena, libre=True, motivo="", fuente=""), []))
    escena = "a vast quiet suburban block at dusk where every house is a hollow stage set propped up by wooden beams"
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))
    assert nueva.arte.portada == "panorama" and nueva.arte.registro == "ilustracion" and llamadas
    monkeypatch.setattr(editorial, "generar_limpia", lambda *a: (None, ["letras (arriba)", "letras (esquina)"]))
    assert "salieron con letras" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))[1]
    cfg.pipeline.arte.ilustracion_editorial.max_por_dia = 0
    assert "máximo del día" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))[1]
    assert "graves" in edicion.aplicar_imagen(None, cfg, _pieza().model_copy(update={"arte": Arte(tono="grave", recurso="foto")}),
                                              _accion("ilustrar", escena=escena))[1]


def test_buscar_otra_imagen_que_falla_no_deja_la_pieza_sin_imagen(cfg, monkeypatch):
    _fijar(cfg, "2026-10-30-1")
    def falla(llm, cfg, pieza, datos, propuesta, ar, usadas, d):
        libres.olvidar(pieza.id, d)                 # como la de verdad, borra antes de elegir
        raise RuntimeError("Europeana caída")
    monkeypatch.setattr(direccion, "_imagen_de_archivo", falla)
    nueva, nota = edicion._imagen_sin_romper(None, cfg, _pieza(registro="archivo"), _accion("buscar_archivo", consultas=["printing press"]))
    assert nueva is None and "Europeana caída" in nota
    assert (libres.dir_imagenes(cfg.dir_cache("2026-10-30")) / "2026-10-30-1.jpg").exists()
    def no_encuentra(llm, cfg, pieza, datos, propuesta, ar, usadas, d):
        libres.olvidar(pieza.id, d)
    monkeypatch.setattr(direccion, "_imagen_de_archivo", no_encuentra)
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(registro="archivo"), _accion("buscar_archivo", consultas=["printing press"]))
    assert nueva is None and (libres.dir_imagenes(cfg.dir_cache("2026-10-30")) / "2026-10-30-1.jpg").exists()



def test_retrato_de_una_persona_real_solo_desde_una_foto_libre(cfg, monkeypatch):
    from folio.imagenes import retrato_generado, retratos
    sin_libro = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="cajon-el-secuestro-perec",
                      eleccion=ELECCION.model_copy(update={"formato": "curiosidad", "libros_candidatos": []}), n_medios=1,
                      libros=[], guion=guion_valido(), arte=Arte(tono="sereno", recurso="ilustracion", portada="panorama"))
    # Sin foto libre: se dice claro y no se dibuja nada
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (None, "Commons no tiene ninguna libre"))
    nueva, nota = edicion.aplicar_imagen(None, cfg, sin_libro, _accion("buscar_retrato", persona="Georges Perec"))
    assert nueva is None and "no puedo poner su cara" in nota
    # Con foto libre: va en la portada y la pieza sin libro guarda a quién retrata
    def fija(persona, pid, d, sa):
        _fijar(cfg, f"{pid}-retrato", "commons:File:Perec.jpg")
        return libres.de_pieza(f"{pid}-retrato", d), ""
    monkeypatch.setattr(retratos, "buscar_y_fijar", fija)
    nueva, nota = edicion.aplicar_imagen(None, cfg, sin_libro, _accion("buscar_retrato", persona="Georges Perec"))
    assert nueva.eleccion.protagonista == "Georges Perec" and nueva.arte.registro == "foto_autor"
    assert nueva.arte.portada == "sangre" and "Retrato de Georges Perec" in nota
    # Ilustrarlo: desde esa foto, en un estilo de la casa, con revisión humana
    estilos = []
    monkeypatch.setattr(retrato_generado, "aplicar", lambda cfg, pid, d, estilo: estilos.append(estilo) or libres.de_pieza(f"{pid}-retrato", d))
    otra, nota = edicion.aplicar_imagen(None, cfg, nueva, _accion("retrato_ilustrado", estilo="voxel"))
    assert estilos == ["voxel"] and otra.arte.registro == "retrato_ia" and "parecido" in nota
    assert direccion.AVISO_RETRATO_GENERADO in otra.revision_humana
    # Con libro, la cara es la del autor y no otra
    con_libro = _pieza()
    nueva, nota = edicion.aplicar_imagen(None, cfg, con_libro, _accion("buscar_retrato", persona="Georges Perec"))
    assert nueva is None and "Hannah Arendt" in nota
