"""«Cinco del libro» (2/11, prueba de cinco días): validación, pieza, escena y render. Sin red ni gasto."""

from datetime import datetime, timezone

import pytest

from folio import cinco, render
from folio.modelos import Articulo, Historia


def _historias(n=6):
    return [Historia(id=f"e{i}", carril="editorial", n_medios=2, medios=["El País", "ABC"], titular_es=f"Noticia {i}",
                     resumen_es="Resumen.", articulos=[Articulo(id=f"a{i}", idioma="es", medio="El País", url=f"https://elpais.com/{i}", titulo=f"Noticia {i}",
                                                                acceso="abierto", publicado_en=datetime(2026, 11, 2, tzinfo=timezone.utc))])
            for i in range(n)]


OBJETOS = ["a polished glass trophy", "a sealed envelope with wax", "a stack of tied novels", "a pair of headphones",
           "an open cardboard box"]


def _guion(**cambios):
    datos = dict(titular="El Cervantes, el Goncourt y tres más", subtitulo="Lo que hay que saber hoy del mundo del libro, "
                 "en cinco diapositivas y con sus fuentes", remate="y tres más",
                 noticias=[cinco.NoticiaCinco(historia=f"e{i}", titular=f"Pasa algo importante en la noticia número {i}",
                                              subtitulo="Una explicación de diez palabras o más que cuenta por qué importa esto hoy",
                                              remate=f"noticia número {i}", objeto=OBJETOS[i]) for i in range(5)],
                 pie_instagram=" ".join(["palabra"] * 90))
    datos.update(cambios)
    return cinco.GuionCinco(**datos)


def test_un_guion_bueno_valida():
    assert cinco.validar(_guion(), {f"e{i}" for i in range(6)}) == []


def test_cada_noticia_necesita_subtitulo_y_remate_literal():
    g = _guion()
    g.noticias[1].subtitulo = "Demasiado corto"
    g.noticias[2].remate = "no está en el titular"
    g.noticias[3].historia = "e0"
    g.noticias[4].objeto = "the Planeta Prize trophy"
    g.noticias[0].objeto = "a small gold medal"
    errores = " ".join(cinco.validar(g, {f"e{i}" for i in range(6)}))
    assert "Noticia 2: el subtítulo" in errores and "Noticia 3: el remate" in errores
    assert "repite la historia" in errores and "Noticia 5: el objeto" in errores and "Noticia 1: nada de medallas" in errores


def test_la_pieza_tiene_portada_cinco_noticias_y_sus_fuentes():
    p = cinco.a_pieza(_guion(), "2026-11-02-9", "2026-11-02", _historias())
    tipos = [d.tipo for d in p.guion.diapositivas]
    assert tipos == ["portada"] + ["noticia"] * 5 and all(d.subtitulo for d in p.guion.diapositivas)
    assert len(p.fuentes) == 5 and p.eleccion.formato == "cinco" and p.arte.objetos == OBJETOS


def test_escenario_por_dia_y_fila_fija(cfg):
    assert cinco.escenario_del_dia("2026-11-02") == "mesa" and cinco.escenario_del_dia("2026-11-03") == "balda"
    e = cinco.escena(cfg, "2026-11-04", OBJETOS)
    assert "bookshop" in e and "(3) a stack of tied novels" in e and "one tenth, three tenths" in e


def test_no_repite_objetos_de_la_semana(cfg):
    cinco.guardar_objetos(cfg, "2026-11-01", ["a polished glass trophy"])
    cinco.guardar_objetos(cfg, "2026-10-20", ["an old brass key"])
    assert cinco.objetos_recientes(cfg, "2026-11-02") == ["a polished glass trophy"]


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_render_portada_y_noticia_con_zoom(cfg_diseno):
    from io import BytesIO
    from PIL import Image
    from folio.imagenes import libres
    p = cinco.a_pieza(_guion(), "2026-11-02-9", "2026-11-02", _historias())
    d = cfg_diseno.dir_cache(p.fecha)
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    b = BytesIO(); Image.new("RGB", (1440, 810)).save(b, "JPEG")
    (libres.dir_imagenes(d) / f"{p.id}-cinco.jpg").write_bytes(b.getvalue())
    libres.guardar_metadatos(libres.ImagenLibre(archivo="magnific:cinco", pagina="", url="", ancho=1440, alto=810, licencia="x",
                                                licencia_url=None, autor="Folio", descripcion="", libre=True, motivo="",
                                                local=f"{p.id}-cinco.jpg", fuente=""), p.id + "-cinco", d)
    pl = render.Plantillas(cfg_diseno, url_medio=lambda r: "/api/medios/" + r.name)
    portada = pl.html_diapositiva(p, 1)
    assert "diapositiva--cinco" in portada and "cinco-mesa" in portada and "Cinco del libro · 2 nov" in portada
    n1, n5 = pl.html_diapositiva(p, 2), pl.html_diapositiva(p, 6)
    assert "cinco-zoom" in n1 and "background-position: 0.0% 50%" in n1 and "Una explicación" in n1
    assert "background-position: 100.0% 50%" in n5 and 'class="remate"' in n5 and "El País" in n5
    assert pl.total(p) == 7                           # y el colofón
