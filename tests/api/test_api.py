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
    ejecutor.diaria = [ejecutor.comando]           # el botón lanza la diaria; aquí, sin el render de verdad
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


def test_etapa_de_la_ejecucion(tmp_path):
    import sys
    import time

    from folio_api.ejecutor import Ejecutor
    codigo = "print('ETAPA: Leyendo las noticias'); print('INFO algo'); print('ETAPA: Escribiendo guiones (1 de 3)', flush=True)"
    e = Ejecutor(tmp_path, comando=[sys.executable, "-c", codigo])
    e.lanzar()
    for _ in range(50):
        if not e.estado().en_marcha:
            break
        time.sleep(0.1)
    estado = e.estado()
    assert estado.etapa == "Escribiendo guiones (1 de 3)" and estado.ultimas_lineas == ["INFO algo"]


def test_portada_del_dia_trae_los_libros_para_la_estanteria(cliente):
    p1 = cliente.get("/api/dias/2026-10-30").json()["piezas"][0]
    assert p1["libros"] == [{"titulo": "Eichmann en Jerusalén", "autor": "Hannah Arendt", "cubierta": None}]
    assert p1["formato"] == "lateral"


def test_medios_solo_imagenes_y_cubiertas(cliente, cfg):
    raiz = cfg.dir_cache("x").parent
    (raiz / "2026-10-30" / "imagenes").mkdir(parents=True)
    (raiz / "2026-10-30" / "imagenes" / "2026-10-30-1.jpg").write_bytes(b"\xff\xd8jpg")
    (raiz / "2026-10-30" / "textos").mkdir(parents=True)
    (raiz / "2026-10-30" / "textos" / "h1.json").write_text("[]")
    assert cliente.get("/api/medios/2026-10-30/imagenes/2026-10-30-1.jpg").status_code == 200
    assert cliente.get("/api/medios/2026-10-30/textos/h1.json").status_code == 404
    assert cliente.get("/api/medios/2026-10-30/imagenes/../textos/h1.json").status_code == 404
    assert cliente.get("/api/medios/cubiertas/no-existe.jpg").status_code == 404


def test_error_interno_dice_el_motivo(cliente, monkeypatch):
    from fastapi.testclient import TestClient
    app = cliente.app
    monkeypatch.setattr(app.state.folio.almacen, "dias", lambda: (_ for _ in ()).throw(ValueError("algo raro key=SECRETO")))
    r = TestClient(app, raise_server_exceptions=False).get("/api/dias")
    assert r.status_code == 500 and "ValueError: algo raro" in r.json()["detail"] and "SECRETO" not in r.text


def test_video_de_portada_en_la_ficha_de_la_pieza(cliente, cfg):
    ficha = cliente.get("/api/ejecuciones/1/piezas/2026-10-30-1").json()
    assert ficha["video_portada"] is None
    assert cliente.get("/api/ejecuciones/1/piezas/2026-10-30-1/video.mp4").status_code == 404
    mp4 = cfg.dir_informes / "2026-10-30" / "render" / "2026-10-30-1" / "01-portada.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    ficha = cliente.get("/api/ejecuciones/1/piezas/2026-10-30-1").json()
    assert ficha["video_portada"] == "/api/ejecuciones/1/piezas/2026-10-30-1/video.mp4"
    r = cliente.get(ficha["video_portada"])
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"


def test_descargar_el_carrusel_en_zip(cliente, cfg, monkeypatch):
    import io
    import zipfile

    from folio.publicacion import preparar as prep

    def preparar_falso(cfg, p, con_video=True):
        carpeta = cfg.dir_informes / p.fecha / "publicar" / p.id
        carpeta.mkdir(parents=True, exist_ok=True)
        for n in range(1, 6):
            (carpeta / f"{n:02d}.jpg").write_bytes(b"jpg")
        (carpeta / "pie.txt").write_text(prep.pie_publicacion(p), encoding="utf-8")
        if con_video:
            (carpeta / "01.mp4").write_bytes(b"recien hecho")
        return prep.Preparada(carpeta, [], prep.pie_publicacion(p), [])
    monkeypatch.setattr(prep, "preparar", preparar_falso)
    r = cliente.get("/api/ejecuciones/1/piezas/2026-10-30-1/descarga.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="folio-2026-10-30-1-v1.zip"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.namelist() == ["01.jpg", "01.mp4", "02.jpg", "03.jpg", "04.jpg", "05.jpg", "pie.txt"]
    # Si ya hay vídeo del render del día y la pieza no se ha editado, se reutiliza
    mp4 = cfg.dir_informes / "2026-10-30" / "render" / "2026-10-30-1" / "01-portada.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"del render del dia")
    z = zipfile.ZipFile(io.BytesIO(cliente.get("/api/ejecuciones/1/piezas/2026-10-30-1/descarga.zip").content))
    assert z.read("01.mp4") == b"del render del dia"


def test_proceder_lanza_el_desarrollo_de_una_propuesta_pendiente(cfg, tmp_path):
    from folio_api.ejecutor import Ejecutor
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())

    class EjecutorFalso(Ejecutor):
        def __init__(self):
            super().__init__(tmp_path)
            self.lanzadas = []

        def lanzar(self, pasos=None):
            self.lanzadas.append(pasos)
            return True

    inf = InformeDiario(fecha="2026-10-30", generado_en=datetime(2026, 10, 30, 9, tzinfo=timezone.utc), stats={}, top_historias=[],
                        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]),
                        piezas=[_pieza(1), _pieza(2, estado="pendiente", guion=None,
                                                  eleccion=ELECCION.model_copy(update={"formato": "edicion"}))])
    informe.escribir(inf, cfg.dir_informes / "2026-10-30")
    ej = EjecutorFalso()
    c = TestClient(crear_app(cfg, Almacen(cfg.ruta_db), ejecutor=ej))
    dia = c.get("/api/dias/2026-10-30").json()
    assert [(p["estado"], p["formato"]) for p in dia["piezas"]] == [("propuesta", "lateral"), ("pendiente", "edicion")]
    assert c.post("/api/ejecuciones/1/piezas/2026-10-30-1/desarrollar").status_code == 409     # ya escrita
    r = c.post("/api/ejecuciones/1/piezas/2026-10-30-2/desarrollar")
    assert r.status_code == 202 and ej.lanzadas[-1][0][-5:] == ["desarrollar", "2026-10-30-2", "--ejecucion", "1", "--quiet"]
    assert "pendiente (sin desarrollar" in (cfg.dir_informes / "2026-10-30" / "informe.md").read_text()
