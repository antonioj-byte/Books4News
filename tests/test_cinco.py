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


ESCENAS = [f"A giant golden laurel wreath descends on thin wires toward tiny writers holding open books, scene number {n}"
           for n in ("one", "two", "three", "four", "five")]


def _guion(**cambios):
    datos = dict(titular="El Cervantes, el Goncourt y tres más", subtitulo="Lo que hay que saber hoy del mundo del libro, "
                 "en cinco diapositivas y con sus fuentes", remate="y tres más",
                 noticias=[cinco.NoticiaCinco(historia=f"e{i}", titular=f"Pasa algo importante en la noticia número {i}",
                                              subtitulo="Una explicación de diez palabras o más que cuenta por qué importa esto hoy",
                                              remate=f"noticia número {i}", escena=ESCENAS[i]) for i in range(5)],
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
    g.noticias[4].escena = "A tiny writer holds the Planeta trophy high above a crowd of anonymous readers in a big hall"
    g.noticias[0].escena = "A small gold medal hangs from a ribbon above a crowd of anonymous readers in a big quiet hall"
    errores = " ".join(cinco.validar(g, {f"e{i}" for i in range(6)}))
    assert "Noticia 2: el subtítulo" in errores and "Noticia 3: el remate" in errores
    assert "repite la historia" in errores and "Noticia 5: la escena no puede llevar nombres propios" in errores
    assert "Noticia 1: la escena no puede llevar medallas" in errores


def test_la_pieza_tiene_portada_cinco_noticias_y_sus_fuentes():
    p = cinco.a_pieza(_guion(), "2026-11-02-9", "2026-11-02", _historias())
    tipos = [d.tipo for d in p.guion.diapositivas]
    assert tipos == ["portada"] + ["noticia"] * 5 and all(d.subtitulo for d in p.guion.diapositivas)
    assert len(p.fuentes) == 5 and p.eleccion.formato == "cinco" and p.arte.escenas_noticias == ESCENAS


def test_estilo_de_la_casa(cfg):
    e = cinco.estilo(cfg)
    assert "collage" in e and "no text" in e.lower()


def test_no_repite_ideas_de_la_semana(cfg):
    cinco.guardar_escenas(cfg, "2026-11-01", ["a laurel crane"])
    cinco.guardar_escenas(cfg, "2026-10-20", ["an old brass key"])
    assert cinco.escenas_recientes(cfg, "2026-11-02") == ["a laurel crane"]


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_render_portada_y_noticias_con_su_ilustracion(cfg_diseno):
    from io import BytesIO
    from PIL import Image
    from folio.imagenes import libres
    p = cinco.a_pieza(_guion(), "2026-11-02-9", "2026-11-02", _historias())
    d = cfg_diseno.dir_cache(p.fecha)
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    for i in (1, 2, 3, 4):                                    # la quinta, sin ilustración
        clave = cinco.clave_imagen(p.id, i)
        b = BytesIO(); Image.new("RGB", (1088, 1360)).save(b, "JPEG")
        (libres.dir_imagenes(d) / f"{clave}.jpg").write_bytes(b.getvalue())
        libres.guardar_metadatos(libres.ImagenLibre(archivo="magnific:cinco", pagina="", url="", ancho=1088, alto=1360, licencia="x",
                                                    licencia_url=None, autor="Folio", descripcion="", libre=True, motivo="",
                                                    local=f"{clave}.jpg", fuente=""), clave, d)
    pl = render.Plantillas(cfg_diseno, url_medio=lambda r: "/api/medios/" + r.name)
    portada = pl.html_diapositiva(p, 1)
    assert "diapositiva--cinco" in portada and "2026-11-02-9-cinco-1.jpg" in portada and "Cinco del libro · 2 nov" in portada
    n2, n6 = pl.html_diapositiva(p, 3), pl.html_diapositiva(p, 6)
    assert "2026-11-02-9-cinco-2.jpg" in n2 and "Una explicación" in n2 and 'class="remate"' in n2 and "El País" in n2
    assert "cinco-ilus" not in n6 and "cinco-numero" in n6       # sin ilustración, el número grande
    assert pl.total(p) == 7                                     # y el colofón
