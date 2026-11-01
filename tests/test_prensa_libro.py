"""Prensa del libro (2/11, «si es una novedad editorial, que busque varias fuentes; seguramente hay más de una entrevista»)."""

import httpx

from folio import temas
from folio.modelos import FuenteNoticia, Historia, Pieza
from folio.pipeline import Pipeline

from datos import ELECCION, LIBRO

HTML = "<html><head><title>Entrevista</title></head><body><article><p>" + "Hannah Arendt y su Eichmann en Jerusalén vuelven a las librerías. " * 20 + "</p></article></body></html>"


class LLM:
    def __init__(self, cfg):
        self.cfg, self.pasos, self.trazas = cfg, [], []

    def con_busqueda(self, paso, prompt, **k):
        self.pasos.append(paso)
        assert "Hannah Arendt" in prompt and "[pegar" not in prompt
        return "resultados", {"https://elpais.com/entrevista", "https://lavanguardia.com/resena", "https://ya.es/estaba"}

    def estructurado(self, paso, mensajes, esquema, **k):
        self.pasos.append(paso)
        return esquema(fuentes=[{"medio": m, "titulo": "T", "url": u} for m, u in (
            ("El País", "https://elpais.com/entrevista"), ("La Vanguardia", "https://lavanguardia.com/resena"),
            ("Ya", "https://ya.es/estaba"), ("Inventado", "https://inventado.org/x"))]), ""


def test_mundo_del_libro_busca_prensa_y_la_congela(cfg, monkeypatch):
    monkeypatch.setattr(temas, "_cliente", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=HTML))))
    llm = LLM(cfg)
    t = Pipeline(cfg, "2026-11-02", llm=llm)
    h = Historia(id="e1", articulos=[], n_medios=1, medios=["ActuaLitté"], titular_es="T", resumen_es="R", carril="editorial")
    p = Pieza(id="2026-11-02-1", fecha="2026-11-02", estado="pendiente", historia_id="e1", n_medios=1, libros=[LIBRO],
              eleccion=ELECCION.model_copy(update={"formato": "edicion"}))
    previos = [(FuenteNoticia(medio="Ya", titulo="T", url="https://ya.es/estaba", acceso="abierto"), "texto")]
    textos = t._prensa_del_libro(p, h, previos)
    assert [f.medio for f, _ in textos] == ["Ya", "El País", "La Vanguardia"]      # sin repetir ni la inventada
    assert all(f.prensa for f, _ in textos[1:]) and any("2 artículos más" in a for a in p.avisos)
    assert [f.url for f, _ in t.etapas.textos("e1")] == [f.url for f, _ in textos]     # congelados: los ve la comprobación de hechos
    pasos = len(llm.pasos)
    assert t._prensa_del_libro(p, h, textos) == textos and len(llm.pasos) == pasos      # ya buscada: no vuelve a buscar
    lateral = p.model_copy(update={"eleccion": ELECCION})
    assert t._prensa_del_libro(lateral, h, previos) == previos                          # en una lectura lateral, no
