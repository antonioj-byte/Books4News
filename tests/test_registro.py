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


def test_la_pregunta_admite_siglas_pero_no_nombres():
    assert arte.validar_pregunta("Por qué la IA nos da miedo") == "por qué la IA nos da miedo"
    assert arte.validar_pregunta("qué leer sobre Mariana Enriquez") is None
    assert arte.validar_pregunta("qué pasó en 2008 con los bancos") is None
    assert arte.validar_pregunta("") is None


def test_wikidata_bloqueado_no_se_vuelve_a_consultar(tmp_path, monkeypatch):
    import httpx
    llamadas = []
    def falla(nombre, cliente):
        llamadas.append(nombre)
        raise httpx.HTTPStatusError("403", request=httpx.Request("GET", "https://query.wikidata.org"),
                                    response=httpx.Response(403))
    monkeypatch.setattr(retratos, "archivo_en_commons", falla)
    img, motivo = retratos.buscar_y_fijar("Ana Pérez", "p1", tmp_path)
    assert img is None and "403" in motivo and "sin reintentar" in motivo
    img, motivo = retratos.buscar_y_fijar("Otra Persona", "p2", tmp_path)
    assert img is None and llamadas == ["Ana Pérez"]


def test_si_el_mapa_no_se_sostiene_va_la_linea(cfg):
    from folio.modelos import Infografia
    p = _pieza()
    a = Arte(tono="sereno", recurso="foto")
    arte._composicion(cfg, p, _propuesta(infografia=Infografia(tipo="mapa", titulo="Del tribunal a la obediencia",
                                                               etiquetas=["inventado del todo", "tampoco está"])), a)
    assert a.infografia.tipo == "linea" and "pasa a la línea de tiempo" in a.avisos[-1]


def test_regresiones_de_la_revision(cfg_diseno, monkeypatch, tmp_path):
    """Hallazgos de la revisión del 31/10."""
    from folio import infografia
    from folio.imagenes import retrato_generado as rg
    from folio.modelos import Infografia
    # Un nombre propio al principio de la pregunta no se cuela pasándolo a minúsculas
    assert arte.validar_pregunta("Madrid puede vivir sin coches") is None
    assert arte.validar_pregunta("Qué leer para entender el miedo") == "qué leer para entender el miedo"
    # Los rótulos de la infografía salen sin las marcas de cursiva
    p = _pieza()
    p.guion.diapositivas[3].texto = "El mal administrativo necesita *gente corriente* que no se pregunte nada."
    info, _ = infografia.validar(Infografia(tipo="mapa", titulo="Del tribunal a la obediencia",
                                            etiquetas=["firmaba órdenes", "*gente corriente*"]), p, ["mapa"], True)
    assert info.etiquetas == ["firmaba órdenes", "gente corriente"]
    # Nunca un retrato generado a partir de una foto de prensa, tampoco a mano
    _foto_prensa(cfg_diseno, "p9")
    with pytest.raises(ValueError, match="prensa"):
        rg.aplicar(cfg_diseno, "p9", cfg_diseno.dir_cache("2026-10-30"), "voxel")
    # La cifra editada fuera del texto deja de pintarse (y de contar en el vídeo)
    from folio.imagenes import cubiertas
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)
    con = _pieza()
    con.guion.diapositivas[1].texto = "Un tribunal de 1963 juzga a un funcionario."
    con.arte = Arte(tono="sereno", recurso="foto", cifra="1963")
    pl = render.Plantillas(cfg_diseno)
    assert "data-contar" in pl.html_diapositiva(con, 2)
    con.guion.diapositivas[1].texto = "Un tribunal juzga a un funcionario que firmaba órdenes."
    assert "cifra__numero" not in pl.html_diapositiva(con, 2)


def test_topes_diarios_cuentan_las_piezas_de_verdad_en_las_pruebas(cfg):
    real, prueba = cfg.dir_cache("2026-10-30"), cfg.dir_cache("2026-10-30") / "prueba"
    vistos = []
    contar = lambda d, pid: vistos.append(d) or 2
    assert arte._del_dia(contar, cfg, _pieza(), prueba) == 4 and vistos == [real, prueba]
    assert arte._del_dia(lambda d, pid: 2, cfg, _pieza(), real) == 2
