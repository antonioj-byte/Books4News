from datetime import datetime, timezone

from folio import informe
from folio.almacen import Almacen, Evaluacion, escribir_evaluacion_md
from folio.modelos import InformeDiario, Pieza

from datos import ELECCION, LIBRO, guion_valido


def _informe(fecha="2026-10-30", hora=9):
    piezas = [Pieza(id=f"{fecha}-{i}", fecha=fecha, estado="propuesta", historia_id=f"h{i}", eleccion=ELECCION,
                    n_medios=3, libros=[LIBRO], guion=guion_valido()) for i in (1, 2)]
    return InformeDiario(fecha=fecha, generado_en=datetime(2026, 10, 30, hora, tzinfo=timezone.utc), stats={},
                         top_historias=[], piezas=piezas, coste_total_usd=0.8)


def test_registrar_es_idempotente_y_cada_ejecucion_es_independiente(tmp_path):
    a = Almacen(tmp_path / "folio.db")
    e1 = a.registrar(_informe())
    assert a.registrar(_informe()) == e1
    e2 = a.registrar(_informe(hora=12))
    assert e2 != e1 and a.ultima_ejecucion("2026-10-30") == e2
    assert [d["fecha"] for d in a.dias()] == ["2026-10-30"] and len(a.dias()[0]["ejecuciones"]) == 2
    assert [p.id for p, _ in a.piezas(e1)] == ["2026-10-30-1", "2026-10-30-2"]


def test_versiones_solo_se_anaden_y_el_estado_se_guarda(tmp_path):
    a = Almacen(tmp_path / "folio.db")
    eid = a.registrar(_informe())
    p, v = a.pieza(eid, "2026-10-30-1")
    assert v == 1
    p.guion.pie_instagram = "Otro pie"
    assert a.guardar_version(eid, p.id, p, "manual", "Pie editado") == 2
    assert a.pieza(eid, p.id)[0].guion.pie_instagram == "Otro pie"
    assert a.version(eid, p.id, 1).guion.pie_instagram != "Otro pie"
    assert [x.origen for x in a.versiones(eid, p.id)] == ["pipeline", "manual"]
    a.cambiar_estado(eid, p.id, "descartada")
    assert a.pieza(eid, p.id)[0].estado == "descartada"


def test_evaluacion_en_bd_y_en_informe_md(tmp_path):
    a = Almacen(tmp_path / "folio.db")
    inf = _informe()
    eid = a.registrar(inf)
    ev = Evaluacion(seleccion=4, libro=5, idea=3, voz=4, publicaria=True, comentario="Buena portada")
    a.guardar_evaluacion(eid, "2026-10-30-1", ev, 1)
    a.guardar_evaluacion(eid, "2026-10-30-1", ev.model_copy(update={"idea": 4}), 2)
    guardada, version = a.evaluacion(eid, "2026-10-30-1")
    assert guardada.idea == 4 and guardada.publicaria is True and version == 2
    assert a.resumen_evaluaciones()[0]["idea"] == 4
    _, md = informe.escribir(inf, tmp_path / "informe")
    assert escribir_evaluacion_md(md, "2026-10-30-1", guardada)
    texto = md.read_text()
    assert "- Idea nueva (1–5): 4\n" in texto and "- ¿La publicarías? (sí/no): sí\n" in texto
    assert informe.evaluacion_rellenada(texto)
