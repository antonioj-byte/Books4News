"""Trabajos en hilo y «suele tardar» (4/11, usabilidad: nada atado a la página y la barra de la tarjeta de trabajo)."""
import time

from fastapi.testclient import TestClient

from folio.almacen import Almacen
from folio_api import ejecutor as ej
from folio_api.ejecutor import Ejecutor


def _esperar(e: Ejecutor, clave: str):
    for _ in range(100):
        estado = e.estado_desarrollo(clave)
        if estado and not estado.en_marcha:
            return estado
        time.sleep(0.02)
    raise AssertionError("el trabajo no acabó")


def test_un_trabajo_en_hilo_anuncia_sus_pasos_y_deja_su_resultado(tmp_path):
    e = Ejecutor(tmp_path)
    assert e.en_hilo("tema-1", "Tema: prueba", lambda anunciar: (anunciar("El jefe de cultura piensa"), {"ok": 1})[1]) is None
    estado = _esperar(e, "tema-1")
    assert estado.codigo == 0 and estado.etapa == "El jefe de cultura piensa"
    assert e.resultado("tema-1") == '{"ok": 1}'
    assert not any(l.startswith(ej.DURACION) for l in estado.ultimas_lineas)      # la duración no sale como línea
    # No cuenta para el tope de «Proceder» y sale en la bandeja con su nombre
    assert e.desarrollando() == 0 and e.trabajos()[0].nombre == "Tema: prueba"


def test_si_falla_dice_el_motivo_en_una_linea(tmp_path):
    e = Ejecutor(tmp_path)

    class NoSe(Exception):
        detail = "El jefe ya está con otro tema; espera a que responda"
    def falla(anunciar):
        raise NoSe()
    e.en_hilo("tema-2", "Tema", falla)
    estado = _esperar(e, "tema-2")
    assert estado.codigo == 1 and estado.ultimas_lineas[-1] == NoSe.detail and e.resultado("tema-2") is None


def test_suele_tardar_es_la_mediana_de_los_que_acabaron_bien(tmp_path):
    e = Ejecutor(tmp_path)
    assert e.tipico("2026-11-05-3") == ej.TIPICO_POR_DEFECTO["pieza"]          # sin historia, el valor por defecto
    for i, (d, codigo) in enumerate([(100, 0), (140, 0), (900, 1), (120, 0)]):
        e._registro_de(f"2026-11-0{i + 1}-1").parent.mkdir(parents=True, exist_ok=True)
        e._registro_de(f"2026-11-0{i + 1}-1").write_text(f"ETAPA: x\n{ej.DURACION}{d}\n{ej.FIN}{codigo}\n", encoding="utf-8")
    assert e.tipico("2026-11-05-3") == 120                                        # el que falló no cuenta
    assert e.tipico("newsletter") == ej.TIPICO_POR_DEFECTO["newsletter"]


def test_un_tema_en_segundo_plano_responde_al_momento(cfg, monkeypatch):
    from folio_api.main import crear_app
    from folio_api.rutas import temas as ruta
    from folio_api.rutas.temas import TemaCreado
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    app = crear_app(cfg, Almacen(cfg.ruta_db), importar=False)
    c = TestClient(app)
    llamadas = []

    def falso(ctx, eid, tid, replica=None, anunciar=None):
        anunciar("El jefe de cultura piensa la propuesta")
        llamadas.append((eid, tid))
        return TemaCreado(tema=next(x for x in ctx.almacen.temas() if x.id == tid), respuesta="Lo llevo a la mesa")
    monkeypatch.setattr(ruta, "_resultado", falso)
    r = c.post("/api/temas", json={"texto": "La huelga de traductores en Francia", "cuando": "ahora", "ejecucion": 1,
                                   "segundo_plano": True}).json()
    assert r["trabajo"] == f"tema-{r['tema']['id']}"
    for _ in range(100):
        t = c.get(f"/api/trabajos/{r['trabajo']}").json()
        if not t["en_marcha"]:
            break
        time.sleep(0.02)
    assert t["codigo"] == 0 and t["resultado"]["respuesta"] == "Lo llevo a la mesa" and llamadas
    assert c.get("/api/trabajos/no-existe").status_code == 404
