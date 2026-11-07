"""«La newsletter del jueves» (4/11): frases literales, pieza, render y la foto de quien firma."""
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from folio import newsletter, render
from folio.newsletter import FraseNewsletter, GuionNewsletter

TEXTO = (Path(__file__).parent / "fixtures" / "newsletter_2026-11-05.md").read_text(encoding="utf-8")
ESCENA = "a giant pencil with its eraser end rubbing out a long line on a blank sheet, a small mountain of crumbs beside it"


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def _guion(**k):
    frases = [("A escribir se aprende borrando", "borrando"),
              ("Lo que escribes solo es el remanente de lo que no escribes", "lo que no escribes"),
              ("un escritor es principalmente un lector que no tiene oferta de lecturas", "oferta de lecturas"),
              ("La tecnología acelera el vector de pensamiento, pero la dirección de ese vector solo la puedes marcar tú",
               "la puedes marcar tú"),
              ("Simplemente, resuelves más puzles", "más puzles"),
              ("Todo es formulaico. Nada es literatura", "Nada es literatura")]
    datos = dict(titular="2026 es el año en que más he escrito, y en el que menos he escrito", remate="menos he escrito",
                 subtitulo="Por qué la IA está cambiando lo que entendemos por autoría y, más aún, por editar",
                 percha="Philippe Jaenada acaba de ganar el Goncourt y lo primero que contó es que había usado un poquito de IA.",
                 percha_url="https://www.liberation.fr/culture/livres/prix-goncourt-2026-le-laureat-philippe-jaenada-revele-avoir-utilise-lia-a-trois-reprises-pour-ecrire-linconnue-du-quai-de-javel-20261104_AJO3OQFPFFHDXLBABUPVOG45FY/",
                 frases=[FraseNewsletter(texto=t, remate=r, escena=ESCENA) for t, r in frases],
                 cierre="la literatura va a sobrevivir. COMO SEA.", remate_cierre="COMO SEA.", escena_portada=ESCENA,
                 pie_instagram=" ".join(["palabra"] * 80))
    datos.update(k)
    return GuionNewsletter(**datos)


def test_las_frases_tienen_que_ser_literales():
    assert newsletter.validar(_guion(), TEXTO) == []
    # Mayúsculas, tildes y signos no cuentan; una palabra cambiada, sí
    assert newsletter.literal("a escribir se aprende borrando", TEXTO)
    errores = newsletter.validar(_guion(titular="2026 es el año en que más he escrito y menos he publicado",
                                        remate="menos he publicado"), TEXTO)
    assert any("titular tiene que ser una frase del ensayo" in e for e in errores)
    malas = _guion().frases
    malas[1] = FraseNewsletter(texto="Lo que escribes es lo que no borras", remate="no borras", escena=ESCENA)
    assert any(e.startswith("Frase 2: tiene que estar letra por letra") for e in newsletter.validar(_guion(frases=malas), TEXTO))
    assert any("enlace de la percha" in e for e in newsletter.validar(_guion(percha_url="https://ejemplo.com/otra"), TEXTO))


def test_la_pieza_tiene_portada_percha_cuatro_frases_y_cierre(cfg):
    p = newsletter.a_pieza(cfg, _guion(), "2026-11-05-7", "2026-11-05", TEXTO)
    assert [d.tipo for d in p.guion.diapositivas] == ["portada", "actualidad", "cita", "cita", "cita", "cita", "cierre"]
    assert p.eleccion.formato == "newsletter" and not p.libros
    assert p.guion.pie_instagram.endswith("Léelo entero en folioeditorial.substack.com (enlace en la bio).")
    assert any("Frases de reserva" in a for a in p.avisos)          # las dos de reserva quedan a la vista
    assert p.fuentes[1].url.startswith("https://www.liberation.fr/")
    sin_percha = newsletter.a_pieza(cfg, _guion(percha="", percha_url=""), "2026-11-05-8", "2026-11-05", TEXTO)
    assert "actualidad" not in [d.tipo for d in sin_percha.guion.diapositivas] and len(sin_percha.fuentes) == 1


def test_render_de_cada_diapositiva(cfg_diseno):
    cfg = cfg_diseno
    p = newsletter.a_pieza(cfg, _guion(), "2026-11-05-7", "2026-11-05", TEXTO)
    newsletter.guardar_foto(cfg, _jpg((800, 1000)))
    pl = render.Plantillas(cfg)
    portada = pl.html_diapositiva(p, 1)
    assert "diapositiva--nl_portada" in portada and "Opinión" in portada and "Antonio J. Rodríguez" in portada
    assert "Director editorial de Alighieria" in portada and "nl-autor__foto" in portada
    assert '2026 es el año en que más he escrito, y en el que <span class="remate">menos he escrito</span></h1>' in portada
    assert "Por qué ahora" in pl.html_diapositiva(p, 2)
    primera, segunda = pl.html_diapositiva(p, 3), pl.html_diapositiva(p, 4)
    assert "nl-par" not in primera and "nl-par" in segunda          # alternan pluma y papel
    assert '<span class="remate">borrando</span>' in primera
    cierre = pl.html_diapositiva(p, 7)
    assert "Léelo entero en folioeditorial.substack.com" in cierre and "La newsletter de Folio" in cierre
    assert "colofon" in pl.html_diapositiva(p, 8)


