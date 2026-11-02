"""Quien propone libros sabe cuáles ya ha usado Folio (2/11: la pieza de Telegram se quedó sin libro porque sus dos
candidatos, Applebaum y Da Empoli, ya se habían usado). Sin red ni gasto."""

from folio import seleccion
from folio.historial import Historial
from folio.llm import cargar_prompt


def test_los_libros_usados_llegan_al_jefe_y_a_la_balda(cfg):
    h = Historial(cfg.ruta_db)
    h.anadir_libros("2026-10-31", [("Autocracia S.A.", "Anne Applebaum", None)])
    h.anadir_libros("2026-11-01", [("La hora de los depredadores", "Giuliano da Empoli", None)])
    h.anadir_libros("2026-08-01", [("Viejo", "Fuera de plazo", None)])
    usados = seleccion.libros_usados(cfg, "2026-11-02")
    assert usados.index("La hora de los depredadores") < usados.index("Autocracia S.A.") and "Viejo" not in usados
    assert "Autocracia S.A." in seleccion.criterios(cfg, "2026-11-02")          # editor del libro, temas y fondo
    for plantilla in ("balda_buscar", "balda_elegir"):
        texto = (cfg.dir_prompts / f"{plantilla}.md").read_text(encoding="utf-8")
        assert "[pegar usados]" in texto
    assert "[pegar usados]" in (cfg.dir_prompts / "jefe_cultura.md").read_text(encoding="utf-8")


def test_sin_libros_usados(cfg):
    assert seleccion.libros_usados(cfg, "2026-11-02") == "(ninguno)"


def test_un_catalogo_caido_no_descarta_ni_quema_la_historia(cfg, monkeypatch):
    """Revisión general (2/11): un 503 de Google Books dejaba el libro en «desconocido», la pieza fallida sin decir por
    qué y la historia fuera una semana."""
    from datos import ELECCION, LIBRO
    from folio.modelos import Pieza
    from folio.pipeline import ERROR_CATALOGOS, Pipeline
    caido = LIBRO.model_copy(update={"edicion_es": "desconocido", "consulta_incompleta": True})
    t = Pipeline(cfg, "2026-11-02")

    class V:
        llamadas = 0

        def verificar(self, c):
            V.llamadas += 1
            return caido
    t.verificador = V()
    t._preverificar([ELECCION])
    assert not t._preverificados                         # lo pasajero no se guarda
    p = Pieza(id="2026-11-02-1", fecha="2026-11-02", estado="fallida", historia_id="h1", eleccion=ELECCION, n_medios=3)
    assert not t._verificar(p, set())
    assert p.error.startswith(ERROR_CATALOGOS) and "vuelve a verificar" in p.error
    registradas = []
    monkeypatch.setattr(t.historial, "registrar_dia", lambda f, h, l, c=(): registradas.append(h))
    t._registrar_historial([p], [], [], None)
    assert registradas == [[]]


def test_politica_de_libros_por_propuesta(cfg):
    """Decisiones del usuario (2/11): los perfiles de «Tres libros» no exigen novedad en la mesa diaria, y las
    excepciones de la redacción (repetir, sin castellano) valen también en los temas «para mañana», nunca fuera."""
    from datos import ELECCION
    from folio.pipeline import Pipeline
    t = Pipeline(cfg, "2026-11-02")
    t.aplicar_politica(ELECCION.model_copy(update={"formato": "balda"}), False)
    assert t.sin_novedad and not t.permitir_repetidos and not t.permitir_sin_castellano
    pide = ELECCION.model_copy(update={"repetir": True, "sin_castellano": True})
    t.aplicar_politica(pide, False)                          # un agente no puede saltarse las reglas por su cuenta
    assert not t.sin_novedad and not t.permitir_repetidos and not t.permitir_sin_castellano
    t.aplicar_politica(pide, True)                           # un tema de la redacción que lo pide, sí
    assert t.sin_novedad and t.permitir_repetidos and t.permitir_sin_castellano
