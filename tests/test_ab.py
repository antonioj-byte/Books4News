import json

import pytest

from folio import ab
from folio.modelos import ComprobacionHechos, HechoComprobado, Pieza

from datos import ELECCION, FUENTES, LIBRO, guion_valido


class LLMFalso:
    """Devuelve un guion válido marcado con el modelo de la variante, y una comprobación de hechos."""
    def __init__(self, cfg, reutilizar=False):
        self.cfg, self.trazas = cfg, []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        from folio.modelos import Traza
        self.trazas.append(Traza(paso=paso, modelo=self.cfg.modelo(etapa_modelo), coste_usd=0.1))
        if esquema is ComprobacionHechos:
            return ComprobacionHechos(hechos=[HechoComprobado(afirmacion="x", donde="pie", tipo="hecho", verificado=False)]), []
        g = guion_valido()
        g.idea_elegida = f"escrito por {self.cfg.modelo('guion')} {self.cfg.esfuerzo('guion')}"
        return g, []


@pytest.fixture
def con_piezas(cfg, monkeypatch):
    monkeypatch.setattr(ab, "LLM", LLMFalso)
    pieza = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                  eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())
    ruta = cfg.dir_cache("2026-10-30") / "piezas.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps([pieza.model_dump(mode="json")]))
    return cfg


def test_genera_versiones_a_ciegas_con_su_clave(con_piezas):
    cfg = con_piezas
    ruta_md, ruta_clave = ab.generar(cfg, "2026-10-30", lambda hid: [(FUENTES[0], "Texto")])
    md, clave = ruta_md.read_text(), json.loads(ruta_clave.read_text())
    letras = clave["piezas"]["2026-10-30-1"]
    assert sorted(v["variante"] for v in letras.values()) == ["opus-high", "voz", "voz-estilo"]
    # Ciego: el archivo de evaluación no nombra modelos ni variantes
    for palabra in ("opus", "sonnet", "medium", "haiku"):
        assert palabra not in md.lower()
    # El control reutiliza el guion de producción (sin coste); las demás se escriben
    control = next(v for v in letras.values() if v["variante"] == "opus-high")
    assert control["coste_usd"] == 0 and "guion de producción" in control["avisos"]
    assert all(v["hechos_total"] == 1 for v in letras.values())


def test_no_sobrescribe_evaluaciones_y_agrega_resultados(con_piezas):
    cfg = con_piezas
    ruta_md, ruta_clave = ab.generar(cfg, "2026-10-30", lambda hid: [(FUENTES[0], "Texto")])
    letras = json.loads(ruta_clave.read_text())["piezas"]["2026-10-30-1"]
    por_variante = {v["variante"]: l for l, v in letras.items()}
    md = ruta_md.read_text()
    notas = {"opus-high": ("4", "4", "sí"), "voz": ("4", "4", "sí"), "voz-estilo": ("2", "3", "no")}
    for variante, (idea, voz, pub) in notas.items():
        l = por_variante[variante]
        bloque = f"<!-- ab:2026-10-30-1:{l} -->\n- Libro (1–5): \n- Idea nueva (1–5): \n- Voz (1–5): \n- ¿La publicarías? (sí/no): "
        assert bloque in md
        md = md.replace(bloque, f"<!-- ab:2026-10-30-1:{l} -->\n- Libro (1–5): 4\n- Idea nueva (1–5): {idea}\n"
                                f"- Voz (1–5): {voz}\n- ¿La publicarías? (sí/no): {pub}")
    md = md.replace("- Preferida (letra): ", f"- Preferida (letra): {por_variante["voz"]}")
    ruta_md.write_text(md)

    with pytest.raises(FileExistsError):
        ab.generar(cfg, "2026-10-30", lambda hid: [(FUENTES[0], "Texto")])

    res = ab.resultados(cfg)
    assert "voz: cumple" in res and "voz-estilo: no cumple" in res
    fila_sonnet = next(l for l in res.splitlines() if l.startswith("| voz "))
    assert "| 1 |" in fila_sonnet  # preferida una vez
