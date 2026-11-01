"""Temas que propone la redacción al jefe de cultura (2/11): noticias del tema, propuesta, pieza en la mesa y madrugada."""

from datetime import datetime, timezone

import httpx
import pytest

from folio import temas
from folio.almacen import Almacen
from folio.etapas import EtapasGuardadas
from folio.modelos import HistoriaElegida, InformeDiario, LibroCandidato, SeleccionJefe

PARRAFO = "<p>" + "Los traductores literarios de Francia han convocado una huelga contra las tarifas. " * 12 + "</p>"
HTML = f"<html><head><title>Huelga de traductores</title></head><body><article>{PARRAFO}</article></body></html>"


def _cliente():
    def manejar(req: httpx.Request) -> httpx.Response:
        if "bloquea" in req.url.host:
            return httpx.Response(403)
        if "corto" in req.url.host:
            return httpx.Response(200, text="<html><body><p>Poco.</p></body></html>")
        return httpx.Response(200, text=HTML)
    return httpx.Client(transport=httpx.MockTransport(manejar))


class LLMFalso:
    def __init__(self, cfg, buscadas=()):
        self.cfg, self.buscadas, self.llamadas, self.trazas = cfg, list(buscadas), [], []

    def con_busqueda(self, paso, prompt, **k):
        self.llamadas.append(paso)
        return "texto de la búsqueda", set(self.buscadas)

    def estructurado(self, paso, mensajes, esquema, **k):
        self.llamadas.append(paso)
        if esquema is temas._FuentesLLM:
            return esquema(fuentes=[{"medio": "Le Monde", "titulo": "Grève", "url": u} for u in [*self.buscadas, "https://inventada.org/x"]]), ""
        assert "[pegar" not in mensajes[0]["content"] and "Línea editorial de Folio" in mensajes[0]["content"]
        return HistoriaElegida(formato="dialogo", historia_id="otro", titular="Traducir también es escribir",
                               de_que_se_habla="Huelga.", cuestion_de_fondo="Quién cobra por las palabras.",
                               libros_candidatos=[LibroCandidato(titulo="Lo que se pierde", titulo_original="Lo que se pierde",
                                                                 idioma_original="español", autor="Ana Pérez")],
                               por_que="Porque sí."), ""


def test_los_enlaces_que_sirven_y_si_ninguno_se_busca_en_la_web(cfg):
    llm = LLMFalso(cfg)
    fuentes, avisos = temas.fuentes_del_tema(llm, cfg, "La huelga de traductores", ["https://bloquea.org/a", "https://bueno.org/b"], _cliente())
    assert [f.url for f in fuentes] == ["https://bueno.org/b"] and fuentes[0].titulo == "Huelga de traductores"
    assert any("403" in a for a in avisos) and llm.llamadas == []           # con un enlace bueno no se busca
    llm = LLMFalso(cfg, buscadas=["https://lemonde.fr/greve", "https://corto.org/c"])
    fuentes, avisos = temas.fuentes_del_tema(llm, cfg, "La huelga de traductores", [], _cliente())
    assert [f.url for f in fuentes] == ["https://lemonde.fr/greve"] and fuentes[0].medio == "Le Monde"
    assert any("inventada" in a for a in avisos) and any("sin texto suficiente" in a for a in avisos)


def test_proponer_ahora_deja_una_pieza_pendiente_en_la_mesa(cfg, monkeypatch):
    from folio.pipeline import Pipeline
    a = Almacen(cfg.ruta_db)
    inf = InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=timezone.utc), stats={},
                        top_historias=[], piezas=[], coste_total_usd=0)
    eid = a.registrar(inf)
    llm = LLMFalso(cfg, buscadas=["https://lemonde.fr/greve"])
    monkeypatch.setattr(temas, "_cliente", _cliente)
    monkeypatch.setattr(Pipeline, "_verificar", lambda self, pieza, reservados: True)
    monkeypatch.setattr(Pipeline, "_cubiertas_de", lambda self, pieza: None)
    tid = a.guardar_tema("La huelga de traductores en Francia", [], "ahora")
    pieza, _ = temas.crear_pieza(cfg, a, eid, tid, llm)
    assert pieza.id == "2026-11-02-1" and pieza.estado == "pendiente" and pieza.historia_id == f"tema-{tid}"
    assert pieza.eleccion.historia_id == f"tema-{tid}" and pieza.eleccion.formato == "dialogo"
    assert [p.id for p, _ in a.piezas(eid)] == ["2026-11-02-1"]
    t = a.temas()[0]
    assert (t.estado, t.pieza_id, t.fecha) == ("en_mesa", "2026-11-02-1", "2026-11-02")
    etapas = EtapasGuardadas(cfg.dir_cache("2026-11-02"))
    assert f"tema-{tid}" in {h.id for h in etapas.historias()[0]} and etapas.textos(f"tema-{tid}")   # para «Proceder»
    # Sin noticias que se lean, el tema queda fallido con el motivo
    tid2 = a.guardar_tema("Algo de lo que no hay nada", ["https://bloquea.org/a"], "ahora")
    with pytest.raises(temas.SinFuentes):
        temas.crear_pieza(cfg, a, eid, tid2, LLMFalso(cfg))
    assert next(x for x in a.temas() if x.id == tid2).estado == "fallido"


def test_la_madrugada_marca_los_temas_elegidos_y_los_que_no(cfg):
    from folio.pipeline import Pipeline
    a = Almacen(cfg.ruta_db)
    t1, t2 = a.guardar_tema("Tema uno de prueba", [], "manana"), a.guardar_tema("Tema dos de prueba", [], "manana")
    h1, h2 = temas.historia(t1, "Tema uno de prueba", []), temas.historia(t2, "Tema dos de prueba", [])
    e = HistoriaElegida(formato="lateral", historia_id=h1.id, titular="T", de_que_se_habla="D", cuestion_de_fondo="C",
                        libros_candidatos=[], por_que="P")
    tuberia = Pipeline(cfg, "2026-11-03", llm=LLMFalso(cfg))
    tuberia._marcar_temas(SeleccionJefe(elegidas=[e], aviso="El dos no se sostiene"), [h1, h2])
    estados = {t.id: (t.estado, t.pieza_id) for t in a.temas()}
    assert estados[t1] == ("en_mesa", "2026-11-03-1") and estados[t2] == ("no_elegido", None)
    assert "tema-" in temas.bloque_para_la_seleccion([h1]) and "(ninguno hoy)" in temas.bloque_para_la_seleccion([])
