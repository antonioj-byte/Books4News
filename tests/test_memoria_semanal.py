"""Memoria: análisis semanal (cuándo toca, registro, nunca falla la diaria) y reglas de las conversaciones."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from folio import memoria
from folio.almacen import Almacen

RAIZ = Path(__file__).resolve().parents[1]


def _con_analisis(a: Almacen, dia: date) -> None:
    a.registrar_analisis("manual", 0, 0, 0.0)
    a.db.execute("UPDATE memoria_analisis SET ts = ?", (datetime(dia.year, dia.month, dia.day, 5, tzinfo=timezone.utc).isoformat(),))
    a.db.commit()


def test_toca_los_lunes_y_si_pasa_una_semana(tmp_path):
    a = Almacen(tmp_path / "f.db")
    lunes = date(2026, 11, 2)
    assert lunes.weekday() == 0
    assert memoria.toca_analisis(a, lunes)[0]                   # nunca se ha analizado
    _con_analisis(a, lunes - timedelta(days=7))
    assert memoria.toca_analisis(a, lunes)[0]
    _con_analisis(a, lunes)
    assert not memoria.toca_analisis(a, lunes)[0]               # ya se analizó hoy
    assert not memoria.toca_analisis(a, lunes + timedelta(days=3))[0]
    assert memoria.toca_analisis(a, lunes + timedelta(days=7))[0]
    assert memoria.proximo_analisis(a, lunes + timedelta(days=1)) == lunes + timedelta(days=7)
    _con_analisis(a, lunes - timedelta(days=2))                 # el sábado, a mano: el lunes no toca
    assert not memoria.toca_analisis(a, lunes)[0]
    assert memoria.toca_analisis(a, lunes + timedelta(days=6))[0]   # si un lunes se perdió, a los ocho días


def test_analizar_sin_feedback_se_registra_y_no_llama_al_modelo(tmp_path, cfg):
    class SinLLM:
        trazas: list = []

        def estructurado(self, *a, **k):
            raise AssertionError("no debe llamar al modelo")

    a = Almacen(tmp_path / "f.db")
    ids, aviso, n = memoria.analizar(SinLLM(), cfg, a, origen="semanal")
    assert (ids, n) == ([], 0) and "No hay feedback" in aviso
    u = a.ultimo_analisis()
    assert u["origen"] == "semanal" and u["coste_usd"] == 0
    assert not memoria.toca_analisis(a)[0]


def test_las_reglas_de_la_conversacion_se_cargan_una_vez_como_aplicadas(tmp_path):
    entradas = memoria.cargar_conversacion(RAIZ)
    assert len(entradas) >= 20
    claves = {e["clave"] for e in entradas}
    assert {"nunca-dos-caras", "archivo-sin-repetir", "lector-sin-contexto", "libros-uno-o-tres"} <= claves
    a = Almacen(tmp_path / "f.db")
    assert a.importar_conversacion(entradas) == len(entradas)
    assert a.importar_conversacion(entradas) == 0               # idempotente
    ps = a.patrones()
    assert len(ps) == len(entradas) and all(p.estado == "aplicada" and p.origen == "conversacion" for p in ps)
    # Si el texto cambia en el archivo, se actualiza sin duplicar ni tocar el estado
    entradas[0]["propuesta"] = "Regla reescrita para la prueba."
    a.importar_conversacion(entradas)
    assert sum(p.propuesta == "Regla reescrita para la prueba." for p in a.patrones()) == 1
    assert len(a.patrones()) == len(entradas)
    assert "conversación" in memoria.markdown(a)
    # Una regla que sale del archivo (sustituida por otra) sale también de la memoria; las del feedback, no
    a.guardar_patron("Un patrón del feedback", ["x"], "Una regla", "guionista")
    quitada = entradas.pop()["clave"]
    a.importar_conversacion(entradas)
    assert quitada not in {p.clave for p in a.patrones()} and len(a.patrones()) == len(entradas) + 1


def test_claves_repetidas_o_destino_desconocido_no_valen(tmp_path):
    (tmp_path / "config").mkdir()
    f = tmp_path / "config" / "memoria_conversacion.yaml"
    base = "  fecha: '2026-11-02'\n  destino: guionista\n  patron: Algo que pidió\n  propuesta: Una regla larga\n  evidencia: [x]\n"
    f.write_text(f"- clave: a\n{base}- clave: a\n{base}", encoding="utf-8")
    with pytest.raises(ValueError, match="repetidas"):
        memoria.cargar_conversacion(tmp_path)
    f.write_text(f"- clave: a\n{base.replace('guionista', 'nadie')}", encoding="utf-8")
    with pytest.raises(Exception):
        memoria.cargar_conversacion(tmp_path)


def test_si_toca_nunca_sale_con_error(cfg, monkeypatch):
    from folio import cli, config

    monkeypatch.setattr(config, "cargar", lambda *a, **k: cfg)

    def roto(*a, **k):
        raise RuntimeError("se cayó")
    monkeypatch.setattr(memoria, "analizar", roto)
    r = CliRunner().invoke(cli.app, ["memoria", "analizar", "--si-toca"])
    assert r.exit_code == 0 and "no se pudo analizar" in r.output
    _con_analisis(Almacen(cfg.ruta_db), date.today())
    r = CliRunner().invoke(cli.app, ["memoria", "analizar", "--si-toca"])
    assert r.exit_code == 0 and "no toca" in r.output


def test_la_diaria_acaba_con_el_analisis_semanal(tmp_path):
    from folio_api.ejecutor import Ejecutor
    assert Ejecutor(tmp_path).diaria[-1][-3:] == ["memoria", "analizar", "--si-toca"]
