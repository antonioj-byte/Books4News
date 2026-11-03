"""La foto del autor recortada en collage (3/11): ciclo de caras, permisos, composición y deshacer."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from folio import arte
from folio.imagenes import libres, recorte


def test_las_caras_se_turnan_foto_recorte_retrato():
    todo = {"recorte", "retrato_ia"}
    assert arte.tratamiento_cara([], todo) == "foto_autor"                       # la primera del día, real
    assert arte.tratamiento_cara(["foto_autor"], todo) == "recorte"
    assert arte.tratamiento_cara(["foto_autor", "recorte"], todo) == "retrato_ia"
    assert arte.tratamiento_cara(["foto_autor", "ilustracion", "recorte", "retrato_ia"], todo) == "foto_autor"
    # Si al que toca no se le puede, el siguiente que se pueda
    assert arte.tratamiento_cara(["foto_autor"], {"retrato_ia"}) == "retrato_ia"
    assert arte.tratamiento_cara(["foto_autor"], set()) == "foto_autor"


def _img(archivo="commons:File:x.jpg", local="p-retrato.jpg", **kw):
    return libres.ImagenLibre(archivo=archivo, pagina="", url="", ancho=800, alto=1000, licencia="CC BY 4.0",
                              licencia_url=None, autor="Fotógrafa", descripcion="", libre=True, motivo="", local=local, **kw)


def test_solo_fotos_que_se_pueden_modificar():
    assert recorte.se_puede(_img()) is None
    assert "prensa" in recorte.se_puede(_img(archivo="prensa:anagrama:x"))
    assert "subida" in recorte.se_puede(_img(archivo="material:abc"))
    assert recorte.se_puede(_img(archivo="material:abc", modificable=True)) is None
    assert "tratada" in recorte.se_puede(_img(archivo="recorte:papel"))
    assert recorte.se_puede(None)


def _foto_y_mascara():
    foto = Image.new("RGB", (400, 500), (120, 140, 160))
    d = ImageDraw.Draw(foto)
    d.ellipse((140, 80, 260, 220), fill=(220, 180, 160))
    d.rectangle((100, 220, 300, 500), fill=(60, 60, 70))
    m = Image.new("L", foto.size, 0)
    dm = ImageDraw.Draw(m)
    dm.ellipse((140, 80, 260, 220), fill=255)
    dm.rectangle((100, 220, 300, 500), fill=255)
    return foto, m


def test_busto_y_las_dos_composiciones():
    foto, m = _foto_y_mascara()
    b = recorte.busto(foto, m, 600)
    assert b.mode == "RGBA" and b.height > 600
    papel = recorte.sobre_papel(b, "pluma")
    assert papel.size == (recorte.ANCHO, recorte.ALTO)
    assert papel.getpixel((20, 20)) == recorte.PLUMA                  # el campo, del color de la pieza
    assert recorte.sobre_papel(b, "marcador").getpixel((20, 20)) == recorte.MARCADOR
    escena = recorte.sobre_escena(Image.new("RGB", (1088, 1360), (10, 200, 10)), b)
    assert escena.size == (recorte.ANCHO, recorte.ALTO)
    assert escena.getpixel((20, 20)) == (10, 200, 10)


def test_sin_persona_no_hay_recorte():
    foto, _ = _foto_y_mascara()
    try:
        recorte.busto(foto, Image.new("L", foto.size, 0), 600)
    except recorte.SinPersona:
        return
    raise AssertionError("debía fallar sin persona")


def test_el_fondo_deja_vacia_la_mitad_de_abajo():
    from folio.config import cargar
    e = recorte.estilo_fondo(cargar())
    assert "lower half" in e and "points of interest on the left" not in e
    assert "No real or recognisable people" in e


def test_aplicar_y_deshacer(tmp_path, monkeypatch):
    from folio.config import cargar
    cfg = cargar()
    carpeta = libres.dir_imagenes(tmp_path)
    carpeta.mkdir(parents=True)
    foto, m = _foto_y_mascara()
    foto.save(carpeta / "p-retrato.jpg")
    libres.guardar_metadatos(_img(persona="Ana Pérez"), "p-retrato", tmp_path)
    monkeypatch.setattr(recorte, "mascara", lambda cfg, im: m.resize(im.size))
    img = recorte.aplicar(cfg, "p", tmp_path, "papel", "pluma")
    assert img.archivo == "recorte:papel" and img.persona == "Ana Pérez"
    assert "recortada y en trama" in img.credito and "Fotógrafa" in img.credito
    assert (carpeta / "p-retrato-original.jpg").exists()
    assert recorte.de_dia(tmp_path, "papel") == 1 and recorte.de_dia(tmp_path, "papel", sin="p") == 0
    # Otra vez, parte del original (no del recorte)
    assert recorte.aplicar(cfg, "p", tmp_path, "papel", "marcador").archivo == "recorte:papel"
    vuelta = recorte.restaurar_original(tmp_path, "p")
    assert vuelta.archivo == "commons:File:x.jpg" and not (carpeta / "p-retrato-original.json").exists()
    with Image.open(carpeta / vuelta.local) as im:
        assert im.size == (400, 500)
