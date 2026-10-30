from folio import evaluacion_md as ev


def test_bloque_con_cabecera():
    assert ev.bloque("evaluacion:p1", ("A (1–5)", "Comentario"), cabecera=["**Evaluación**", ""]) == [
        "<!-- evaluacion:p1 -->", "**Evaluación**", "", "- A (1–5): ", "- Comentario: ", "<!-- /evaluacion:p1 -->", ""]


def test_leer_rellenar_y_rellenada():
    md = "\n".join(ev.bloque("ab:p1:A", ev.CAMPOS_AB) + ev.bloque("ab:p1:B", ev.CAMPOS_AB))
    assert ev.leer(md, "ab") == {} and not ev.rellenada(md, "ab")
    md = ev.rellenar(md, "ab:p1:B", {"Voz (1–5)": 4, "Comentario": "Bien", "¿La publicarías? (sí/no)": None})
    assert ev.leer(md, "ab") == {"p1:B": {"Voz (1–5)": "4", "Comentario": "Bien"}}
    assert ev.rellenada(md, "ab") and not ev.rellenada(md, "evaluacion")
    assert ev.rellenar(md, "ab:p9:Z", {"Voz (1–5)": 1}) is None


def test_rellenar_solo_toca_su_bloque():
    md = "\n".join(ev.bloque("evaluacion:p1", ev.CAMPOS_PIEZA) + ev.bloque("evaluacion:p2", ev.CAMPOS_PIEZA))
    md = ev.rellenar(md, "evaluacion:p2", {"Voz (1–5)": 5})
    assert ev.leer(md, "evaluacion") == {"p2": {"Voz (1–5)": "5"}}
