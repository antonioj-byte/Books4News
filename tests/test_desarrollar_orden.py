"""2/11 («Proceder que enseña antes la pieza»): la versión se guarda con sus PNG antes de pintar los vídeos."""

from datetime import datetime, timezone

from typer.testing import CliRunner

from folio.almacen import Almacen
from folio.modelos import InformeDiario, Pieza

from datos import ELECCION, LIBRO, guion_valido


def test_la_pieza_se_guarda_antes_que_los_videos(cfg, monkeypatch):
    from folio import cli, config, etapas, pipeline, render
    a = Almacen(cfg.ruta_db)
    p = Pieza(id="2026-11-02-2", fecha="2026-11-02", estado="pendiente", historia_id="h1", eleccion=ELECCION, n_medios=3, libros=[LIBRO])
    eid = a.registrar(InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=timezone.utc), stats={},
                                    top_historias=[], piezas=[p], coste_total_usd=0))
    orden = []
    monkeypatch.setattr(config, "cargar", lambda *x, **k: cfg)
    monkeypatch.setattr(etapas.EtapasGuardadas, "historias", lambda self: ([], [], {}))

    def desarrollar(self, pieza, al_jefe, otras):
        return pieza.model_copy(update={"estado": "propuesta", "guion": guion_valido()})
    monkeypatch.setattr(pipeline.Pipeline, "desarrollar", desarrollar)
    monkeypatch.setattr(render, "renderizar", lambda cfg, piezas, destino, *x: orden.append("png") or ([], []))
    monkeypatch.setattr(render, "renderizar_video", lambda cfg, piezas, destino, *x: orden.append(
        f"video (versión guardada: {a.pieza(eid, p.id)[1]}, estado: {a.pieza(eid, p.id)[0].estado})") or ([], []))
    r = CliRunner().invoke(cli.app, ["desarrollar", p.id, "--ejecucion", str(eid), "--quiet"])
    assert r.exit_code == 0, r.output
    assert orden == ["png", "video (versión guardada: 2, estado: propuesta)"]
    assert "ETAPA: La pieza ya está en la mesa" in r.output
