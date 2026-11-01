import re

import pytest

from folio import render
from folio.modelos import Pieza

from datos import ELECCION, LIBRO, guion_valido


@pytest.fixture
def pieza():
    from folio.guion import ajustar_libros
    g = guion_valido()
    ajustar_libros(g, [LIBRO])  # como en el pipeline: la ficha con los datos verificados
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=g)


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_tokens_a_variables_css():
    css = render.css_tokens({"colores": {"papel": "#fff", "tinta_suave": "#666"}, "logotipo": "<svg/>"})
    assert "--colores-papel: #fff;" in css and "--colores-tinta-suave: #666;" in css
    assert "svg" not in css


def test_texto_escapado_y_cursivas():
    assert str(render.texto_html("En *La peste* <b>x</b> & y")) == "En <em>La peste</em> &lt;b&gt;x&lt;/b&gt; &amp; y"


def test_plantillas_solo_usan_variables_de_los_tokens(cfg_diseno):
    """Cambiar el design system es cambiar diseno/tokens.yaml, no las plantillas (también en las propuestas)."""
    carpetas = [render.dir_diseno(cfg_diseno)] + [render.dir_diseno(cfg_diseno, d) for d in render.direcciones(cfg_diseno)]
    for archivo in (a for c in carpetas for a in (c / "plantillas").iterdir()):
        texto = archivo.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", texto), f"color a fuego en {archivo.name}"
        assert not re.search(r"font-family:\s*(?!var\()['\"A-Za-z]", texto), f"fuente a fuego en {archivo.name}"


def test_html_de_cada_diapositiva(cfg_diseno, pieza):
    p = render.Plantillas(cfg_diseno)
    portada = p.html_diapositiva(pieza, 1, base_url="/diseno/")
    assert '<base href="/diseno/">' in portada and "diapositiva--portada" in portada and "--colores-pluma" in portada
    assert "portada--tipografica" in portada          # sin imagen, portada tipográfica
    cierre = p.html_diapositiva(pieza, 5)
    # La firma del texto no se repite; la ficha lleva los datos verificados
    assert "Léelo." in cierre and "Léelo. Folio" not in cierre
    assert "Debolsillo, 2014" in cierre and "tarjeta" in cierre
    assert "cubierta" not in cierre.split("<body>")[1]   # la cubierta sale una vez, en la diapositiva del libro
    assert "cubierta--dibujada" in p.html_diapositiva(pieza, 3)   # sin cubierta en la caché, se dibuja


def test_imagen_cifra_antetitulo_y_cubierta(cfg_diseno, pieza):
    from folio.imagenes import cubiertas, libres as imagenes
    from folio.modelos import Arte
    cache = cfg_diseno.dir_cache(pieza.fecha)
    imagenes.dir_imagenes(cache).mkdir(parents=True)
    (imagenes.dir_imagenes(cache) / f"{pieza.id}.jpg").write_bytes(b"jpg")
    img = imagenes.ImagenLibre(archivo="europeana:/1/x", pagina="", url="", ancho=1200, alto=900, licencia="Dominio público",
                               licencia_url=None, autor="Ana Pérez", descripcion="", libre=True, motivo="",
                               local=f"{pieza.id}.jpg", fuente="Europeana", institucion="Museo", enfoque=(30, 70))
    imagenes.guardar_metadatos(img, pieza.id, cache)
    (cache.parent / "cubiertas").mkdir()
    (cache.parent / "cubiertas" / "c.jpg").write_bytes(b"jpg")
    (cache.parent / "cubiertas" / f"{cubiertas._nombre(pieza.libros[0])}.json").write_text('{"archivo": "c.jpg"}')
    pieza.arte = Arte(tono="ironico", recurso="foto", portada="sangre", antetitulo="PODER", cifra="tribunal", cifra_rotulo="juzga",
                      remate="se elige")
    p = render.Plantillas(cfg_diseno, url_medio=lambda r: "/api/medios/" + r.name)
    portada = p.html_diapositiva(pieza, 1)
    assert "/api/medios/2026-10-30-1.jpg" in portada and "object-position: 30% 70%" in portada
    assert "portada--sangre" in portada and ">PODER<" in portada
    assert 'La obediencia también <span class="remate">se elige</span>' in portada
    assert "Ana Pérez" not in portada                  # el crédito va en el pie de la publicación
    noticia = p.html_diapositiva(pieza, 2)
    assert 'class="cifra__numero" data-encajar>tribunal<' in noticia and "imagen--arriba" not in noticia
    assert "/api/medios/c.jpg" in p.html_diapositiva(pieza, 3) and "/api/medios/c.jpg" not in p.html_diapositiva(pieza, 5)


