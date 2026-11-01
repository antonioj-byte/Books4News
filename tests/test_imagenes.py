import json
from io import BytesIO

import httpx
import pytest
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


# --- Búsqueda de cubiertas (sin red) ---------------------------------------------

def _servidor(rutas: dict, llamadas: list):
    """MockTransport: cada clave es un trozo de URL y su valor una lista de respuestas que se van gastando."""
    def manejar(req):
        llamadas.append(str(req.url))
        for trozo, respuestas in rutas.items():
            if trozo in str(req.url):
                return respuestas.pop(0) if len(respuestas) > 1 else respuestas[0]
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(manejar))


def _libro_es():
    from datos import LIBRO
    return LIBRO.model_copy(update={"isbn13": []})          # edición española 9788483460627, obra OL1386647W


@pytest.fixture(autouse=True)
def _sin_espera(monkeypatch):
    monkeypatch.setattr(cubiertas, "ESPERA_S", 0)


def test_cubierta_de_open_library_de_300_px_vale():
    assert cubiertas.es_buena(_jpg(298, 475, (180, 30, 30)))[0]           # El profesor y el loco, Debate


def test_un_5xx_se_reintenta_en_el_momento(tmp_path):
    llamadas = []
    rutas = {"isbn/9788483460627": [httpx.Response(502), httpx.Response(200, content=_jpg(298, 475, (180, 30, 30)))]}
    ruta = cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor(rutas, llamadas))
    assert ruta and ruta.exists()
    assert "edición española" in json.loads((tmp_path / "cubiertas" / "9788483460627.json").read_text())["origen"]


def test_fallo_pasajero_no_se_guarda_como_no_hay(tmp_path):
    rutas = {"covers.openlibrary.org": [httpx.Response(502)], "openlibrary.org/works": [httpx.Response(503)]}
    assert cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor(rutas, [])) is None
    llamadas = []
    rutas = {"isbn/9788483460627": [httpx.Response(200, content=_jpg(300, 470, (20, 60, 160)))]}
    assert cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor(rutas, llamadas))      # la siguiente vez, sí
    assert llamadas


def test_no_hay_definitivo_se_guarda_y_no_se_repite(tmp_path):
    cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor({}, []))                       # todo 404
    llamadas = []
    assert cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor({}, llamadas)) is None and llamadas == []


def test_no_hay_de_un_criterio_anterior_se_vuelve_a_buscar(tmp_path):
    (tmp_path / "cubiertas").mkdir()
    (tmp_path / "cubiertas" / "9788483460627.json").write_text(json.dumps(
        {"archivo": None, "descartes": ["Open Library (edición española, 9788483460627): demasiado pequeña (298 px)"]}))
    rutas = {"isbn/9788483460627": [httpx.Response(200, content=_jpg(298, 475, (180, 30, 30)))]}
    assert cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor(rutas, []))


def test_cubiertas_de_la_obra_y_403_de_google_books_a_la_vista(tmp_path):
    """Con edición española, solo cubiertas en castellano (2/11: salía la inglesa de «Aprender a rezar…»)."""
    llamadas = []
    ediciones = {"entries": [
        {"languages": [{"key": "/languages/eng"}], "covers": [999], "publishers": ["Dalkey Archive"], "publish_date": "2011"},
        {"languages": [{"key": "/languages/spa"}], "covers": [3332121], "publishers": ["Mondadori"], "publish_date": "2008",
         "isbn_13": ["9788439721000"]}]}
    rutas = {"googleapis.com/books": [httpx.Response(403, json={"error": {"message": "forbidden"}})],
             "OL1386647W/editions.json": [httpx.Response(200, json=ediciones)],
             "b/id/3332121": [httpx.Response(200, content=_jpg(298, 475, (180, 30, 30)))],
             "b/id/999": [httpx.Response(200, content=_jpg(298, 475, (30, 30, 180)))]}
    assert cubiertas.buscar(_libro_es(), tmp_path, clave_gb="k", cliente=_servidor(rutas, llamadas))
    meta = json.loads((tmp_path / "cubiertas" / "9788483460627.json").read_text())
    assert "en castellano, Mondadori, 2008" in meta["origen"] and not any("b/id/999" in u for u in llamadas)
    assert any("Google Books" in d and "HTTP 403" in d for d in meta["descartes"])
    assert not cubiertas.es_pasajero("Google Books (edición española, 1): HTTP 403")
    assert cubiertas.es_pasajero("Open Library (1): HTTP 502") and cubiertas.es_pasajero("Open Library (1): ConnectTimeout")


def test_sin_cubierta_en_castellano_mejor_la_tipografica(tmp_path):
    """Si solo hay cubiertas en otra lengua, ninguna; y una extranjera guardada de antes deja de valer."""
    ediciones = {"entries": [{"languages": [{"key": "/languages/eng"}], "covers": [999], "publishers": ["Dalkey"]}]}
    rutas = {"OL1386647W/editions.json": [httpx.Response(200, json=ediciones)],
             "OL1386647W.json": [httpx.Response(200, json={"covers": [999]})],
             "b/id/999": [httpx.Response(200, content=_jpg(298, 475, (30, 30, 180)))]}
    assert cubiertas.buscar(_libro_es(), tmp_path, cliente=_servidor(rutas, [])) is None
    carpeta = tmp_path / "cubiertas"
    (carpeta / "vieja.jpg").write_bytes(_jpg(298, 475, (30, 30, 180)))
    (carpeta / "9788483460627.json").write_text(json.dumps({"archivo": "vieja.jpg", "origen": "Open Library (obra OL1, cubierta 9)"}))
    assert cubiertas.en_cache(_libro_es(), tmp_path) is None


def test_cubierta_de_una_edicion_pedida_en_el_chat(tmp_path):
    """«Pon la portada de la edición de Mondadori»: la busca entre las ediciones en castellano y trae sus datos."""
    ediciones = {"entries": [{"languages": [{"key": "/languages/spa"}], "covers": [3332121], "publishers": ["Mondadori"],
                              "publish_date": "marzo de 2008", "isbn_13": ["9788439721000"], "title": "Aprender a rezar en la era de la técnica"}]}
    rutas = {"OL1386647W/editions.json": [httpx.Response(200, json=ediciones)],
             "b/id/3332121": [httpx.Response(200, content=_jpg(298, 475, (180, 30, 30)))]}
    ruta, ed, nota = cubiertas.de_edicion(_libro_es(), tmp_path, editorial="Random House / Mondadori", cliente=_servidor(rutas, []))
    assert ruta and ruta.exists() and ed.editorial == "Mondadori" and ed.anio == "2008" and ed.isbn == "9788439721000"
    ruta, ed, nota = cubiertas.de_edicion(_libro_es(), tmp_path, editorial="Anagrama", cliente=_servidor(rutas, []))
    assert ruta is None and "Anagrama" in nota
