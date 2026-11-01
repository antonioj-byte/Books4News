"""El friso de «Tres libros» (2/11, opción B elegida por el usuario): una ilustración en banda que cruza las tres
fichas de libro."""

from io import BytesIO

import pytest
from PIL import Image

from folio import arte as direccion, edicion, render
from folio.imagenes import friso, libres
from folio.informe import creditos_pie
from folio.modelos import Arte, Diapositiva, LibroGuion, Pieza

from datos import ELECCION, LIBRO, guion_valido


def _pieza(formato="balda", tres=True, **arte):
    g = guion_valido()
    titulos = ["Jerusalén", "Aprender a rezar en la era de la técnica", "Un viaje a la India"]
    if tres:
        g.diapositivas = [g.diapositivas[0], g.diapositivas[1],
                          *[Diapositiva(n=3 + i, tipo="libro", texto=f"En *{t}* pasa algo concreto.") for i, t in enumerate(titulos)],
                          Diapositiva(n=6, tipo="idea", texto="Lo que dicen juntos."), Diapositiva(n=7, tipo="cierre", texto="Empieza por *Jerusalén*. Folio.")]
        base = g.libros[0].model_dump()
        g.libros = [LibroGuion(**{**base, "titulo": t}) for t in titulos]
    libros = [LIBRO.model_copy(update={"titulo": t, "titulo_propuesto": t, "olid": f"OL{i}W"}) for i, t in enumerate(titulos)] if tres else [LIBRO]
    return Pieza(id="2026-11-02-7", fecha="2026-11-02", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION.model_copy(update={"formato": formato}), n_medios=3, libros=libros, guion=g,
                 arte=Arte(tono="reflexivo", recurso="foto", **arte))


def _jpg(cfg, clave):
    d = cfg.dir_cache("2026-11-02")
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    b = BytesIO()
    Image.new("RGB", (1414, 544), (20, 20, 30)).save(b, "JPEG")
    (libres.dir_imagenes(d) / f"{clave}.jpg").write_bytes(b.getvalue())
    return libres.dir_imagenes(d) / f"{clave}.jpg"


def test_cuando_lleva_friso(cfg):
    assert direccion.lleva_friso(cfg, _pieza(), "reflexivo")
    assert not direccion.lleva_friso(cfg, _pieza(), "grave")                 # nunca en las graves
    assert not direccion.lleva_friso(cfg, _pieza(formato="dialogo"), "reflexivo")
    assert not direccion.lleva_friso(cfg, _pieza(tres=False), "reflexivo")   # hacen falta las tres fichas


def test_estilo_y_recorte():
    from folio.config import cargar
    e = friso.estilo(cargar())
    assert "uninterrupted" in e and "panel" not in e.lower().replace("panels or", "")
    b = BytesIO()
    Image.new("RGB", (1440, 592), "white").save(b, "JPEG")
    im = friso.recortar(b.getvalue())
    assert im.size[0] < 1440 and im.size[1] < 592                            # sin el borde de papel ni la firma


def test_la_etapa_de_arte_dibuja_el_friso_y_el_pie_lo_acredita(cfg, monkeypatch):
    p = _pieza()
    dibujo = _jpg(cfg, "dibujo")
    monkeypatch.setattr(direccion, "escena_friso", lambda llm, cfg, pieza: ("A long night landscape with a lit window, a lamp over a table and a road to the sea.", "tres noches", None))
    monkeypatch.setattr(friso, "dibujar", lambda cfg, pid, escena, cliente=None: dibujo)
    monkeypatch.setattr(friso.editorial, "revisar", lambda llm, cfg, pid, d: None)
    a = p.arte
    direccion._friso(None, cfg, p, a, cfg.dir_cache(p.fecha))
    assert a.friso and a.friso_idea == "tres noches" and friso.de_pieza(p.id, cfg.dir_cache(p.fecha))
    assert any("Ilustración de las fichas" in c for c in creditos_pie(a))
    # Relanzar el arte de la pieza reutiliza el friso que ya tiene (no se paga otro)
    monkeypatch.setattr(friso, "dibujar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería dibujar")))
    otra_vez = Arte(tono="reflexivo", recurso="foto")
    direccion._friso(None, cfg, p, otra_vez, cfg.dir_cache(p.fecha))
    assert otra_vez.friso == a.friso
    # Con el tope del día lleno, no se dibuja otro
    otra = _pieza().model_copy(update={"id": "2026-11-02-8"})
    for i in range(cfg.pipeline.arte.friso.max_por_dia):
        friso.fijar(cfg.dir_cache(p.fecha), f"2026-11-02-{20 + i}", "x", dibujo)
    direccion._friso(None, cfg, otra, otra.arte, cfg.dir_cache(p.fecha))
    assert not otra.arte.friso and any("los del día" in x for x in otra.arte.avisos)


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


def test_cada_ficha_ensena_su_tercio(cfg_diseno):
    p = _pieza(friso="A long night landscape.")
    friso.fijar(cfg_diseno.dir_cache(p.fecha), p.id, "x", _jpg(cfg_diseno, "dibujo"))
    pl = render.Plantillas(cfg_diseno, url_medio=lambda r: "/api/medios/" + r.name)
    for n, k in ((3, 0), (4, 1), (5, 2)):
        html = pl.html_diapositiva(p, n)
        assert f"--k: {k};" in html and "2026-11-02-7-friso.jpg" in html and "con-friso" in html
    assert "class=\"friso\"" not in pl.html_diapositiva(p, 6)
    # Si una edición deja dos fichas de libro, no se pinta (saldría cortado)
    p.guion.diapositivas[3].tipo = "idea"
    assert "class=\"friso\"" not in pl.html_diapositiva(p, 3)


def test_el_chat_quita_o_rehace_el_friso(cfg, monkeypatch):
    base = dict(enfoque_x=50, enfoque_y=50, composicion="", consultas=[], persona="", estilo="", material="", como="",
                destacado="", antetitulo="", acento="", libro="", editorial="", isbn="")
    p = _pieza(friso="A long night landscape.")
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, edicion.AccionImagen(tipo="friso", escena="ninguno", **base))
    assert nueva and nueva.arte.friso is None and "Quitado" in nota
    dibujo = _jpg(cfg, "dibujo")
    monkeypatch.setattr(friso, "dibujar", lambda cfg, pid, escena, cliente=None: dibujo)
    monkeypatch.setattr(friso.editorial, "revisar", lambda llm, cfg, pid, d: None)
    escena = "A quiet night landscape with a lit window on the left, a lamp over a table and a road to the sea on the right."
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, edicion.AccionImagen(tipo="friso", escena=escena, **base))
    assert nueva and nueva.arte.friso == escena and "Friso nuevo" in nota
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(formato="dialogo"), edicion.AccionImagen(tipo="friso", escena=escena, **base))
    assert nada is None and "Tres libros" in nota
