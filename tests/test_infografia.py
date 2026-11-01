"""Infografía de la idea (folio.infografia), su esquema de Magnific, el vídeo por diapositiva y el retrato
por tono. Sin red ni gasto."""

from io import BytesIO

import httpx
import pytest
from PIL import Image

from folio import arte, infografia, render
from folio.imagenes import esquema, libres
from folio.imagenes import retrato_generado as rg
from folio.modelos import Arte, Infografia, Pieza

from datos import ELECCION, LIBRO, guion_valido
from test_arte import _propuesta

# El guion de los datos: «Un tribunal juzga a un funcionario que firmaba órdenes.» / «El mal administrativo
# necesita gente que no se pregunte nada.»
MAPA = Infografia(tipo="mapa", titulo="Del tribunal a la obediencia", etiquetas=["firmaba órdenes", "mal administrativo"])
ESQUEMA = Infografia(tipo="esquema", titulo="Una máquina de obedecer", etiquetas=["tribunal", "funcionario", "gente corriente"])


def _pieza(**arte_):
    p = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
              eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())
    if arte_:
        p.arte = Arte(tono="sereno", recurso="foto", **arte_)
    return p


def test_la_linea_de_tiempo_sale_de_la_ficha_verificada():
    h = infografia.hitos(_pieza())
    assert [x["anio"] for x in h] == [1963, 2014, 2026]          # original, edición española y la noticia
    assert h[0]["detalle"] == "primera edición en inglés" and "Debolsillo" in h[1]["detalle"] and h[2].get("ahora")
    mismo = _pieza()
    mismo.libros = [LIBRO.model_copy(update={"anio_primera_edicion": 2026, "edicion_es": "no", "edicion_es_detalle": None})]
    assert infografia.hitos(mismo) == []                          # un solo año: no hay línea


def test_rotulos_literales_del_guion_y_titulo_sin_cifras():
    p = _pieza()
    info, avisos = infografia.validar(MAPA, p, ["linea", "mapa", "esquema"], True)
    assert info.etiquetas == ["firmaba órdenes", "mal administrativo"] and avisos == []
    info, avisos = infografia.validar(MAPA.model_copy(update={"etiquetas": ["firmaba órdenes", "obediencia ciega"]}), p, ["mapa"], True)
    assert info is None and any("obediencia ciega" in a for a in avisos)
    info, avisos = infografia.validar(MAPA.model_copy(update={"titulo": "En 1963 lo vio"}), p, ["mapa"], True)
    assert not info.titulo and "sin cifras" in avisos[0]
    assert infografia.validar(ESQUEMA, p, ["esquema"], hay_imagen=False)[0] is None    # sin imagen no hay esquema
    assert infografia.validar(MAPA, p, ["linea"], True)[0] is None                     # no permitida


def test_en_piezas_graves_solo_la_linea(cfg):
    p = _pieza()
    a = Arte(tono="grave", recurso="foto")
    arte._composicion(cfg, p, _propuesta(tono="grave", infografia=MAPA), a)
    assert a.infografia.tipo == "linea"                    # el mapa no se permite en graves: pasa a la línea
    arte._composicion(cfg, p, _propuesta(tono="grave", infografia=Infografia(tipo="linea", titulo="Antes de la noticia, el libro")), a)
    assert a.infografia.tipo == "linea"


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_la_idea_pinta_su_infografia_y_se_marca_para_video(cfg_diseno):
    p = render.Plantillas(cfg_diseno)
    linea = p.html_diapositiva(_pieza(infografia=Infografia(tipo="linea", titulo="El libro llegó antes")), 4)
    assert "infografia--linea" in linea and "1963" in linea and "2014" in linea and "hito--ahora" in linea
    assert "data-video" in linea and 'class="glifo"' not in linea
    mapa = p.html_diapositiva(_pieza(infografia=MAPA), 4)
    assert "infografia--mapa" in mapa and "firmaba órdenes" in mapa
    # El esquema sin su ilustración, o con el guion editado que ya no casa, sale como antes
    assert "infografia" not in p.html_diapositiva(_pieza(infografia=ESQUEMA), 4)
    editada = _pieza(infografia=MAPA)
    editada.guion.diapositivas[1].texto = "Otro texto."
    html = p.html_diapositiva(editada, 4)
    assert "infografia" not in html and "data-video" not in html and 'class="glifo"' in html


def test_que_diapositivas_salen_en_video(cfg_diseno):
    p = render.Plantillas(cfg_diseno)
    sereno = _pieza(cifra="tribunal")
    assert "data-video" not in p.html_diapositiva(sereno, 1)          # portada tipográfica, sin interferencia
    assert "data-video" not in p.html_diapositiva(sereno, 2)          # una cifra sin número no cuenta
    ironico = _pieza(cifra="tribunal")
    ironico.arte.tono = "ironico"
    portada = p.html_diapositiva(ironico, 1)
    assert "data-video" in portada and portada.count('class="interferencia') == 2
    con_numero = _pieza(cifra="1963")
    con_numero.guion.diapositivas[1].texto = "Un tribunal de 1963 juzga a un funcionario que firmaba órdenes."
    assert "data-contar" in p.html_diapositiva(con_numero, 2) and "data-video" in p.html_diapositiva(con_numero, 2)
    assert "window.folioFotograma" in (render.dir_diseno(cfg_diseno) / "ajuste.js").read_text()