def test_render_png_de_1080x1350(cfg_diseno, pieza, tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    from folio.imagenes import cubiertas
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)   # sin red en los tests
    from PIL import Image
    try:
        archivos, avisos = render.renderizar(cfg_diseno, [pieza], tmp_path)
    except Exception as exc:  # sin navegador en este entorno
        pytest.skip(f"Chromium no disponible: {exc}")
    assert [a.name for a in archivos] == ["01-portada.png", "02-actualidad.png", "03-libro.png", "04-idea.png", "05-cierre.png", "06-colofon.png"]
    assert all(Image.open(a).size == (1080, 1350) for a in archivos) and avisos == []


def test_libro_de_la_diapositiva(pieza):
    libros = render.ficha_libros(pieza)
    assert render.libro_de_diapositiva(libros, pieza, "Arendt vio en *Eichmann en Jerusalén* a un hombre corriente.")["autor"]
    assert render.libro_de_diapositiva(libros, pieza, "Nada que ver") is None


def test_portada_con_ilustracion_en_la_propuesta_humanista(cfg_diseno, pieza):
    from folio.imagenes import ilustracion
    from folio.modelos import Arte
    pieza.arte = Arte(tono="reflexivo", recurso="foto", portada="ilustracion")
    p = render.Plantillas(cfg_diseno, "humanista")
    assert "portada--revista" not in p.html_diapositiva(pieza, 1)       # sin SVG, se cae al círculo
    destino = ilustracion.ruta(cfg_diseno.dir_cache(pieza.fecha), pieza.id)
    destino.parent.mkdir(parents=True)
    destino.write_text(ilustracion.sanear('<svg><rect width="9" height="9"/><circle r="3"/><path d="M0 0"/></svg>'))
    portada = p.html_diapositiva(pieza, 1)
    assert "portada--revista" in portada and "<circle" in portada and "--campo: #EFC77A" in portada


def test_video_de_portada(cfg_diseno, pieza, tmp_path, monkeypatch):
    """MP4 de 1080×1350 solo si la portada tiene imagen; el PNG no se anima (en-video lo pone el vídeo)."""
    import shutil
    import subprocess
    pytest.importorskip("playwright")
    if not shutil.which("ffmpeg"):
        pytest.skip("sin ffmpeg")
    from PIL import Image
    from folio.imagenes import cubiertas, libres as imagenes
    from folio.modelos import Arte
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)
    cache = cfg_diseno.dir_cache(pieza.fecha)
    imagenes.dir_imagenes(cache).mkdir(parents=True)
    Image.new("RGB", (1200, 1500), (120, 90, 60)).save(imagenes.dir_imagenes(cache) / f"{pieza.id}.jpg")
    imagenes.guardar_metadatos(imagenes.ImagenLibre(
        archivo="x", pagina="", url="", ancho=1200, alto=1500, licencia="Dominio público", licencia_url=None, autor="A",
        descripcion="", libre=True, motivo="", local=f"{pieza.id}.jpg"), pieza.id, cache)
    sin_imagen = pieza.model_copy(update={"id": "2026-10-30-2"})
    pieza.arte = Arte(tono="sereno", recurso="foto", portada="sangre")
    try:
        archivos, avisos = render.renderizar_video(cfg_diseno, [pieza, sin_imagen], tmp_path, fps=4, segundos=1)
    except Exception as exc:  # sin navegador en este entorno
        pytest.skip(f"Chromium no disponible: {exc}")
    assert archivos == [tmp_path / pieza.id / "01-portada.mp4"] and avisos == []      # sin imagen, sin vídeo
    datos = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames", "-of", "csv=p=0",
                            str(archivos[0])], capture_output=True, text=True).stdout.strip()
    assert datos == "1080,1350,4"
    assert ".en-video .imagen img" in (render.dir_diseno(cfg_diseno) / "plantillas" / "base.css").read_text()
    assert "--video-segundos: 6;" in render.css_tokens(render.cargar_tokens(cfg_diseno))


def test_la_cubierta_no_se_repite_en_el_carrusel(cfg_diseno, pieza):
    """Si dos diapositivas de libro hablan del mismo libro, la segunda sale solo con el texto."""
    from folio.modelos import Diapositiva
    pieza.guion.diapositivas.insert(3, Diapositiva(n=4, tipo="libro", texto="Eichmann en Jerusalén vuelve a la obediencia."))
    for i, d in enumerate(pieza.guion.diapositivas, 1):
        d.n = i
    p = render.Plantillas(cfg_diseno)
    assert 'class="escaparate"' in p.html_diapositiva(pieza, 3)
    segunda = p.html_diapositiva(pieza, 4)
    assert 'class="escaparate"' not in segunda and "vuelve a la obediencia" in segunda


