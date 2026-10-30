"""Pipeline completo con modelo simulado, Open Library grabado y vectores sintéticos."""

from datetime import datetime, timezone

import httpx
import numpy as np

from folio import textos
from folio.ingesta import agrupacion
from folio.historial import Historial
from folio.libros.verificacion import Verificador
from folio.llm import LLM
from folio.modelos import Articulo, ComprobacionHechos, HechoComprobado, ResumenHistoria, SeleccionJefe
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
        if esquema is ComprobacionHechos:
            return ComprobacionHechos(hechos=[
                # Sostenido por la fuente («Texto» es el texto que reciben los tests)
                HechoComprobado(afirmacion="Un tribunal juzga", donde="diapositiva 2", tipo="hecho",
                                verificado=True, medio="The Guardian", evidencia="Texto de la noticia aquí"),
                HechoComprobado(afirmacion="El funcionario firmaba órdenes", donde="diapositiva 2", tipo="hecho",
                                verificado=False, nota="Ninguna fuente lo dice"),
            ]), []
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
    monkeypatch.setattr(textos, "textos_historia", lambda cfg, h: [(FUENTES[0], "Texto de la noticia aquí.")])
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
    reintento = next(m for paso, m in reversed(llm.llamadas) if paso.startswith("guion:"))[-1]["content"]
    assert "comillas" in reintento
    # Datos de edición sustituidos por los verificados, pero sin silencio: «revisar edición»
    assert pieza.guion.libros[0].editorial_espanola == "Debolsillo"
    assert pieza.revisar_edicion
    assert any(d.modelo == "Inventada" and d.api == "Debolsillo" for d in pieza.discrepancias_edicion)
    assert any("id inexistente" in a for a in inf.avisos)
    # Comprobación de hechos: el verificado se mantiene y el que no, va al informe
    assert [h.verificado for h in pieza.hechos] == [True, False]
    md = ruta_md.read_text()
    assert "Hechos no verificados" in md and "El funcionario firmaba órdenes" in md
    assert md.startswith("# Folio Lateral")
    assert "revisar edición" in md and "| Inventada | Debolsillo |" in md
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


def test_segunda_pasada_fusiona_grupos_del_mismo_evento():
    """Dos grupos que la primera pasada separa se unen si sus centroides superan el umbral de fusión."""
    ahora = datetime.now(timezone.utc)
    vecs = {
        "a1": [1.0, 0.0, 0.0], "a2": [0.97, 0.243, 0.0],   # evento A, primer ángulo
        "b1": [0.90, 0.436, 0.0], "b2": [0.85, 0.527, 0.0],  # evento A, segundo ángulo
        "c1": [0.0, 0.0, 1.0], "c2": [0.0, 0.1, 0.995],    # otro evento
    }
    arts = [Articulo(id=i, medio=f"M{i}", url=URL, titulo=i, publicado_en=ahora, idioma="es", acceso="abierto")
            for i in vecs]
    v = {i: np.array(x) / np.linalg.norm(x) for i, x in vecs.items()}
    assert len(agrupacion.agrupar(arts, v, 0.99)) > 2
    fusionadas = agrupacion.agrupar(arts, v, 0.99, umbral_fusion=0.92)
    grupos = sorted(sorted(a.id for a in h.articulos) for h in fusionadas)
    assert ["a1", "a2", "b1", "b2"] in grupos and ["c1", "c2"] in grupos


def test_textos_congelados_por_historia(cfg, monkeypatch):
    p, _ = _pipeline(cfg, monkeypatch, [])
    descargas = []
    monkeypatch.setattr(textos, "textos_historia",
                        lambda cfg, h: descargas.append(h.id) or [(FUENTES[0], "Texto de la noticia aquí.")])
    arts = _articulos()
    h = agrupacion.agrupar(arts, _vectores(arts), 0.84)[0]
    primero = p._textos(h)
    segundo = p._textos(h)
    assert descargas == [h.id]  # la segunda vez sale de data/cache/<fecha>/textos/
    assert primero == segundo and (p.cache / "textos" / f"{h.id}.json").exists()


def test_ejecuciones_de_prueba_no_tocan_historial_ni_etapas(cfg, monkeypatch):
    p, _ = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    p.ejecutar()
    seleccion_real = (p.cache / "seleccion.json").read_text()

    # Solo una pieza: informe aparte, sin registrar el día (que borraría el resto)
    p2, _ = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    p2.solo_pieza, p2.prueba = 1, True
    inf, (_, md) = p2.ejecutar(desde="guion")
    assert [x.id for x in inf.piezas] == ["2026-10-29-1"]
    assert md.parent.name == "solo-pieza-1"
    assert (p.cache / "seleccion.json").read_text() == seleccion_real

    # Modo desarrollo desde la selección: no sobrescribe la selección guardada
    p3, _ = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    p3.dev, p3.prueba = True, True
    inf3, (_, md3) = p3.ejecutar(desde="seleccion")
    assert md3.parent.name == "2026-10-29-dev" and inf3.avisos[0].startswith("MODO DESARROLLO")
    assert (p.cache / "seleccion.json").read_text() == seleccion_real
    assert p.historial.libro_usado("2026-10-30", 60, "Eichmann en Jerusalén", "Hannah Arendt", None) == "2026-10-29"


def test_desde_hechos_reutiliza_los_guiones(cfg, monkeypatch):
    p, llm = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    p.ejecutar()
    p2, llm2 = _pipeline(cfg, monkeypatch, [], fecha="2026-10-29")  # sin guiones: no puede escribir ninguno
    inf, _ = p2.ejecutar(desde="hechos")
    assert inf.piezas[0].guion and inf.piezas[0].hechos
    assert [paso.split(":")[0] for paso, _ in llm2.llamadas] == ["hechos"]
