"""Formato «recomendado» (catálogo de las independientes), citas de la crítica y radar del libro. Sin red ni gasto."""

from datetime import date
from pathlib import Path

import httpx
import pytest

from folio import catalogo, guion, radar, seleccion
from folio.modelos import Diapositiva, Historia, LibroGuion, SeleccionJefe

from datos import ELECCION, guion_valido

FIXTURES = Path(__file__).parent / "fixtures"
URL_FICHA = "https://www.todostuslibros.com/libros/los-adversarios_979-13-88412-02-8"


def test_lee_las_novedades_de_una_editorial():
    libros = catalogo.leer_novedades((FIXTURES / "ttl_novedades.html").read_text())
    assert libros[0].titulo == "Los adversarios" and libros[0].autor == "Michael Crummey"
    assert libros[0].editorial == "Impedimenta" and libros[0].mes == "2026-10" and libros[0].isbn == "9791388412028"
    assert len(libros) == 3


def test_lee_la_ficha_con_la_critica_aparte():
    f = catalogo.leer_ficha((FIXTURES / "ttl_ficha.html").read_text(), URL_FICHA)
    assert f.titulo == "Los adversarios" and f.autores == ["Michael Crummey"] and f.traductores == ["Diego de los Santos"]
    assert f.editorial == "Impedimenta" and f.fecha == "2026-10-19" and f.isbn == "9791388412028"
    assert f.sinopsis.startswith("Una deslumbrante epopeya") and "CRÍTICA" not in f.sinopsis
    assert f.critica.startswith("Uno de los mejores libros de 2023") and "The New Yorker" in f.critica
    libro = catalogo.libro_de_ficha(f)
    assert libro.edicion_es == "si" and libro.edicion_es_detalle.anio == "2026" and libro.fuentes_verificacion == ["todostuslibros"]
    (fuente, _), (critica, texto) = catalogo.textos(f)
    assert not fuente.critica and critica.critica and texto == f.critica


def _transporte(pedidas):
    def manejar(req: httpx.Request) -> httpx.Response:
        pedidas.append(str(req.url))
        if req.url.path == "/editorial/impedimenta":
            return httpx.Response(200, text='<a href="https://www.todostuslibros.com/editoriales/impedimenta_79803">x</a>')
        if req.url.path.endswith("/novedades"):
            return httpx.Response(200, text=(FIXTURES / "ttl_novedades.html").read_text())
        if req.url.path.startswith("/libros/"):
            return httpx.Response(200, text=(FIXTURES / "ttl_ficha.html").read_text())
        return httpx.Response(404)
    return httpx.MockTransport(manejar)


def _cfg_catalogo(cfg):
    (cfg.raiz / "config").mkdir(exist_ok=True)
    (cfg.raiz / "config" / "editoriales_independientes.yaml").write_text(
        "- {nombre: Impedimenta}\n- {nombre: Kalandraka, excluir: infantil}\n", encoding="utf-8")
    cfg.pipeline.catalogo.pausa_s = 1.0
    return cfg


def test_candidatos_del_catalogo_con_cache(cfg, monkeypatch):
    monkeypatch.setattr(catalogo.time, "sleep", lambda s: None)
    _cfg_catalogo(cfg)
    pedidas = []
    cat = catalogo.Catalogo(cfg, httpx.Client(transport=_transporte(pedidas)), hoy=date(2026, 11, 1))
    hs, avisos = catalogo.candidatos(cfg, date(2026, 11, 1), cat=cat)
    assert [h.id for h in hs] == ["catalogo-9791388412028"] and avisos == []
    assert hs[0].carril == "catalogo" and "Con crítica" in hs[0].resumen_es
    assert not any("kalandraka" in u for u in pedidas)                 # la infantil queda fuera
    # Al día siguiente todo sale de la caché: ni una petición
    pedidas.clear()
    cat2 = catalogo.Catalogo(cfg, httpx.Client(transport=_transporte(pedidas)), hoy=date(2026, 11, 2))
    assert catalogo.candidatos(cfg, date(2026, 11, 2), cat=cat2)[0] and pedidas == []
    # Los libros ya usados no se proponen; los de hace más de seis meses, tampoco
    assert catalogo.candidatos(cfg, date(2026, 11, 2), lambda t, a: True, cat=cat2)[0] == []
    assert catalogo.candidatos(cfg, date(2027, 6, 1), cat=catalogo.Catalogo(cfg, httpx.Client(transport=_transporte([])), hoy=date(2027, 6, 1)))[0] == []
    assert catalogo.ficha_guardada(cfg, hs[0].id).titulo == "Los adversarios"