def test_la_cara_solo_va_con_su_libro(cfg_diseno, pieza):
    """El retrato de otro autor (p. ej. Borges junto a un libro de Enríquez) no sale ni en la portada ni
    en el círculo junto a la cubierta."""
    from PIL import Image
    from folio.imagenes import libres as imagenes
    from folio.modelos import Arte
    cache = cfg_diseno.dir_cache(pieza.fecha)
    imagenes.dir_imagenes(cache).mkdir(parents=True)
    Image.new("RGB", (1200, 1500), (90, 90, 90)).save(imagenes.dir_imagenes(cache) / f"{pieza.id}-retrato.jpg")
    pieza.arte = Arte(tono="sereno", recurso="foto", portada="sangre")

    def con_retrato_de(persona):
        imagenes.guardar_metadatos(imagenes.ImagenLibre(
            archivo="commons:File:x.jpg", pagina="", url="", ancho=1200, alto=1500, licencia="CC BY 4.0", licencia_url=None,
            autor="A", descripcion="", libre=True, motivo="", local=f"{pieza.id}-retrato.jpg", persona=persona),
            f"{pieza.id}-retrato", cache)
        p = render.Plantillas(cfg_diseno)
        return p.html_diapositiva(pieza, 1), p.html_diapositiva(pieza, 3)

    portada, libro = con_retrato_de("Jorge Luis Borges")
    assert "con-retrato" not in portada and 'class="cara"' not in libro
    portada, libro = con_retrato_de("Hannah Arendt")
    assert "con-retrato" in portada and 'class="cara"' in libro


def test_misma_persona():
    from folio.render.plantillas import misma_persona
    assert misma_persona("Mariana Enriquez", "Mariana Enríquez") and misma_persona("Mariana Enríquez", "mariana enriquez")
    assert misma_persona("Javier Cercas", "Javier Cercas Mena")
    assert not misma_persona("Jorge Luis Borges", "Mariana Enríquez") and not misma_persona(None, "Borges")


def test_el_video_borra_los_de_una_version_anterior(cfg_diseno, pieza, tmp_path, monkeypatch):
    """Los NN-tipo.mp4 viejos de la pieza se borran al pintar: la web y el .zip los servirían."""
    import shutil
    pytest.importorskip("playwright")
    if not shutil.which("ffmpeg"):
        pytest.skip("sin ffmpeg")
    from folio.imagenes import cubiertas
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)
    viejo = tmp_path / pieza.id / "02-actualidad.mp4"
    viejo.parent.mkdir(parents=True)
    viejo.write_bytes(b"de otra version")
    try:
        archivos, _ = render.renderizar_video(cfg_diseno, [pieza], tmp_path, fps=2, segundos=1)
    except Exception as exc:  # sin navegador en este entorno
        pytest.skip(f"Chromium no disponible: {exc}")
    assert archivos == [] and not viejo.exists()          # esta pieza no tiene nada animado


def test_la_hoja_de_estilos_lleva_su_version(cfg_diseno, pieza):
    """El navegador no puede usar una base.css vieja con plantillas nuevas (1/11: retrato gigante en el cierre)."""
    html = render.Plantillas(cfg_diseno).html_diapositiva(pieza, 1)
    v = render.Plantillas(cfg_diseno).version_diseno
    assert f'plantillas/base.css?v={v}"' in html and f'ajuste.js?v={v}"' in html and len(v) == 10


def test_la_imagen_de_archivo_no_se_repite_en_la_noticia(cfg_diseno, pieza):
    from PIL import Image
    from folio.imagenes import libres as imagenes
    from folio.modelos import Arte
    cache = cfg_diseno.dir_cache(pieza.fecha)
    imagenes.dir_imagenes(cache).mkdir(parents=True)
    def fijar(clave, archivo):
        Image.new("RGB", (1200, 1500), (90, 90, 90)).save(imagenes.dir_imagenes(cache) / f"{clave}.jpg")
        imagenes.guardar_metadatos(imagenes.ImagenLibre(archivo=archivo, pagina="", url="", ancho=1200, alto=1500, licencia="CC0",
                                   licencia_url=None, autor="A", descripcion="", libre=True, motivo="", local=f"{clave}.jpg"), clave, cache)
    fijar(pieza.id, "europeana:/1")
    pieza.arte = Arte(tono="sereno", recurso="foto", portada="sangre", registro="archivo", imagen="europeana:/1")
    p = render.Plantillas(cfg_diseno)
    portada, noticia = p.html_diapositiva(pieza, 1), p.html_diapositiva(pieza, 2)
    assert f"{pieza.id}.jpg" in portada and f"{pieza.id}.jpg" not in noticia      # sin segunda: noticia sin foto
    fijar(pieza.id + "-noticia", "europeana:/2")
    noticia = render.Plantillas(cfg_diseno).html_diapositiva(pieza, 2)
    assert f"{pieza.id}-noticia.jpg" in noticia and f"{pieza.id}.jpg\"" not in noticia
