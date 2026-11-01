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
    def __init__(self, cfg, buscadas=(), preguntar=False):
        self.cfg, self.buscadas, self.llamadas, self.trazas = cfg, list(buscadas), [], []
        self.preguntar, self.prompts = preguntar, []

    def con_busqueda(self, paso, prompt, **k):
        self.llamadas.append(paso)
        return "texto de la búsqueda", set(self.buscadas)

    def estructurado(self, paso, mensajes, esquema, **k):
        self.llamadas.append(paso)
        if esquema is temas._FuentesLLM:
            return esquema(fuentes=[{"medio": "Le Monde", "titulo": "Grève", "url": u} for u in [*self.buscadas, "https://inventada.org/x"]]), ""
        assert "[pegar" not in mensajes[0]["content"] and "Línea editorial de Folio" in mensajes[0]["content"]
        self.prompts.append(mensajes[0]["content"])
        if self.preguntar and "Redacción:" not in mensajes[0]["content"]:
            return temas.RespuestaJefeTema(respuesta="Necesito saber el enfoque.", preguntas=["¿Perfil o noticia?"], propuesta=None), ""
        titular = "Un perfil del traductor" if "Redacción:" in mensajes[0]["content"] else "Traducir también es escribir"
        return temas.RespuestaJefeTema(respuesta="Propongo un diálogo.", preguntas=[], propuesta=HistoriaElegida(
                               formato="dialogo", historia_id="otro", titular=titular,
                               de_que_se_habla="Huelga.", cuestion_de_fondo="Quién cobra por las palabras.",
                               libros_candidatos=[LibroCandidato(titulo="Lo que se pierde", titulo_original="Lo que se pierde",
                                                                 idioma_original="español", autor="Ana Pérez")],
                               por_que="Porque sí.")), ""


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
    pieza = temas.crear_pieza(cfg, a, eid, tid, llm).pieza
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


def test_el_jefe_pregunta_y_la_replica_rehace_la_propuesta(cfg, monkeypatch):
    """2/11 («¿quizá necesita preguntarme a mí? añadimos la opción de la réplica»)."""
    from folio.pipeline import Pipeline
    a = Almacen(cfg.ruta_db)
    eid = a.registrar(InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=timezone.utc), stats={},
                                    top_historias=[], piezas=[], coste_total_usd=0))
    monkeypatch.setattr(temas, "_cliente", _cliente)
    monkeypatch.setattr(Pipeline, "_verificar", lambda self, pieza, reservados: True)
    monkeypatch.setattr(Pipeline, "_cubiertas_de", lambda self, pieza: None)
    llm = LLMFalso(cfg, buscadas=["https://lemonde.fr/greve"], preguntar=True)
    tid = a.guardar_tema("Gonçalo Tavares gana el Formentor", [], "ahora")
    r = temas.crear_pieza(cfg, a, eid, tid, llm)
    assert r.pieza is None and r.preguntas == ["¿Perfil o noticia?"] and a.piezas(eid) == []
    t = a.temas()[0]
    assert t.estado == "pregunta" and t.conversacion[-1]["rol"] == "jefe" and "Perfil o noticia" in t.conversacion[-1]["texto"]
    busquedas = llm.llamadas.count("tema-fuentes")
    # La redacción contesta: el jefe propone (sin volver a buscar las noticias)
    r = temas.crear_pieza(cfg, a, eid, tid, llm, replica="Un perfil, con sus obras publicadas en España")
    assert r.pieza is not None and r.pieza.eleccion.titular == "Un perfil del traductor"
    assert llm.llamadas.count("tema-fuentes") == busquedas
    assert "Redacción: Un perfil, con sus obras publicadas en España" in llm.prompts[-1]
    pid = r.pieza.id
    # Otra réplica a la propuesta: la pieza pendiente se rehace en el sitio (versión nueva, mismo id)
    r = temas.crear_pieza(cfg, a, eid, tid, llm, replica="Mejor con otro libro")
    assert r.pieza.id == pid and [p.id for p, _ in a.piezas(eid)] == [pid] and a.pieza(eid, pid)[1] == 2
    assert [x["rol"] for x in a.temas()[0].conversacion] == ["jefe", "redaccion", "jefe", "redaccion", "jefe"]


