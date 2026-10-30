from io import BytesIO

from PIL import Image

from folio.imagenes import cubiertas, libres as imagenes


def test_licencias_aceptadas_y_rechazadas():
    assert imagenes.licencia_libre("Public domain")[0]
    assert imagenes.licencia_libre("CC0")[0]
    assert imagenes.licencia_libre("CC BY 4.0")[0]
    assert not imagenes.licencia_libre("CC BY-SA 4.0")[0]      # la imagen se modifica
    assert not imagenes.licencia_libre("CC BY-NC 2.0")[0]
    assert not imagenes.licencia_libre("")[0]
    assert imagenes.licencia_europeana("http://creativecommons.org/publicdomain/mark/1.0/") == ("Dominio público", True, "")
    assert imagenes.licencia_europeana("http://creativecommons.org/licenses/by/4.0/")[:2] == ("CC BY 4.0", True)
    assert not imagenes.licencia_europeana("http://creativecommons.org/licenses/by-sa/4.0/")[1]
    assert not imagenes.licencia_europeana("http://rightsstatements.org/vocab/InC/1.0/")[1]


def test_candidato_de_commons_con_restricciones():
    pagina = {"title": "File:x.jpg", "imageinfo": [{"width": 2000, "height": 1500, "url": "u", "descriptionurl": "d",
              "extmetadata": {"LicenseShortName": {"value": "Public domain"}, "Restrictions": {"value": "personality"}}}]}
    c = imagenes._candidato(pagina)
    assert not c.libre and "restricciones" in c.motivo


def _jpg(ancho, alto, color):
    b = BytesIO()
    im = Image.new("RGB", (ancho, alto), color)
    if color != "white":                                   # una franja clara, como una cubierta de verdad
        im.paste((240, 230, 210), (0, alto // 3, ancho, alto // 2))
    im.save(b, "JPEG")
    return b.getvalue()


def test_cubiertas_buenas_y_malas():
    assert cubiertas.es_buena(_jpg(600, 900, (180, 30, 30)))[0]
    assert "pequeña" in cubiertas.es_buena(_jpg(128, 186, (180, 30, 30)))[1]
    assert "blanco" in cubiertas.es_buena(_jpg(600, 900, "white"))[1]
    assert not cubiertas.es_buena(b"no soy una imagen")[0]


def test_iiif_a_mayor_resolucion():
    assert imagenes.mayor_resolucion("https://x.org/image/V1.jpg/full/512,/0/default.jpg") == \
        "https://x.org/image/V1.jpg/full/1600,/0/default.jpg"
    assert imagenes.mayor_resolucion("https://mm.dimu.org/image/1?dimension=1200x1200").endswith("1200x1200")