def test_ante_un_403_se_para(cfg, monkeypatch):
    monkeypatch.setattr(catalogo.time, "sleep", lambda s: None)
    _cfg_catalogo(cfg)
    pedidas = []
    cliente = httpx.Client(transport=httpx.MockTransport(lambda req: pedidas.append(1) or httpx.Response(403)))
    hs, avisos = catalogo.candidatos(cfg, date(2026, 11, 1), cat=catalogo.Catalogo(cfg, cliente, hoy=date(2026, 11, 1)))
    assert hs == [] and "403" in avisos[0] and len(pedidas) == 1


def _guion_recomendado(cita="«Magnífica», dice Kirkus Reviews."):
    return guion_valido(diapositivas=[
        Diapositiva(n=1, tipo="portada", texto="Una guerra de hermanos en la costa helada",
                    subtitulo="Michael Crummey convierte Terranova en un Caín y Abel de mercaderes en Los adversarios."),
        Diapositiva(n=2, tipo="libro", texto="Los adversarios cuenta la guerra de Abe Strapp y su hermana por la bahía."),
        Diapositiva(n=3, tipo="actualidad", texto=f"La crítica la ha celebrado: {cita}"),
        Diapositiva(n=4, tipo="idea", texto="El rencor heredado es una empresa familiar que nunca quiebra."),
        Diapositiva(n=5, tipo="cierre", texto="Los adversarios, de Michael Crummey. Léela. Folio."),
    ], pie_instagram="Michael Crummey y Los adversarios: " + " ".join(["palabra"] * 95),
        libros=[LibroGuion(titulo="Los adversarios", autor="Michael Crummey", editorial_espanola="Impedimenta",
                           traductor="Diego de los Santos", edicion_original="inglés")],
        fuentes_noticia=[f"Todos tus libros {URL_FICHA}"])


def test_citas_de_la_critica_solo_si_estan_letra_por_letra(cfg):
    f = catalogo.leer_ficha((FIXTURES / "ttl_ficha.html").read_text(), URL_FICHA)
    libros, tx = [catalogo.libro_de_ficha(f)], catalogo.textos(f)
    fuentes = [x for x, _ in tx]
    assert guion.citas_de_la_critica(_guion_recomendado(), libros, tx) == []   # una palabra suelta no basta
    g = _guion_recomendado("«una potente interpretación de las formas en que la desesperanza maligna y odiosa de un rencor puede corromper todo lo que toca», según The New Yorker.")
    criticas = guion.citas_de_la_critica(g, libros, tx)
    assert len(criticas) == 1 and criticas[0].tipo == "critica" and criticas[0].fuente.endswith("#critica")
    ok = frozenset(guion.normalizar(c.texto) for c in criticas)
    assert guion.validar(cfg, g, libros, fuentes, frozenset(), ok, "recomendado") == []
    # Una frase inventada se rechaza aunque se atribuya a la crítica
    inventada = _guion_recomendado("«la novela canadiense más importante del siglo», según The New Yorker.")
    assert guion.citas_de_la_critica(inventada, libros, tx) == []
    assert any("Texto entre comillas" in e for e in guion.validar(cfg, inventada, libros, fuentes, frozenset(), frozenset(), "recomendado"))
    # Fuera del recomendado, el pie sigue teniendo que citar un medio
    assert any("citar el medio" in e for e in guion.validar(cfg, g, libros, fuentes, frozenset(), ok, "lateral"))