def test_si_ningun_libro_pasa_el_jefe_propone_otros_una_vez(cfg, monkeypatch):
    """2/11: el perfil de Tavares se quedó sin libro (todos anteriores a 2024). En los temas no se exige novedad, y si
    aun así ningún libro pasa, el jefe ve los motivos y propone otros."""
    from folio.modelos import LibroDescartado
    from folio.pipeline import Pipeline
    a = Almacen(cfg.ruta_db)
    eid = a.registrar(InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=timezone.utc), stats={},
                                    top_historias=[], piezas=[], coste_total_usd=0))
    monkeypatch.setattr(temas, "_cliente", _cliente)
    vistos = []

    def verificar(self, pieza, reservados):
        vistos.append(self.sin_novedad)
        if len(vistos) == 1:
            pieza.libros_descartados = [LibroDescartado(titulo="El Reino", autor="Tavares", motivo="sin edición en castellano")]
            return False
        return True
    monkeypatch.setattr(Pipeline, "_verificar", verificar)
    monkeypatch.setattr(Pipeline, "_cubiertas_de", lambda self, pieza: None)
    llm = LLMFalso(cfg, buscadas=["https://lemonde.fr/greve"])
    tid = a.guardar_tema("Gonçalo Tavares gana el Formentor", [], "ahora")
    r = temas.crear_pieza(cfg, a, eid, tid, llm)
    assert vistos == [True, True] and r.pieza.estado == "pendiente"
    assert "Verificación de libros: Ninguno de tus libros pasó" in llm.prompts[-1] and "El Reino" in llm.prompts[-1]
    assert [x["rol"] for x in a.temas()[0].conversacion] == ["jefe", "verificacion", "jefe"]


def test_un_tema_solo_espera_al_pipeline_del_dia(tmp_path):
    """2/11: «Proponer ahora» no choca con «Proceder», el render ni la nevera; solo con `folio run`."""
    import sys
    import time
    from folio_api.ejecutor import Ejecutor
    dormir = [sys.executable, "-c", "import time; time.sleep(1.5)"]
    e = Ejecutor(tmp_path, comando=dormir)
    assert e.lanzar([dormir])
    assert e.ocupado() and not e.con_pipeline()
    while e.ocupado():
        time.sleep(0.1)
    e2 = Ejecutor(tmp_path, comando=[*dormir, "run"])
    assert e2.lanzar()
    assert e2.con_pipeline()
    while e2.ocupado():
        time.sleep(0.1)
    assert not e2.con_pipeline()


def test_guardar_json_es_atomico(tmp_path):
    from folio.etapas import cargar_json, guardar_json
    guardar_json(tmp_path / "a.json", {"x": 1})
    guardar_json(tmp_path / "a.json", {"x": 2})
    assert cargar_json(tmp_path / "a.json") == {"x": 2}
    assert [f.name for f in tmp_path.iterdir()] == ["a.json"]


def test_embedder_suelta_el_modelo_si_se_pide(tmp_path):
    """«Proceder» en paralelo (2/11): cada proceso suelta el modelo de embeddings en cuanto calcula lo suyo."""
    import numpy as np
    from folio.ingesta.agrupacion import Embedder

    class Motor:
        def embed(self, textos, batch_size=32):
            return [np.ones(4) for _ in textos]

    e = Embedder("intfloat/multilingual-e5-large", tmp_path)
    e._cargar = lambda: setattr(e, "_motor", Motor()) or e._motor
    e.liberar = True
    assert set(e.vectores({"a": "uno", "b": "dos"})) == {"a", "b"}
    assert e._motor is None
    assert set(e.vectores({"a": "uno"})) == {"a"}                     # de la caché, sin modelo
    assert not [f for f in tmp_path.iterdir() if f.name.endswith(".tmp.npz")]
