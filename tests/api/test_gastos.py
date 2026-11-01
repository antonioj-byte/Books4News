"""Registro del gasto (folio.gastos) y panel de la web (/api/gastos). Sin red ni gasto."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from folio import gastos, informe
from folio.almacen import Almacen
from folio.modelos import InformeDiario, SeleccionJefe, Traza
from folio_api.main import crear_app

from datos import ELECCION


def test_apuntes_de_anthropic_y_magnific_en_el_panel(cfg, monkeypatch):
    monkeypatch.setattr(gastos, "hoy", lambda: "2026-11-01")
    monkeypatch.setattr(gastos, "_almacenes", {})
    gastos.apuntar(cfg, "anthropic", "seleccion", 0.21, "USD", unidades=40000, modelo="m", detalle="seleccion")
    gastos.apuntar(cfg, "anthropic", "guion", 0.30, "USD", detalle="guion:2026-11-01-1")
    gastos.imagen_magnific(cfg, "ilustración", "2026-11-01-1")
    gastos.imagen_magnific(cfg, "retrato", "2026-11-01-1 · voxel")
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    monkeypatch.setattr("folio_api.rutas.gastos.registro.hoy", lambda: "2026-11-01")
    d = TestClient(crear_app(cfg, Almacen(cfg.ruta_db))).get("/api/gastos?dias=7").json()
    assert d["anthropic_hoy_usd"] == d["anthropic_mes_usd"] == 0.51
    assert d["magnific_mes_imagenes"] == 2 and d["magnific_mes_creditos"] == 50 and d["magnific_mes_eur"] == 0.05
    assert len(d["dias"]) == 7 and d["dias"][-1] == {"fecha": "2026-11-01", "anthropic_usd": 0.51,
                                                     "magnific_eur": 0.05, "magnific_imagenes": 2}
    assert d["conceptos"][0] == {"servicio": "anthropic", "concepto": "guion", "moneda": "USD", "coste": 0.3, "n": 1}
    assert d["ultimos"][0]["concepto"] == "retrato"


def test_el_registro_nunca_para_el_pipeline(cfg, monkeypatch):
    monkeypatch.setattr(gastos, "_almacen", lambda cfg: (_ for _ in ()).throw(OSError("disco lleno")))
    gastos.apuntar(cfg, "anthropic", "guion", 0.3, "USD")        # no lanza


def test_el_gasto_de_ejecuciones_anteriores_se_carga_una_vez(cfg):
    inf = InformeDiario(
        fecha="2026-10-30", generado_en=datetime(2026, 10, 30, 9, tzinfo=timezone.utc), stats={}, top_historias=[],
        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]), piezas=[], coste_total_usd=0.5,
        trazas=[Traza(paso="seleccion", modelo="m", tokens_entrada=1000, coste_usd=0.2),
                Traza(paso="guion:2026-10-30-1", modelo="m", coste_usd=0.3),
                Traza(paso="arte:x", modelo="m", nota="caché", coste_usd=0.0)],
    )
    informe.escribir(inf, cfg.dir_informes / "2026-10-30")
    a = Almacen(cfg.ruta_db)
    a.importar_informes(cfg.dir_informes)
    assert a.importar_gastos_historicos() == 2 and a.importar_gastos_historicos() == 0
    apuntes = a.gastos("2026-10-01")
    assert [(g.concepto, g.coste) for g in apuntes] == [("seleccion", 0.2), ("guion", 0.3)]
