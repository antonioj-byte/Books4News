"""La imagen de portada (31/10, reglas del usuario): foto de autor, si no ilustración si el tema es
conceptual, si no archivo; barajando en el día, alternando foto real y retrato generado, y sin generar
nunca a partir de una foto de prensa. Sin red ni gasto."""

import pytest

from folio import arte, render
from folio.imagenes import libres, prensa, retratos
from folio.modelos import Arte, Pieza
from folio.render.medios import LADO_SANGRE

from datos import ELECCION, LIBRO, guion_valido
from test_arte import _propuesta


def test_jerarquia_de_la_portada():
    assert arte.elegir_registro(True, True, []) == "foto_autor"          # la foto del autor manda
    assert arte.elegir_registro(False, True, []) == "ilustracion"        # sin foto, el tema conceptual se ilustra
    assert arte.elegir_registro(False, False, []) == "archivo"
    assert arte.elegir_registro(True, False, ["foto_autor"]) == "foto_autor"   # sin alternativa no se baja al archivo


def test_barajar_en_el_dia():
    assert arte.elegir_registro(True, True, ["foto_autor"]) == "ilustracion"
    assert arte.elegir_registro(True, True, ["retrato_ia"]) == "ilustracion"
    assert arte.elegir_registro(True, True, ["ilustracion"]) == "foto_autor"
    assert arte.elegir_registro(False, True, ["ilustracion"]) == "ilustracion"
    assert arte.elegir_registro(True, True, ["ilustracion", None]) == "foto_autor"   # cuenta la última con registro


def test_foto_real_y_retrato_generado_se_alternan():
    assert not arte.toca_retrato_ia([])                                   # la primera del día, real
    assert arte.toca_retrato_ia(["foto_autor"])
    assert not arte.toca_retrato_ia(["foto_autor", "retrato_ia"])
    assert arte.toca_retrato_ia(["foto_autor", "ilustracion", "retrato_ia", "foto_autor"])


def _pieza():
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())


def _foto_prensa(cfg, pieza_id="2026-10-30-1", lado=520):
    from io import BytesIO
    from PIL import Image
    dir_fecha = cfg.dir_cache("2026-10-30")
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (lado, lado), (90, 80, 70)).save(carpeta / f"{pieza_id}-retrato.jpg")
    img = libres.ImagenLibre(archivo="prensa:anagrama:x", pagina="", url="", ancho=lado, alto=lado,
                             licencia="cortesía de Anagrama", licencia_url=None, autor="Sebastián Freire", descripcion="",
                             libre=True, motivo="", local=f"{pieza_id}-retrato.jpg", fuente="", persona="Hannah Arendt")
    libres.guardar_metadatos(img, f"{pieza_id}-retrato", dir_fecha)
    return img


def test_sin_commons_se_usa_la_foto_de_prensa_y_nunca_se_genera_a_partir_de_ella(cfg, monkeypatch):
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (None, "Sin retrato en Wikidata"))
    monkeypatch.setattr(prensa, "buscar_y_fijar", lambda autor, editorial, pid, d, **k: (_foto_prensa(cfg, pid), ""))
    generados = []
    monkeypatch.setattr(arte, "_retrato_generado", lambda *a, **k: generados.append(1) or True)
    monkeypatch.setattr(arte, "_imagen_de_archivo", lambda *a, **k: None)
    monkeypatch.setattr(arte, "_propuesta", lambda *a, **k: _propuesta())
    from folio.imagenes import cubiertas
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)
    cfg.pipeline.arte.retrato_generado.activo = True
    a = arte.dirigir(None, cfg, _pieza(), None, registros_del_dia=["foto_autor"])     # tocaría generado...
    assert a.registro == "foto_autor" and generados == []                             # ...pero es de prensa
    assert a.retrato == "Sebastián Freire · cortesía de Anagrama"
    assert any("Sin retrato en Wikidata" in x for x in a.avisos)


def test_bloqueo_de_la_editorial_no_para_la_pieza(cfg, monkeypatch):
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (None, "Sin retrato"))
    def bloqueo(*a, **k):
        raise prensa.BloqueoEditorial("https://www.anagrama-ed.es/autores/a respondió 429")
    monkeypatch.setattr(prensa, "buscar_y_fijar", bloqueo)
    a = Arte(tono="sereno", recurso="foto")
    assert arte._retrato(cfg, _pieza(), a, cfg.dir_cache("2026-10-30")) is None
    assert any("429" in x and "sin reintentar" in x for x in a.avisos)


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_la_foto_pequena_va_en_copia_y_la_grande_a_sangre(cfg_diseno, monkeypatch):
    from folio.imagenes import cubiertas
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)
    p = _pieza()
    p.arte = Arte(tono="sereno", recurso="foto", portada="sangre")
    _foto_prensa(cfg_diseno)
    html = render.Plantillas(cfg_diseno).html_diapositiva(p, 1)
    assert "portada--copia" in html and 'class="copia"' in html and "data-video" in html
    _foto_prensa(cfg_diseno, lado=LADO_SANGRE + 200)
    html = render.Plantillas(cfg_diseno).html_diapositiva(p, 1)
    assert "portada--sangre" in html and 'class="copia"' not in html