def _jpg(tam):
    b = BytesIO()
    Image.new("RGB", tam, (120, 110, 100)).save(b, "PNG")
    return b.getvalue()


def test_la_foto_de_quien_firma_se_guarda_cuadrada(cfg):
    ruta = newsletter.guardar_foto(cfg, _jpg((800, 1200)))
    with Image.open(ruta) as im:
        assert im.size == (600, 600) and im.format == "JPEG"


def test_editar_a_mano_con_sus_reglas_sin_firma_ni_comillas_dentro(cfg):
    """4/11, en producción: la edición a mano aplicaba las reglas de las piezas con libro (7 diapositivas, «idea»,
    12 palabras, comillas), metía la píldora en el texto y añadía «Folio.» al cierre."""
    from folio import edicion
    from folio.imagenes.editorial import nombres_de_pieza
    p = newsletter.a_pieza(cfg, _guion(), "2026-11-05-7", "2026-11-05", TEXTO)
    assert edicion.validar(cfg, p, p.guion) == []
    nueva, avisos = edicion.editar_diapositiva(cfg, p, 2, "El Goncourt retiró a Orélien y el ganador habló de la IA.")
    assert avisos == []                                   # la percha se puede reescribir
    nueva, avisos = edicion.editar_diapositiva(cfg, p, 7, "La literatura va a sobrevivir. COMO SEA.")
    assert avisos == [] and nueva.guion.diapositivas[6].texto == "La literatura va a sobrevivir. COMO SEA."   # sin «Folio.»
    _, avisos = edicion.editar_diapositiva(cfg, p, 3, "A escribir se aprende tachando")
    assert any("letra por letra" in a for a in avisos)    # las frases siguen siendo literales
    # «COMO SEA» en mayúsculas no hace de «sea» un nombre propio que las escenas no puedan usar
    assert "sea" not in nombres_de_pieza(p)


def test_opinion_de_otra_firma_con_su_foto_y_sin_enlace(cfg_diseno):
    """7/11 («quiero meter un tema de opinión de Diego… es básicamente como la newsletter del jueves»): el mismo carrusel
    con otra firma; sin enlace, el cierre enseña su nombre y su cargo y el pie no inventa una dirección."""
    cfg = cfg_diseno
    f = newsletter.guardar_firmante(cfg, "Diego Prueba", "Fundador de Alighieria")
    assert newsletter.firmante(cfg, f.slug).nombre == "Diego Prueba"
    assert [x.slug for x in newsletter.firmantes(cfg)] == [newsletter.CASA, "diego-prueba"]
    newsletter.guardar_foto(cfg, _jpg((800, 1000)), f.slug)
    assert newsletter.ruta_foto(cfg, f.slug).exists() and not newsletter.ruta_foto(cfg).exists()
    p = newsletter.a_pieza(cfg, _guion(), "2026-11-07-3", "2026-11-07", TEXTO, firma=f, formato=newsletter.OPINION)
    assert p.eleccion.formato == "opinion" and p.firmante.slug == "diego-prueba"
    assert "Léelo entero" not in p.guion.pie_instagram and "substack" not in p.guion.pie_instagram
    pl = render.Plantillas(cfg)
    portada = pl.html_diapositiva(p, 1)
    assert "Diego Prueba" in portada and "Fundador de Alighieria" in portada and "Antonio J." not in portada
    assert "firmantes/diego-prueba" in portada                       # su foto, no la de la casa
    cierre = pl.html_diapositiva(p, 7)
    assert "Léelo entero" not in cierre and "Diego Prueba" in cierre and "Fundador de Alighieria" in cierre
    # Con dónde se publica, el cierre lo dice
    g = newsletter.guardar_firmante(cfg, "Diego Prueba", "Fundador", "El blog de Diego", "https://diego.example/")
    p2 = newsletter.a_pieza(cfg, _guion(), "2026-11-07-4", "2026-11-07", TEXTO, firma=g, formato=newsletter.OPINION)
    assert "Léelo entero en diego.example" in pl.html_diapositiva(p2, 7)
    assert p2.guion.pie_instagram.endswith("Léelo entero en diego.example (enlace en la bio).")
