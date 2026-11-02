"""La banda panorámica a sangre sobre tres diapositivas (2/11, opción B elegida por el usuario), con una persona real
solo a partir de su foto libre. Sin red ni gasto."""

from io import BytesIO

import pytest
from PIL import Image

from folio import edicion, render
from folio.imagenes import banda, libres, retratos
from folio.informe import creditos_pie
from folio.modelos import Arte, Diapositiva, Pieza

from datos import ELECCION, LIBRO, guion_valido

ESCENA = ("A huge night square full of tiny walkers, a lamp post on the left, a small closed booth with a padlock in "
          "the middle third and a quiet street with one lit window on the right.")


def _pieza(**arte):
    g = guion_valido()
    g.diapositivas = [g.diapositivas[0], g.diapositivas[1], Diapositiva(n=3, tipo="libro", texto=g.diapositivas[2].texto),
                      Diapositiva(n=4, tipo="idea", texto="Solo el chat secreto queda entre las dos personas que hablan."),
                      Diapositiva(n=5, tipo="idea", texto="La plaza se ve entera; la cabina, no."),
                      Diapositiva(n=6, tipo="idea", texto="Lo cerrado de verdad es la cerradura."),
                      g.diapositivas[-1].model_copy(update={"n": 7})]
    return Pieza(id="2026-11-01-9", fecha="2026-11-01", estado="propuesta", historia_id="h1", eleccion=ELECCION,
                 n_medios=3, libros=[LIBRO], guion=g, arte=Arte(tono="reflexivo", recurso="foto", acento="marcador", **arte))


def _accion(**k):
    base = dict(tipo="banda", enfoque_x=50, enfoque_y=50, composicion="", consultas=[], escena=ESCENA, persona="", estilo="",
                material="", como="", destacado="", antetitulo="", acento="", libro="", autor="", sin_castellano="",
                editorial="", isbn="", desde=4)
    return edicion.AccionImagen(**{**base, **k})


def _jpg(cfg, nombre, tam=(1440, 600)):
    d = cfg.dir_cache("2026-11-01")
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    b = BytesIO()
    Image.new("RGB", tam, (20, 20, 30)).save(b, "JPEG")
    ruta = libres.dir_imagenes(d) / f"{nombre}.jpg"
    ruta.write_bytes(b.getvalue())
    return ruta


def test_recorte_a_tres_diapositivas():
    for tam in ((1920, 1080), (1414, 544), (2400, 1000)):
        a, b = banda.a_proporcion(Image.new("RGB", tam)).size
        assert abs(a / b - 12 / 5) < 0.01


def test_estilo_con_y_sin_persona():
    from folio.config import cargar
    sin, con = banda.estilo(cargar(), False), banda.estilo(cargar(), True)
    assert "one sixth, one half and five sixths" in sin and "cut into" not in sin and "anonymous" in sin and "reference photo" not in sin
    assert "reference photo" in con and banda._ANONIMAS not in con


def test_solo_sobre_tres_seguidas_sin_portada_ni_cierre():
    tipos = ["portada", "actualidad", "libro", "idea", "idea", "idea", "cierre"]
    assert banda.diapositivas_validas(tipos, 4) is None
    assert banda.diapositivas_validas(tipos, 2) is None
    assert "cierre" in banda.diapositivas_validas(tipos, 5)
    assert banda.diapositivas_validas(tipos, 1) and banda.diapositivas_validas(tipos, 6)


def test_el_chat_pone_la_banda_y_el_pie_la_acredita(cfg, monkeypatch):
    dibujo = _jpg(cfg, "dibujo")
    pedidas = []
    monkeypatch.setattr(banda, "dibujar", lambda cfg, pid, escena, foto=None, cliente=None: pedidas.append(foto) or dibujo)
    monkeypatch.setattr(banda.editorial, "revisar", lambda llm, cfg, pid, d: None)
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion())
    assert nueva and nueva.arte.banda == ESCENA and nueva.arte.banda_desde == 4 and "4–6" in nota
    assert pedidas == [None]                                           # sin persona: desde el texto
    assert any("diapositivas 4–6" in c for c in creditos_pie(nueva.arte))
    # Quitarla
    sin, nota = edicion.aplicar_imagen(None, cfg, nueva, _accion(escena="ninguno"))
    assert sin and sin.arte.banda is None and "Quitada" in nota
    # Nunca sobre el cierre, ni con una escena con nombres propios
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion(desde=5))
    assert nada is None and "cierre" in nota
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion(escena=ESCENA.replace("a quiet street", "a quiet Telegram street")))
    assert nada is None and "no vale" in nota


def test_una_persona_real_solo_desde_su_foto_libre(cfg, monkeypatch):
    dibujo = _jpg(cfg, "dibujo")
    pedidas = []
    monkeypatch.setattr(banda, "dibujar", lambda cfg, pid, escena, foto=None, cliente=None: pedidas.append(foto) or dibujo)
    monkeypatch.setattr(banda.editorial, "revisar", lambda llm, cfg, pid, d: None)
    # Sin foto libre, no se pinta (nunca una cara desde cero)
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (None, "Sin retrato en Wikidata"))
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion(persona="Pavel Durov"))
    assert nada is None and "licencia libre" in nota and pedidas == []
    # Con su foto, la foto va de referencia y el pie lleva su crédito; la pieza pasa a revisión humana
    foto = _jpg(cfg, "2026-11-01-9-banda-retrato", (800, 1000))
    img = libres.ImagenLibre(archivo="commons:File:Durov.jpg", pagina="", url="", ancho=800, alto=1000, licencia="CC BY 2.0",
                             licencia_url=None, autor="TechCrunch", descripcion="", libre=True, motivo="", local=foto.name, fuente="Commons")
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (img, ""))
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion(persona="Pavel Durov", escena=ESCENA.replace("a small closed booth", "the man beside a small closed booth")))
    assert nueva and pedidas == [foto.read_bytes()] and "Pavel Durov" in nueva.arte.banda_credito
    assert "obra derivada" in nueva.arte.banda_credito and nueva.revision_humana and "parecido" in nota
    # El nombre de la persona no puede ir en la escena
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion(persona="Pavel Durov", escena=ESCENA + " Durov waits."))
    assert nada is None


def test_nunca_dos_caras(cfg, monkeypatch):
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería buscar")))
    autor = LIBRO.autores[0]
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(registro="foto_autor"), _accion(persona=autor))
    assert nada is None and "una sola vez" in nota


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_cada_diapositiva_ensena_su_tercio(cfg_diseno):
    p = _pieza(banda=ESCENA, banda_desde=4, banda_credito="generada con IA (Magnific) para Folio")
    banda.fijar(cfg_diseno.dir_cache(p.fecha), p.id, ESCENA, _jpg(cfg_diseno, "dibujo"), "x")
    pl = render.Plantillas(cfg_diseno, url_medio=lambda r: "/api/medios/" + r.name)
    for n, k in ((4, 0), (5, 1), (6, 2)):
        html = pl.html_diapositiva(p, n)
        assert f"--k: {k};" in html and "2026-11-01-9-banda.jpg" in html and "con-banda" in html
    for n in (3, 7):
        assert "class=\"banda\"" not in pl.html_diapositiva(p, n)
    # Si una edición la deja sobre el cierre, no se pinta
    p.guion.diapositivas[5].tipo = "cierre"
    assert "class=\"banda\"" not in pl.html_diapositiva(p, 4)
