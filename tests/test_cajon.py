"""Cajón de curiosidades (formato «curiosidad»): historias sin percha y sin libro obligatorio. Sin red ni gasto."""

import shutil

import pytest

from folio import cajon, guion, render, seleccion
from folio.config import RAIZ
from folio.modelos import Diapositiva, FuenteNoticia, Historia, LibroGuion, Pieza, SeleccionJefe

from datos import ELECCION, LIBRO, guion_valido
from test_pipeline import LLMFalso, _pipeline

URL_CAJON = "https://ejemplo.org/biblia-malvada"
FUENTE = FuenteNoticia(medio="BBC Mundo", titulo="La Biblia malvada", url=URL_CAJON, acceso="abierto", texto_completo=True)
CURIOSIDAD = ELECCION.model_copy(update={"formato": "curiosidad", "historia_id": "cajon-biblia-malvada", "libros_candidatos": [],
                                         "titular": "La Biblia que olvidó un «no»", "gancho_libro": ""})


def _cajon(cfg, ids=("biblia-malvada",)):
    (cfg.raiz / "config").mkdir(exist_ok=True)
    (cfg.raiz / "config" / "cajon_curiosidades.yaml").write_text("".join(
        f"- id: {i}\n  titular: T de {i}\n  resumen: R de {i}\n  fuentes:\n    - {{medio: BBC Mundo, url: '{URL_CAJON}', titulo: La Biblia malvada}}\n"
        for i in ids), encoding="utf-8")


def guion_sin_libro(**cambios):
    datos = dict(
        diapositivas=[
            Diapositiva(n=1, tipo="portada", texto="La Biblia que mandaba pecar",
                        subtitulo="En 1631 una errata quitó un no al séptimo mandamiento y los impresores lo pagaron caro."),
            Diapositiva(n=2, tipo="actualidad", texto="En 1631 una Biblia inglesa imprimió el mandamiento sin la negación."),
            Diapositiva(n=3, tipo="idea", texto="Una errata dice más del oficio que cien aciertos: alguien leyó y nadie vio."),
            Diapositiva(n=4, tipo="cierre", texto="La próxima vez que leas una errata, piensa en aquel cajista. Folio."),
        ],
        pie_instagram="Según BBC Mundo, " + " ".join(["palabra"] * 95),
        libros=[], fuentes_noticia=[f"BBC Mundo {URL_CAJON}"],
    )
    return guion_valido(**(datos | cambios))


def test_el_cajon_del_repositorio_es_valido():
    curiosidades = cajon.cargar(RAIZ)
    assert len(curiosidades) >= 10
    assert all(c.fuentes and c.titular and c.resumen for c in curiosidades)
    h = cajon.historia(curiosidades[0])
    assert h.id.startswith(cajon.PREFIJO) and h.carril == "cajon" and h.n_medios == len(h.medios) >= 1
    assert all(a.acceso == "abierto" and a.carril == "cajon" for a in h.articulos)


def test_ids_repetidos_en_el_cajon(cfg):
    _cajon(cfg, ("a", "a"))
    with pytest.raises(ValueError, match="repetidos"):
        cajon.cargar(cfg.raiz)


def test_validacion_del_guion_sin_libro(cfg):
    assert guion.validar(cfg, guion_sin_libro(), [], [FUENTE]) == []
    # Sin libro verificado no se cuela ninguno inventado
    inventado = guion_sin_libro(libros=[LibroGuion(titulo="Erratas célebres", autor="Nadie", editorial_espanola=None, traductor=None, edicion_original="español, X, 2025")])
    assert any("no está entre los verificados" in e for e in guion.validar(cfg, inventado, [], [FUENTE]))
    # Con libro verificado vuelven las reglas del libro
    errores = guion.validar(cfg, guion_sin_libro(), [LIBRO], [FUENTE])
    assert "Falta una diapositiva de tipo «libro»." in errores and "Falta la lista de libros." in errores


def test_el_prompt_del_guionista_sin_libro(cfg):
    prompt = guion.construir_prompt(cfg, CURIOSIDAD, [(FUENTE, "Texto")], [])
    assert "no lleva libro" in prompt and "sin percha" in prompt