def test_la_seleccion_con_catalogo(cfg):
    h = Historia(id="h1", articulos=[], n_medios=1, medios=["El País"], titular_es="T", resumen_es="R")
    f = catalogo.leer_ficha((FIXTURES / "ttl_ficha.html").read_text(), URL_FICHA)
    hc = catalogo.historia(f)
    prompts = []

    class LLMJefe:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            prompts.append(mensajes[0]["content"])
            e = ELECCION.model_copy(update={"historia_id": "h1", "libros_candidatos": ELECCION.libros_candidatos * 2})
            rec = e.model_copy(update={"formato": "recomendado", "historia_id": hc.id, "libros_candidatos": e.libros_candidatos[:1]})
            mal = e.model_copy(update={"formato": "recomendado"})        # recomendado que no sale del catálogo
            return SeleccionJefe(elegidas=[rec, mal] + [e.model_copy(update={"formato": f}) for f in ("lateral", "lateral", "dialogo", "dialogo", "edicion", "edicion")], reserva=[]), []

    sel, avisos = seleccion.seleccionar(LLMJefe(cfg), [h, hc], "2026-11-01")
    assert "1 de libro recomendado" in prompts[0] and "Los adversarios, de Michael Crummey" in prompts[0]
    assert sel.elegidas[0].formato == "recomendado" and len(sel.elegidas) == 7
    assert any("el recomendado del catálogo" in a for a in avisos)


def test_radar(cfg):
    hs = [Historia(id=f"e{i}", articulos=[], n_medios=1, medios=["ActuaLitté"], titular_es=f"T{i}", resumen_es="R",
                   carril="editorial" if i < 2 else "radar") for i in range(3)]
    hs.append(Historia(id="a1", articulos=[], n_medios=3, medios=["X"], titular_es="Actualidad", resumen_es="R"))
    vistos = []

    class LLMRadar:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            vistos.append(mensajes[0]["content"])
            t = dict(titular="Un manuscrito de Poe sobrevive a dos incendios", de_que_se_habla="x", cuestion_de_fondo="y", por_que="z",
                     protagonista="Edgar Allan Poe")
            return radar.RadarLLM(temas=[radar.TemaRadar(historia_id=i, **t) for i in ("e2", "e2", "a1", "inventada")]), []

    sel = SeleccionJefe(elegidas=[ELECCION.model_copy(update={"historia_id": "e0"})], reserva=[])
    temas, avisos = radar.temas(LLMRadar(cfg), hs, sel)
    assert [t.historia_id for t in temas] == ["e2"] and temas[0].formato == "radar" and temas[0].libros_candidatos == []
    assert temas[0].protagonista == "Edgar Allan Poe"
    assert "id: e1" in vistos[0] and "id: e2" in vistos[0] and "id: e0" not in vistos[0] and "id: a1" not in vistos[0]
    assert len(avisos) == 3
    cfg.pipeline.radar.activo = False
    assert radar.temas(LLMRadar(cfg), hs, sel) == ([], [])


def test_el_archivo_de_editoriales_es_valido():
    from folio.config import RAIZ
    eds = catalogo.editoriales(RAIZ)
    assert len(eds) > 100 and all(e.nombre for e in eds) and not any(e.excluir for e in eds)


def test_la_ruta_de_la_editorial_tiene_que_casar_con_el_nombre():
    assert catalogo.ruta_que_casa("Impedimenta", ["masson_6404", "impedimenta_79803"]) == "impedimenta_79803"
    assert catalogo.ruta_que_casa("Pre-Textos", ["plaza-janes_84460"]) is None
    assert catalogo.ruta_que_casa("Libros del Asteroide", ["libros-del-asteroide-s-l-u_81623"]) == "libros-del-asteroide-s-l-u_81623"
    assert catalogo.ruta_que_casa("Errata Naturae", ["desconocido_173060"]) is None


def test_las_de_referencia_se_intercalan_y_son_75():
    from folio.config import RAIZ
    eds = catalogo.editoriales(RAIZ)
    assert sum(e.referencia for e in eds) == 75
    assert len({e.nombre for e in eds}) == len(eds)
