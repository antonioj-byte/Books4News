from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from folio import informe
from folio.almacen import Almacen
from folio.modelos import HechoComprobado, InformeDiario, Pieza, SeleccionJefe
from folio_api.main import crear_app, hechos_ligados

from datos import ELECCION, LIBRO, guion_valido


def _pieza(i, **cambios):
    datos = dict(id=f"2026-10-30-{i}", fecha="2026-10-30", estado="propuesta", historia_id=f"h{i}",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())
    datos.update(cambios)
    return Pieza(**datos)


@pytest.fixture
def cliente(cfg, tmp_path):
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    hecho = HechoComprobado(afirmacion="Un tribunal juzga a un funcionario", donde="diapositiva 2", tipo="hecho",
                            verificado=False, nota="Ninguna fuente lo dice")
    inf = InformeDiario(
        fecha="2026-10-30", generado_en=datetime(2026, 10, 30, 9, tzinfo=timezone.utc), stats={}, top_historias=[],
        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[], aviso="Día flojo: solo dos buenas"),
        piezas=[_pieza(1, hechos=[hecho], revisar_edicion=True), _pieza(2, revision_humana=["sin traducir"])],
        coste_total_usd=0.8,
    )
    informe.escribir(inf, cfg.dir_informes / "2026-10-30")
    app = crear_app(cfg, Almacen(cfg.ruta_db))  # importa el informe al arrancar
    return TestClient(app)


def test_dias_y_portada_del_dia(cliente):
    dias = cliente.get("/api/dias").json()
    assert dias[0]["fecha"] == "2026-10-30" and dias[0]["ejecuciones"][0]["piezas"] == 2
    dia = cliente.get("/api/dias/2026-10-30").json()
    assert dia["aviso_jefe"] == "Día flojo: solo dos buenas"
    p1, p2 = dia["piezas"]
    assert p1["marcas"] == {"revisar_edicion": True, "hechos_no_verificados": 1, "revision_humana": 0, "error": None}
    assert p2["marcas"]["revision_humana"] == 1 and p1["portada"] == "La obediencia también se elige"
    assert cliente.get("/api/dias/2026-01-01").status_code == 404


def test_pieza_con_hechos_ligados_a_su_frase(cliente):
    eid = cliente.get("/api/dias/2026-10-30").json()["ejecucion"]["id"]
    d = cliente.get(f"/api/ejecuciones/{eid}/piezas/2026-10-30-1").json()
    assert d["pieza"]["guion"]["diapositivas"][0]["tipo"] == "portada" and d["version"] == 1
    [h] = d["hechos_no_verificados"]
    assert h["diapositiva"] == 2 and h["frase"].startswith("Un tribunal juzga")
    assert d["versiones"][0]["origen"] == "pipeline"


def test_html_de_la_diapositiva_y_tokens(cliente):
    eid = cliente.get("/api/dias/2026-10-30").json()["ejecucion"]["id"]
    html = cliente.get(f"/api/ejecuciones/{eid}/piezas/2026-10-30-1/diapositivas/1.html").text
    assert '<base href="/diseno/">' in html and "diapositiva--portada" in html
    assert cliente.get(f"/api/ejecuciones/{eid}/piezas/2026-10-30-1/diapositivas/9.html").status_code == 404
    assert cliente.get("/diseno/plantillas/base.css").status_code == 200
    assert "--colores-papel" in cliente.get("/api/diseno/tokens.css").text


def test_estado_y_evaluacion_se_guardan_y_van_al_informe_md(cliente, cfg):
    eid = cliente.get("/api/dias/2026-10-30").json()["ejecucion"]["id"]
    url = f"/api/ejecuciones/{eid}/piezas/2026-10-30-1"
    assert cliente.patch(f"{url}/estado", json={"estado": "aprobada"}).status_code == 200
    assert cliente.patch(f"{url}/estado", json={"estado": "inventado"}).status_code == 422
    ev = {"seleccion": 4, "libro": 5, "idea": 3, "voz": 4, "publicaria": True, "comentario": "Bien"}
    assert cliente.put(f"{url}/evaluacion", json=ev).json()["idea"] == 3
    assert cliente.put(f"{url}/evaluacion", json={**ev, "voz": 9}).status_code == 422
    dia = cliente.get("/api/dias/2026-10-30").json()
    assert dia["piezas"][0]["estado"] == "aprobada" and dia["piezas"][0]["evaluada"]
    assert "- Voz (1–5): 4" in (cfg.dir_informes / "2026-10-30" / "informe.md").read_text()
    [r] = cliente.get("/api/evaluaciones/resumen").json()
    assert r["fecha"] == "2026-10-30" and r["publicaria"] == 1


def test_hechos_ligados_en_el_pie():
    p = _pieza(1, hechos=[HechoComprobado(afirmacion="Según The Guardian", donde="pie", tipo="nombre", verificado=False)])
    [h] = hechos_ligados(p)
    assert h.diapositiva is None and "The Guardian" in h.frase


def test_lanzar_ejecucion_una_a_la_vez(cfg, tmp_path):
    import sys
    import time

    from folio_api.ejecutor import Ejecutor
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    ejecutor = Ejecutor(tmp_path, comando=[sys.executable, "-c", "import time; print('pipeline en marcha', flush=True); time.sleep(1.5)"])
    c = TestClient(crear_app(cfg, Almacen(cfg.ruta_db), ejecutor=ejecutor))
    assert c.get("/api/ejecuciones/en-marcha").json()["en_marcha"] is False
    r = c.post("/api/ejecuciones/lanzar")
    assert r.status_code == 202 and r.json()["en_marcha"] is True
    assert c.post("/api/ejecuciones/lanzar").status_code == 409
    for _ in range(50):
        estado = c.get("/api/ejecuciones/en-marcha").json()
        if not estado["en_marcha"]:
            break
        time.sleep(0.1)
    assert estado["codigo"] == 0 and estado["ultimas_lineas"] == ["pipeline en marcha"]


def test_datos_en_el_volumen(cfg, monkeypatch, tmp_path):
    monkeypatch.setenv("FOLIO_DATOS", str(tmp_path / "volumen"))
    assert cfg.dir_datos == tmp_path / "volumen" / "data" and cfg.ruta_db == tmp_path / "volumen" / "data" / "folio.db"
    assert cfg.dir_informes == tmp_path / "volumen" / "informes"
    assert (cfg.dir_prompts).exists()  # prompts, config y diseño siguen en el código
