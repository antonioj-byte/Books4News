"""El juez a ciegas de las rondas de la voz y la regla de decisión."""

import json

from folio import ab, juez
from folio.modelos import Traza

from test_ab import FUENTES, con_piezas, LLMFalso  # noqa: F401  (fixture)


class JuezFalso:
    """Da mejor nota a la versión cuyo texto lleva «voz» en idea_elegida... no la ve: puntúa por letra."""
    def __init__(self, cfg, notas):
        self.cfg, self.notas, self.trazas, self.prompts = cfg, notas, [], []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        assert etapa_modelo == "juez"
        p = mensajes[0]["content"]
        self.prompts.append(p)
        self.trazas.append(Traza(paso=paso, modelo="juez", coste_usd=0.01))
        vers = []
        for letra in "ABC":
            if f'<version letra="{letra}">' not in p:
                continue
            frase = p.split(f'<version letra="{letra}">\n', 1)[1].split("\n", 1)[0][3:40]
            idea, voz, pub = self.notas[letra]
            vers.append(juez.NotaVersion(letra=letra, idea=idea, voz=voz, publicaria=pub, mejor_frase=frase,
                                         peor_frase="una frase que no está", por_que_idea="x", por_que_voz="y"))
        return juez.Juicio(versiones=vers), []


def test_juzga_a_ciegas_rellena_y_decide(con_piezas):
    cfg = con_piezas
    ruta_md, ruta_clave = ab.generar(cfg, "2026-10-30", lambda hid: [(FUENTES[0], "Texto")], ronda="r1")
    letras = json.loads(ruta_clave.read_text())["piezas"]["2026-10-30-1"]
    por_variante = {v["variante"]: l for l, v in letras.items()}
    notas = {por_variante["opus-high"]: (3, 3, True), por_variante["voz"]: (4, 4, True),
             por_variante["voz-estilo"]: (3, 3, False)}
    falso = JuezFalso(cfg, notas)
    salida = juez.juzgar(cfg, ruta_md.parent, llm=falso)
    # Ciego: el prompt del juez no nombra variantes ni modelos
    assert not any(w in falso.prompts[0].lower() for w in ("opus", "voz-estilo", "variante"))
    md = ruta_md.read_text()
    assert md.count("- Idea nueva (1–5): 4") == 1 and "Juez a ciegas" in md
    nota = salida["piezas"]["2026-10-30-1"][por_variante["voz"]]
    assert nota["frases_literales"] is False      # la peor frase no está en el texto: queda marcado
    tabla, datos = juez.decidir(ruta_md.parent)
    assert datos["veredictos"]["voz"] == {"gana": True, "dif": 1.0}
    assert datos["veredictos"]["voz-estilo"]["gana"] is False     # menos publicables
    assert "voz: GANA" in tabla
