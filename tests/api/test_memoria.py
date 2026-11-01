"""Memoria del feedback (folio.memoria, /api/memoria). Sin red ni gasto: el modelo está simulado."""

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from folio import edicion, informe, memoria
from folio.almacen import Almacen, Evaluacion
from folio.modelos import InformeDiario, Pieza, SeleccionJefe
from folio_api.main import crear_app

from datos import ELECCION, LIBRO, guion_valido


def _almacen_con_feedback(cfg) -> Almacen:
    p = Pieza(id="2026-11-01-1", fecha="2026-11-01", estado="propuesta", historia_id="h1", eleccion=ELECCION,
              n_medios=3, libros=[LIBRO], guion=guion_valido())
    inf = InformeDiario(fecha="2026-11-01", generado_en=datetime(2026, 11, 1, 5, tzinfo=timezone.utc), stats={}, top_historias=[],
                        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]), piezas=[p], coste_total_usd=0)
    informe.escribir(inf, cfg.dir_informes / "2026-11-01")
    a = Almacen(cfg.ruta_db)
    a.importar_informes(cfg.dir_informes)
    eid = a.ultima_ejecucion("2026-11-01")
    nueva, _ = edicion.editar_diapositiva(cfg, p, 1, "La obediencia se elige")
    a.guardar_version(eid, p.id, nueva, "manual", "a mano")
    a.anadir_mensaje(eid, p.id, "usuario", "El titular es demasiado largo")
    a.guardar_evaluacion(eid, p.id, Evaluacion(voz=2, publicaria=False, comentario="Nunca titulares tan largos"), 2)
    return a


def test_el_feedback_recoge_evaluacion_ediciones_y_chat(cfg):
    a = _almacen_con_feedback(cfg)
    datos = a.feedback("2026-10-20")
    assert len(datos) == 1 and datos[0]["pedidos_chat"] == ["El titular es demasiado largo"]
    assert datos[0]["ediciones"] == [{"diapositiva": "1 (portada)", "antes": "La obediencia también se elige", "despues": "La obediencia se elige"}]
    assert datos[0]["evaluacion"]["comentario"] == "Nunca titulares tan largos"
    bloque = memoria._bloque_feedback(datos)
    assert "¿la publicaría? no" in bloque and "antes: La obediencia también se elige" in bloque


class LLMFalso:
    def __init__(self, cfg, salida):
        self.cfg, self.salida, self.prompts = cfg, salida, []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.prompts.append(mensajes[0]["content"])
        return esquema.model_validate(self.salida), []


def test_analizar_guarda_y_refuerza_patrones(cfg):
    a = _almacen_con_feedback(cfg)
    patron = {"existente": 0, "patron": "Acorta los titulares", "evidencia": ["2026-11-01-1: quitó «también»"],
              "propuesta": "Titular de 8 palabras como máximo", "destino": "guionista"}
    llm = LLMFalso(cfg, {"patrones": [patron], "aviso": ""})
    ids, aviso, n = memoria.analizar(llm, cfg, a, 14, hoy=date(2026, 11, 2))
    assert n == 1 and len(ids) == 1 and "Nunca titulares tan largos" in llm.prompts[0]
    # La segunda vez sale el mismo: se refuerza, no se duplica
    llm2 = LLMFalso(cfg, {"patrones": [patron | {"existente": ids[0], "evidencia": ["2026-11-02-3: otro titular acortado"]}], "aviso": ""})
    memoria.analizar(llm2, cfg, a, 14, hoy=date(2026, 11, 2))
    [p] = a.patrones()
    assert p.veces == 2 and len(p.evidencia) == 2 and f"{p.id}. [propuesta] Acorta los titulares" in llm2.prompts[0]
    assert "Titular de 8 palabras" in memoria.markdown(a)


def test_sin_feedback_no_se_llama_al_modelo(cfg):
    llm = LLMFalso(cfg, {})
    ids, aviso, n = memoria.analizar(llm, cfg, Almacen(cfg.ruta_db), 14)
    assert ids == [] and n == 0 and "No hay feedback" in aviso and llm.prompts == []


def test_decidir_un_patron_desde_la_web(cfg):
    a = _almacen_con_feedback(cfg)
    pid = a.guardar_patron("Acorta los titulares", ["x"], "Titular de 8 palabras", "guionista")
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    c = TestClient(crear_app(cfg, a))
    assert c.patch(f"/api/memoria/{pid}", json={"estado": "aceptada", "nota": "sí, para el guionista"}).status_code == 200
    [p] = c.get("/api/memoria").json()
    assert p["estado"] == "aceptada" and p["nota"] == "sí, para el guionista"
    assert c.patch("/api/memoria/999", json={"estado": "rechazada"}).status_code == 404


def test_un_fallo_del_editor_se_explica_en_vez_de_un_500_mudo(cfg, monkeypatch):
    from folio.llm import ErrorLLM
    a = _almacen_con_feedback(cfg)
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    eid = a.ultima_ejecucion("2026-11-01")
    c = TestClient(crear_app(cfg, a), raise_server_exceptions=False)
    monkeypatch.setattr(edicion, "chat", lambda *x, **k: (_ for _ in ()).throw(ErrorLLM("chat: respuesta cortada por max_tokens")))
    r = c.post(f"/api/ejecuciones/{eid}/piezas/2026-11-01-1/chat", json={"mensaje": "acorta el titular"})
    assert r.status_code == 502 and "max_tokens" in r.json()["detail"]
    monkeypatch.setattr(edicion, "chat", lambda *x, **k: (_ for _ in ()).throw(KeyError("libros")))
    r = c.post(f"/api/ejecuciones/{eid}/piezas/2026-11-01-1/chat", json={"mensaje": "acorta el titular"})
    assert r.status_code == 500 and "KeyError" in r.json()["detail"]