def test_seleccion_con_el_cajon(cfg):
    h = Historia(id="h1", articulos=[], n_medios=1, medios=["El País"], titular_es="T", resumen_es="R")
    hc = cajon.historia(cajon.Curiosidad(id="biblia-malvada", titular="TC", resumen="RC",
                                         fuentes=[cajon.FuenteCajon(medio="BBC Mundo", url=URL_CAJON, titulo="x")]))
    prompts = []

    class LLMJefe:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            prompts.append(mensajes[0]["content"])
            e = ELECCION.model_copy(update={"historia_id": "h1", "libros_candidatos": ELECCION.libros_candidatos * 2})
            normales = [e.model_copy(update={"formato": f}) for f in ("lateral", "lateral", "dialogo", "dialogo", "edicion", "edicion")]
            mezclada = e.model_copy(update={"formato": "lateral", "historia_id": hc.id})   # el cajón solo vale para la curiosidad
            return SeleccionJefe(elegidas=[CURIOSIDAD, mezclada, *normales], reserva=[]), []

    sel, avisos = seleccion.seleccionar(LLMJefe(cfg), [h, hc], "2026-11-01")
    assert "1 del cajón de curiosidades" in prompts[0] and "id: cajon-biblia-malvada" in prompts[0]
    assert [e.formato for e in sel.elegidas][0] == "curiosidad" and len(sel.elegidas) == 7
    assert any("tiene que salir del cajón" in a for a in avisos)
    assert not any("libros candidatos" in a for a in avisos)          # la curiosidad puede ir sin candidatos
    # Sin curiosidades disponibles, el reparto del día no la pide
    assert "curiosidad" not in seleccion.reparto_del_dia(cfg.pipeline.seleccion.reparto, [h])


class LLMCurioso(LLMFalso):
    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        if esquema is SeleccionJefe:
            self.llamadas.append((paso, mensajes))
            return SeleccionJefe(elegidas=[CURIOSIDAD], reserva=[]), []
        return super().estructurado(paso, mensajes, esquema, etapa_modelo=etapa_modelo, max_tokens=max_tokens)


def test_pipeline_con_una_curiosidad_sin_libro(cfg, monkeypatch):
    _cajon(cfg)
    cfg.pipeline.seleccion.reparto = {"curiosidad": 1}
    p, llm = _pipeline(cfg, monkeypatch, [guion_sin_libro()], fecha="2026-11-01")
    p.llm = LLMCurioso(cfg, [guion_sin_libro()])
    from folio import textos
    monkeypatch.setattr(textos, "textos_historia", lambda cfg, h, puntuaciones=None: [(FUENTE, "En 1631 una Biblia inglesa…")])
    inf, _ = p.ejecutar()
    [pieza] = inf.piezas
    assert pieza.estado == "propuesta" and pieza.libros == [] and pieza.error is None, pieza.avisos
    assert inf.stats["curiosidades_al_jefe"] == 1
    # Queda en el historial: al día siguiente no se ofrece, pasados 90 días vuelve
    assert p.historial.curiosidades_recientes("2026-11-02", 90) == {"biblia-malvada"}
    assert p._del_cajon() and not _pipeline(cfg, monkeypatch, [], fecha="2026-11-02")[0]._del_cajon()
    assert _pipeline(cfg, monkeypatch, [], fecha="2027-03-01")[0]._del_cajon()


def test_render_de_una_curiosidad_sin_libro(cfg, tmp_path, monkeypatch):
    """Prototipo de verdad: las diapositivas se pintan sin libro (sin cubierta, sin ficha en el cierre)."""
    pytest.importorskip("playwright")
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    pieza = Pieza(id="2026-11-01-7", fecha="2026-11-01", estado="propuesta", historia_id="cajon-biblia-malvada",
                  eleccion=CURIOSIDAD, n_medios=1, libros=[], guion=guion_sin_libro(), fuentes=[FUENTE])
    p = render.Plantillas(cfg)
    cierre = p.html_diapositiva(pieza, 4)
    assert "aquel cajista" in cierre and "Eichmann" not in cierre
    try:
        archivos, avisos = render.renderizar(cfg, [pieza], tmp_path)
    except Exception as exc:  # sin navegador en este entorno
        pytest.skip(f"Chromium no disponible: {exc}")
    assert [a.name for a in archivos][:4] == ["01-portada.png", "02-actualidad.png", "03-idea.png", "04-cierre.png"]
    shutil.copytree(tmp_path, cfg.raiz.parent / "render-curiosidad", dirs_exist_ok=True)