def _jpeg() -> bytes:
    b = BytesIO()
    Image.new("RGB", (400, 300), (90, 80, 70)).save(b, "JPEG")
    return b.getvalue()


def _fijar_imagen(cfg, pieza_id="2026-10-30-1"):
    dir_fecha = cfg.dir_cache("2026-10-30")
    libres.dir_imagenes(dir_fecha).mkdir(parents=True, exist_ok=True)
    (libres.dir_imagenes(dir_fecha) / f"{pieza_id}.jpg").write_bytes(_jpeg())
    libres.guardar_metadatos(libres.ImagenLibre(
        archivo="europeana:/1", pagina="", url="", ancho=400, alto=300, licencia="Dominio público", licencia_url=None,
        autor="", descripcion="", libre=True, motivo="", local=f"{pieza_id}.jpg", fuente="Europeana", institucion="Rijksmuseum"),
        pieza_id, dir_fecha)
    return dir_fecha


def test_el_esquema_parte_de_la_imagen_y_se_guarda_en_cache(cfg, monkeypatch):
    cfg.magnific_api_key = "clave"
    dir_fecha = _fijar_imagen(cfg)
    llamadas = []
    monkeypatch.setattr(rg, "generar", lambda foto, texto, *a, **k: (llamadas.append(texto), (_jpeg(), "t1", 1.0))[1])
    p = _pieza(infografia=ESQUEMA, imagen="europeana:/1")
    for _ in range(2):
        arte._esquema(cfg, p, p.arte, dir_fecha)
    assert len(llamadas) == 1 and "No people" in llamadas[0]                   # relanzar no vuelve a pagar
    assert esquema.ruta(dir_fecha, p.id).exists() and "Magnific" in p.arte.esquema and "Rijksmuseum" in p.arte.esquema
    from folio.informe import creditos_pie
    assert any(c.startswith("Infografía: esquema generado con IA") for c in creditos_pie(p.arte))


def test_sin_magnific_el_esquema_pasa_a_la_linea(cfg, monkeypatch):
    cfg.magnific_api_key = "clave"
    dir_fecha = _fijar_imagen(cfg)
    def falla(*a, **k):
        raise rg.ErrorMagnific("Magnific respondió 429", bloqueo=True)
    monkeypatch.setattr(rg, "generar", falla)
    p = _pieza(infografia=ESQUEMA, imagen="europeana:/1")
    arte._esquema(cfg, p, p.arte, dir_fecha)
    assert p.arte.infografia.tipo == "linea" and "pasa a la línea" in p.arte.avisos[-1]
    assert rg.bloqueado()                                                        # no se vuelve a llamar hoy
    rg.reiniciar()
    cfg.pipeline.arte.esquema.max_por_dia = 0
    p = _pieza(infografia=ESQUEMA, imagen="europeana:/1")
    arte._esquema(cfg, p, p.arte, dir_fecha)
    assert "máximo del día" in p.arte.avisos[-1]


def test_el_estilo_del_retrato_va_con_el_tono(cfg):
    rgc = cfg.pipeline.arte.retrato_generado
    rgc.estilos = ["low_poly", "voxel", "render_2000"]
    rgc.por_tono = {"grave": [], "ironico": ["render_2000"], "luminoso": ["voxel", "dithering"]}
    dir_fecha = cfg.dir_cache("2026-10-30")
    assert rg.estilo_del_dia(cfg, "p1", dir_fecha, "ironico") == ("render_2000", 0)
    assert rg.estilo_del_dia(cfg, "p1", dir_fecha, "luminoso") == ("voxel", 0)     # el dithering no está activo
    assert rg.estilo_del_dia(cfg, "p1", dir_fecha, "grave") == (None, 0)           # en graves, la foto
    assert rg.estilo_del_dia(cfg, "p1", dir_fecha, "sereno")[0] in rgc.estilos     # sin reparto, rota entre todos


def test_el_estilo_de_la_ilustracion_editorial_se_carga_del_prompt(cfg):
    """dibujar() lo necesita y los tests lo simulan: que exista y se lea (se perdió una vez al reorganizar)."""
    from folio.imagenes import editorial
    texto = editorial.estilo(type(cfg)(pipeline={}, fuentes=[]))
    assert "wordless" in texto.lower() and "no writing" in texto.lower()
    assert "magazine" not in texto.lower() and "editorial" not in texto.lower()   # llevaban a Seedream a maquetar (2/11)
