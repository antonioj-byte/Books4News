"""Pipeline completo con modelo simulado, Open Library grabado y vectores sintéticos."""

from datetime import datetime, timezone

import httpx
import numpy as np

from folio import textos
from folio.historial import Historial
from folio.libros.verificacion import Verificador
from folio.llm import LLM
from folio.modelos import Articulo, ResumenHistoria, SeleccionJefe
from folio.pipeline import Pipeline

from conftest import transporte_openlibrary
from datos import ELECCION, FUENTES, URL, guion_valido


class LLMFalso(LLM):
    def __init__(self, cfg, guiones):
        super().__init__(cfg, cliente=object())
        self.guiones = list(guiones)
        self.llamadas = []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.llamadas.append((paso, mensajes))
        if esquema is ResumenHistoria:
            return ResumenHistoria(titular_es="Titular", resumen_es="Resumen", seccion="sociedad"), []
        if esquema is SeleccionJefe:
            elegida = ELECCION.model_copy(update={"historia_id": self.ids[0]})
            reserva = ELECCION.model_copy(update={"historia_id": self.ids[1], "titular": "Reserva"})
            return SeleccionJefe(elegidas=[elegida, elegida.model_copy(update={"historia_id": "inexistente"})],
                                 reserva=[reserva]), []
        return self.guiones.pop(0), []


def _articulos():
    ahora = datetime.now(timezone.utc)
    arts = []
    for evento in range(2):
        for medio in ("The Guardian", "BBC News", "El País"):
            arts.append(Articulo(id=f"{evento}{medio[:3]}", medio=medio, url=URL, titulo=f"Evento {evento}",
                                 publicado_en=ahora, idioma="en", acceso="abierto"))
    return arts


def _vectores(arts):
    base = {0: np.array([1.0, 0, 0]), 1: np.array([0, 1.0, 0])}
    return {a.id: base[int(a.id[0])] for a in arts}


def _pipeline(cfg, monkeypatch, guiones, fecha="2026-10-30"):
    llm = LLMFalso(cfg, guiones)
    p = Pipeline(cfg, fecha, llm=llm, verificador=Verificador(cfg, httpx.Client(transport=transporte_openlibrary())),
                 historial=Historial(cfg.ruta_db))
    arts = _articulos()
    monkeypatch.setattr(p, "ingesta", lambda usar_cache: arts)
    monkeypatch.setattr(p, "vectores", lambda a: _vectores(a))
    monkeypatch.setattr(textos, "textos_historia", lambda cfg, h: [(FUENTES[0], "Texto")])
    from folio.ingesta import agrupacion
    llm.ids = [h.id for h in agrupacion.agrupar(arts, _vectores(arts), 0.84)]
    return p, llm


def test_pipeline_completo(cfg, monkeypatch):
    malo = guion_valido()
    malo.diapositivas[2].texto = "Arendt dijo «una cita inventada»."
    p, llm = _pipeline(cfg, monkeypatch, [malo, guion_valido()])
    inf, (ruta_json, ruta_md) = p.ejecutar()

    assert len(inf.piezas) == 1
    pieza = inf.piezas[0]
    assert pieza.estado == "propuesta"
    # El libro inventado se descarta; el real se verifica
    assert [l.olid for l in pieza.libros] == ["OL1386647W"]
    assert pieza.libros_descartados[0].titulo == "El jardín de las máquinas tristes"
    # Primer guion con cita → reintento con los errores; el segundo pasa
    assert "Guion aceptado en el intento 2" in pieza.avisos
    reintento = llm.llamadas[-1][1][-1]["content"]
    assert "comillas" in reintento
    # Datos de edición sustituidos por los verificados
    assert pieza.guion.libros[0].editorial_espanola == "Debolsillo"
    assert any("id inexistente" in a for a in inf.avisos)
    assert ruta_md.read_text().startswith("# Folio Lateral")
    assert ruta_json.exists()


def test_exclusion_de_historias_y_libros_usados(cfg, monkeypatch):
    p, _ = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    p.ejecutar()
    # Al día siguiente la historia usada queda excluida y el libro también
    p2, llm2 = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-30")
    _, resumidas = p2.historias(_articulos(), _vectores(_articulos()), con_llm=False)
    assert sum(1 for r in resumidas if r.excluida) == 1
    assert p2.historial.libro_usado("2026-10-30", 60, "Eichmann en Jerusalén", "Hannah Arendt", None) == "2026-10-29"
    # Relanzar el mismo día no se excluye a sí mismo
    assert p.historial.libro_usado("2026-10-29", 60, "Eichmann en Jerusalén", "Hannah Arendt", None) is None
