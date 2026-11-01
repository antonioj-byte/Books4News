"""Feedback por agente (2/11): la evaluación en tres comentarios, el motivo de un descarte y las notas de diapositiva,
que la Memoria recibe con su destino."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from folio import informe
from folio.almacen import Almacen
from folio.modelos import InformeDiario, SeleccionJefe
from folio_api.main import crear_app

from datos import ELECCION, LIBRO, guion_valido
from test_api import _pieza


def _cliente(cfg):
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    inf = InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=timezone.utc), stats={}, top_historias=[],
                        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]),
                        piezas=[_pieza(1).model_copy(update={"id": "2026-11-02-1", "fecha": "2026-11-02"}),
                                _pieza(2, estado="pendiente", guion=None).model_copy(update={"id": "2026-11-02-2", "fecha": "2026-11-02"})])
    informe.escribir(inf, cfg.dir_informes / "2026-11-02")
    a = Almacen(cfg.ruta_db)
    return TestClient(crear_app(cfg, a)), a


def test_evaluacion_en_tres_comentarios_y_notas_para_la_memoria(cfg):
    c, a = _cliente(cfg)
    base = "/api/ejecuciones/1/piezas/2026-11-02-1"
    ev = {"seleccion": 4, "libro": 3, "idea": 4, "voz": 2, "publicaria": False, "comentario": "",
          "comentario_seleccion": "Buen tema", "comentario_copy": "Arranque de nota de prensa", "comentario_arte": "El friso, genial"}
    assert c.put(f"{base}/evaluacion", json=ev).status_code == 200
    assert c.get(f"{base}/evaluacion").json()["comentario_copy"] == "Arranque de nota de prensa"
    r = c.post(f"{base}/notas", json={"destino": "director_arte", "diapositiva": 1, "texto": "Con titulares largos, nada de banda"})
    assert r.status_code == 200 and r.json()["recurso"].startswith("portada") and r.json()["tipo"] == "diapositiva"
    assert c.post(f"{base}/notas", json={"destino": "jefe_cultura", "diapositiva": 1, "texto": "x x"}).status_code == 422
    # Descartar la pendiente con su motivo
    r = c.post("/api/ejecuciones/1/piezas/2026-11-02-2/descartar", json={"etiquetas": ["Puente forzado"], "texto": "Une por el tema genérico"})
    assert r.status_code == 200 and r.json()["destino"] == "jefe_cultura"
    assert c.post("/api/ejecuciones/1/piezas/2026-11-02-2/descartar", json={"etiquetas": ["Inventada"]}).status_code == 422
    assert "Puente forzado" in c.get("/api/motivos-descarte").json()
    fb = {f["pieza"]: f for f in a.feedback("2026-11-01")}
    assert fb["2026-11-02-1"]["evaluacion"]["comentario_arte"] == "El friso, genial"
    assert fb["2026-11-02-1"]["notas"][0]["destino"] == "director_arte"
    assert fb["2026-11-02-2"]["estado"] == "descartada" and fb["2026-11-02-2"]["notas"][0]["etiquetas"] == ["Puente forzado"]
    nid = c.get(f"{base}/notas").json()[0]["id"]
    assert c.delete(f"{base}/notas/{nid}").status_code == 200 and c.get(f"{base}/notas").json() == []
