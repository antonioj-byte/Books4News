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
