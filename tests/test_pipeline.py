"""Pipeline completo con modelo simulado, Open Library grabado y vectores sintéticos."""

from datetime import datetime, timezone

import httpx
import numpy as np

from folio import textos
from folio.ingesta import agrupacion
from folio.historial import Historial
from folio.libros.verificacion import Verificador
from folio.llm import LLM
from folio.modelos import (Arte, Articulo, ComprobacionHechos, HechoComprobado, Infografia, PropuestaArte, ResumenHistoria,
                           SeleccionJefe, SinFoto)
from folio.pipeline import Pipeline

from conftest import transporte_openlibrary
from datos import ELECCION, FUENTES, LIBRO, URL, guion_valido


class LLMFalso(LLM):
    def __init__(self, cfg, guiones):
        super().__init__(cfg, cliente=object())
        self.guiones = list(guiones)
        self.llamadas = []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.llamadas.append((paso, mensajes))
        if esquema is ResumenHistoria:
            return ResumenHistoria(titular_es="Titular", resumen_es="Resumen", seccion="sociedad", sobre_libros=False), []
        from folio import puentes
        if esquema is puentes.Notas:                         # el evaluador de puentes: todo sólido
            return puentes.Notas(notas=[puentes.Nota(numero=i, puntuacion=5, por_que="Sólido") for i in range(1, 10)]), []
        if esquema is SeleccionJefe and paso.startswith("seleccion-libro"):
            return SeleccionJefe(elegidas=[], aviso="Hoy no hay nada del mundo del libro"), []
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
        if esquema is PropuestaArte:
            return PropuestaArte(tono="sereno", portada="circulo", suceso_con_victimas=False, recurso="grabado", consultas=["court"],
                                 sin_foto=SinFoto(recurso="golpe"), infografia=Infografia(tipo="ninguna"),
                                 evitar=[], cifra=None, por_que="Un tribunal antiguo"), []
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
    cfg.pipeline.seleccion.antiguedad_libros = 100     # el libro de las pruebas es de 1963 (la novedad, en su test)
    llm = LLMFalso(cfg, guiones)
    p = Pipeline(cfg, fecha, llm=llm, verificador=Verificador(cfg, httpx.Client(transport=transporte_openlibrary())),
                 historial=Historial(cfg.ruta_db))
    arts = _articulos()
    monkeypatch.setattr(p, "ingesta", lambda usar_cache: arts)
    monkeypatch.setattr(p, "vectores", lambda a: _vectores(a))
    monkeypatch.setattr(p, "vector_texto", lambda texto: np.array([1.0, 0, 0]))
    monkeypatch.setattr(textos, "textos_historia", lambda cfg, h, puntuaciones=None: [(FUENTES[0], "Texto de la noticia aquí.")])
    # Arte sin red: ninguna imagen candidata ni cubierta
    from folio import arte
    from folio.imagenes import cubiertas, prensa, retratos
    monkeypatch.setattr(arte, "candidatas", lambda propuesta, excluir=(): [])
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (None, "sin red en los tests"))
    monkeypatch.setattr(prensa, "buscar_y_fijar", lambda *a, **k: (None, "sin red en los tests"))
    monkeypatch.setattr(cubiertas, "buscar", lambda *a, **k: None)
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
    # El real se verifica y es el libro; el inventado, de reserva, ni se consulta (2/11: uno por pieza fuera de «Tres libros»)
    assert [l.olid for l in pieza.libros] == ["OL1386647W"]
    assert pieza.libros_descartados == []
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
                        lambda cfg, h, puntuaciones=None: descargas.append(h.id) or [(FUENTES[0], "Texto de la noticia aquí.")])
    arts = _articulos()
    h = agrupacion.agrupar(arts, _vectores(arts), 0.84)[0]
    primero = p.textos_de_historia(h)
    segundo = p.textos_de_historia(h)
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
    assert [paso.split(":")[0] for paso, _ in llm2.llamadas] == ["hechos", "arte"]
    assert inf.piezas[0].arte.recurso == "grabado" and any("Sin imagen" in a for a in inf.piezas[0].arte.avisos)


def test_desde_arte_no_repite_los_hechos(cfg, monkeypatch):
    p, _ = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    p.ejecutar()
    p2, llm2 = _pipeline(cfg, monkeypatch, [], fecha="2026-10-29")
    inf, _ = p2.ejecutar(desde="arte")
    assert [paso.split(":")[0] for paso, _ in llm2.llamadas] == ["arte"]
    assert inf.piezas[0].hechos                      # los de la ejecución anterior, guardados con la pieza


def test_textos_congelados_de_la_version_anterior_se_vuelven_a_elegir(cfg, monkeypatch):
    p, _ = _pipeline(cfg, monkeypatch, [])
    arts = _articulos()
    h = agrupacion.agrupar(arts, _vectores(arts), 0.84)[0]
    ruta = p.cache / "textos" / f"{h.id}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text('[{"fuente": {"medio": "X", "titulo": "t", "url": "u", "acceso": "abierto"}, "texto": "viejo"}]')
    recibidas = []
    monkeypatch.setattr(textos, "textos_historia",
                        lambda cfg, h, puntuaciones=None: recibidas.append(puntuaciones) or [(FUENTES[0], "nuevo")])
    p.vectores_articulos = _vectores(arts)
    assert p.textos_de_historia(h, ELECCION)[0][1] == "nuevo"
    assert recibidas[0] and set(recibidas[0]) == {a.id for a in h.articulos}


def _pipeline_tres(cfg, monkeypatch, escribir):
    """Pipeline con tres elegidas y una reserva; cada guion lo decide `escribir(paso)`. Se escriben las tres
    al inicio (en producción, solo la primera: el resto espera a «Proceder»)."""
    from folio import guion as guionista
    p, llm = _pipeline(cfg, monkeypatch, [])
    cfg.pipeline.seleccion.desarrollar_al_inicio = 3
    arts = _articulos()
    ids = [h.id for h in agrupacion.agrupar(arts, _vectores(arts), 0.84)]
    sel = SeleccionJefe(elegidas=[ELECCION.model_copy(update={"historia_id": ids[i % 2], "titular": f"E{i}"}) for i in range(3)],
                        reserva=[ELECCION.model_copy(update={"historia_id": ids[0], "titular": "Reserva"})])
    from datos import LIBRO
    monkeypatch.setattr(p, "_verificar_libros", lambda e, reservados: ([LIBRO.model_copy()], []))
    monkeypatch.setattr(guionista, "escribir", lambda llm, pid, e, t, libros, verificar_cita=None: (escribir(pid), [], []))
    al_jefe = [h for h in agrupacion.agrupar(arts, _vectores(arts), 0.84)]
    return p, sel, al_jefe


def test_los_guiones_se_escriben_a_la_vez(cfg, monkeypatch, capsys):
    import time

    def escribir(pid):
        time.sleep(0.6)
        return guion_valido()

    p, sel, al_jefe = _pipeline_tres(cfg, monkeypatch, escribir)
    inicio = time.monotonic()
    piezas = p.piezas(sel, al_jefe)
    assert time.monotonic() - inicio < 1.5  # en serie serían 1,8 s
    assert [x.estado for x in piezas] == ["propuesta"] * 3 + ["pendiente"]    # la reserva no hizo falta
    assert "ETAPA: Escribiendo guiones (3 de 3)" in capsys.readouterr().out


def test_si_falla_un_guion_entra_la_reserva(cfg, monkeypatch):
    def escribir(pid):
        if pid.endswith("-2"):
            raise ValueError("El guion no pasó la validación")
        return guion_valido()

    p, sel, al_jefe = _pipeline_tres(cfg, monkeypatch, escribir)
    piezas = p.piezas(sel, al_jefe)
    assert [(x.id[-1], x.estado, x.reserva) for x in piezas] == [
        ("1", "propuesta", False), ("2", "fallida", False), ("3", "propuesta", False), ("4", "propuesta", True)]


def test_carril_editorial_solo_historias_de_libros(cfg, monkeypatch):
    """Los artículos del carril editorial se agrupan aparte y solo pasan los que tratan de libros."""
    p, llm = _pipeline(cfg, monkeypatch, [])
    arts = _articulos()
    libro = Articulo(id="e1", medio="El Cultural", url=URL + "e1", titulo="Premio de novela", idioma="es",
                     acceso="abierto", carril="editorial", tier=1, publicado_en=datetime.now(timezone.utc))
    cine = libro.model_copy(update={"id": "e2", "url": URL + "e2", "titulo": "Estreno de cine"})
    vect = _vectores(arts) | {"e1": np.array([0, 0, 1.0]), "e2": np.array([0.6, 0, 0.8])}
    from folio.ingesta import resumen
    monkeypatch.setattr(resumen, "resumir", lambda llm, hs: [setattr(h, "sobre_libros", h.articulos[0].id == "e1") for h in hs] and [])
    al_jefe, _ = p.historias(arts + [libro, cine], vect, con_llm=True)
    editoriales = [h for h in al_jefe if h.carril == "editorial"]
    assert [h.articulos[0].id for h in editoriales] == ["e1"]
    assert all(a.carril == "actualidad" for h in al_jefe if h.carril == "actualidad" for a in h.articulos)


def test_las_pruebas_guardan_las_imagenes_aparte(cfg, monkeypatch):
    """Las piezas de prueba tienen los mismos ids que las de verdad: sus imágenes van a otra carpeta."""
    p, llm = _pipeline(cfg, monkeypatch, [guion_valido()], fecha="2026-10-29")
    from folio import arte
    carpetas = []
    real = arte.dirigir
    monkeypatch.setattr(arte, "dirigir", lambda *a, **k: carpetas.append(a[6] if len(a) > 6 else k.get("dir_fecha")) or real(*a, **k))
    p.prueba = True          # como --dev o --solo-pieza
    p.ejecutar()
    assert carpetas and all(c is not None and c.name == "prueba" for c in carpetas)


def test_solo_libros_novedad(cfg, monkeypatch):
    from folio.pipeline import anio_de_publicacion, fuera_de_novedad
    from folio.modelos import EdicionEspanola
    assert anio_de_publicacion(LIBRO) == 2014                       # 1963, edición española de 2014
    assert "publicado en 2014" in fuera_de_novedad(LIBRO, 2024)
    nuevo = LIBRO.model_copy(update={"edicion_es_detalle": EdicionEspanola(titulo="X", editorial="Y", anio="2025", isbn="1", pais="España")})
    assert anio_de_publicacion(nuevo) == 2025 and fuera_de_novedad(nuevo, 2024) is None      # traducción nueva
    sin_anio = LIBRO.model_copy(update={"anio_primera_edicion": None, "edicion_es": "desconocido", "edicion_es_detalle": None})
    assert "sin año" in fuera_de_novedad(sin_anio, 2024)
    # En el pipeline: el libro de 1963/2014 se descarta con su motivo
    p, _ = _pipeline(cfg, monkeypatch, [])
    cfg.pipeline.seleccion.antiguedad_libros = 2
    ok, descartes = p._verificar_libros(ELECCION, set())
    assert ok == [] and any("Folio va de novedades (desde 2024)" in d.motivo for d in descartes)


def test_el_jefe_recibe_el_anio_minimo(cfg):
    from folio import seleccion
    from folio.llm import cargar_prompt
    assert seleccion.anio_minimo("2026-10-31", 2) == 2024
    texto = cargar_prompt(cfg, "jefe_cultura", {"[pegar año mínimo]": "2024", "[pegar lista]": "", "[pegar lista editorial]": ""})
    assert "publicados en 2024 o después" in texto


def test_los_libros_quedan_en_el_orden_del_guion_sin_repetir(cfg, monkeypatch):
    """Regresión: ordenar con dict.fromkeys rompía cualquier guion (las fichas no son hashables)."""
    from datos import LIBRO
    from folio import guion as guionista
    from folio.modelos import Pieza
    p, _ = _pipeline(cfg, monkeypatch, [])
    otro = LIBRO.model_copy(update={"titulo": "Ficciones", "titulo_propuesto": "Ficciones", "autores": ["Jorge Luis Borges"], "olid": "OL1W"})
    pieza = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="fallida", historia_id="h1", eleccion=ELECCION, n_medios=1, libros=[otro, LIBRO])
    monkeypatch.setattr(guionista, "escribir", lambda *a, **k: (guion_valido(), [], []))
    p._escribir(pieza, [])
    assert pieza.estado == "propuesta" and [l.titulo for l in pieza.libros] == ["Eichmann in Jerusalem"]

def test_la_mesa_escribe_solo_la_primera_y_proceder_escribe_otra(cfg, monkeypatch):
    """Seis propuestas: se verifican todas y se escribe la primera; las demás quedan «pendiente» hasta
    que se desarrollan (folio desarrollar), sin tocar el arte de las ya escritas."""
    from folio import arte as arte_mod
    escritas = []
    p, sel, al_jefe = _pipeline_tres(cfg, monkeypatch, lambda pid: escritas.append(pid) or guion_valido())
    cfg.pipeline.seleccion.desarrollar_al_inicio = 1
    sel.elegidas = [e.model_copy(update={"formato": f}) for e, f in zip(sel.elegidas * 2, ["lateral", "dialogo", "edicion"] * 2)]
    piezas = p.piezas(sel, al_jefe)
    assert [x.estado for x in piezas] == ["propuesta"] + ["pendiente"] * 6 and escritas == [piezas[0].id]
    assert [x.eleccion.formato for x in piezas[:3]] == ["lateral", "dialogo", "edicion"]
    dirigidas = []
    monkeypatch.setattr(arte_mod, "dirigir", lambda llm, cfg, pieza, *a, **k: dirigidas.append(pieza.id) or Arte(tono="sereno", recurso="foto"))
    from folio import hechos as hechos_mod
    monkeypatch.setattr(hechos_mod, "comprobar", lambda *a, **k: [])
    hecha = p.desarrollar(piezas[2], al_jefe, piezas)
    assert hecha.estado == "propuesta" and hecha.guion and dirigidas == [piezas[2].id]   # solo la desarrollada


def test_proceder_con_guion_que_falla_deja_la_propuesta_fallida(cfg, monkeypatch):
    p, sel, al_jefe = _pipeline_tres(cfg, monkeypatch, lambda pid: (_ for _ in ()).throw(ValueError("no valida")) if pid.endswith("-2") else guion_valido())
    cfg.pipeline.seleccion.desarrollar_al_inicio = 1
    piezas = p.piezas(sel, al_jefe)
    hecha = p.desarrollar(piezas[1], al_jefe, piezas)
    assert hecha.estado == "fallida" and "no valida" in hecha.error


def test_reparto_en_el_prompt_y_avisos_si_no_se_cumple(cfg):
    cfg.pipeline.seleccion.elegidas, cfg.pipeline.seleccion.reparto = 8, {"lateral": 2, "dialogo": 2, "edicion": 2, "curiosidad": 1, "recomendado": 1}   # el mecanismo, con el reparto del 1/11
    from folio import seleccion
    assert seleccion.texto_reparto({"lateral": 2, "dialogo": 2, "edicion": 2}) == \
        "2 de lectura lateral, 2 de diálogo con la actualidad y 2 del mundo del libro"
    prompts = {}

    class LLMJefe:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            prompts.setdefault(paso, (mensajes[0]["content"], etapa_modelo))
            assert max_tokens > 16000
            e = ELECCION.model_copy(update={"historia_id": "h1", "libros_candidatos": ELECCION.libros_candidatos * 2})
            return SeleccionJefe(elegidas=[e.model_copy(update={"formato": f}) for f in ("lateral", "lateral", "dialogo", "dialogo", "edicion")],
                                 reserva=[]), []

    from folio.modelos import Historia
    h = Historia(id="h1", articulos=_articulos()[:1], n_medios=1, medios=["El País"], titular_es="T", resumen_es="R",
                 carril="editorial")
    sel, avisos = seleccion.seleccionar(LLMJefe(cfg), [h], "2026-10-31")
    # El jefe (Opus) lleva lateral y diálogo; el editor del libro (Haiku), el mundo del libro
    assert "2 de lectura lateral y 2 de diálogo con la actualidad" in prompts["seleccion"][0] and prompts["seleccion"][1] == "seleccion"
    assert "2 del mundo del libro" in prompts["seleccion-libro"][0] and prompts["seleccion-libro"][1] == "seleccion_libro"
    assert "Línea editorial de Folio" in prompts["seleccion-libro"][0] and "[pegar" not in prompts["seleccion-libro"][0]
    assert len(sel.elegidas) == 5 and "Propuestas del mundo del libro: 1 (se pedían 2)" in avisos
    assert any("fuera de esta parte de la mesa" in a for a in avisos)
    assert any("No se pudo completar" in a for a in avisos)


def test_si_falta_un_formato_se_completa_la_mesa_y_se_ordena_por_potencial(cfg):
    cfg.pipeline.seleccion.elegidas, cfg.pipeline.seleccion.reparto = 6, {"lateral": 2, "dialogo": 2, "edicion": 2}
    from folio import seleccion
    from folio.modelos import Historia
    pasos = []

    class LLMJefe:
        def __init__(self, cfg):
            self.cfg = cfg

        def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
            pasos.append(paso)
            e = ELECCION.model_copy(update={"historia_id": "h1", "libros_candidatos": ELECCION.libros_candidatos * 2})
            if paso.startswith("seleccion-libro"):
                return SeleccionJefe(elegidas=[e.model_copy(update={"formato": "edicion", "potencial": p}) for p in (9, 3)]), []
            formatos = ("lateral", "lateral", "dialogo") + (("dialogo",) if paso == "seleccion-completar" else ())
            if paso == "seleccion-completar":
                assert "1 de diálogo con la actualidad" in mensajes[-1]["content"] and mensajes[1]["role"] == "assistant"
            return SeleccionJefe(elegidas=[e.model_copy(update={"formato": f}) for f in formatos], reserva=[]), [{"type": "text", "text": "x"}]

    h = Historia(id="h1", articulos=_articulos()[:1], n_medios=1, medios=["El País"], titular_es="T", resumen_es="R")
    sel, avisos = seleccion.seleccionar(LLMJefe(cfg), [h], "2026-10-31")
    assert sorted(pasos) == ["seleccion", "seleccion-completar", "seleccion-libro"] and len(sel.elegidas) == 6
    assert any("se ha completado" in a for a in avisos)
    # La mesa se ordena por potencial: la de 9 del editor del libro va primera, la de 3, la última
    assert [e.potencial for e in sel.elegidas][0] == 9 and sel.elegidas[-1].potencial == 3


def test_solo_libros_con_edicion_en_castellano(cfg):
    """2/11 (a petición del usuario): un libro sin edición en castellano verificada se descarta, aunque sea novedad."""
    from folio.modelos import HistoriaElegida, LibroCandidato
    from folio.pipeline import Pipeline
    from datos import LIBRO

    class Verificador:
        def verificar(self, c):
            return LIBRO.model_copy(update={"titulo_propuesto": c.titulo, "edicion_es": "si" if "Traducido" in c.titulo else "no",
                                            "anio_primera_edicion": 2026})
    tuberia = Pipeline(cfg, "2026-11-02", verificador=Verificador())
    e = HistoriaElegida(formato="lateral", historia_id="h1", titular="T", de_que_se_habla="D", cuestion_de_fondo="C",
                        libros_candidatos=[LibroCandidato(titulo="Sin traducir", autor="Hannah Arendt"),
                                           LibroCandidato(titulo="Traducido", autor="Hannah Arendt")], por_que="P")
    ok, descartes = tuberia._verificar_libros(e, set())
    assert [l.titulo_propuesto for l in ok] == ["Traducido"]
    assert "sin edición en castellano" in descartes[0].motivo
    cfg.pipeline.seleccion.solo_con_edicion_es = False
    ok, _ = tuberia._verificar_libros(e, set())
    assert [l.titulo_propuesto for l in ok] == ["Sin traducir"]       # fuera de «Tres libros», solo el primero que pasa
    # En «Tres libros», hasta tres
    e3 = e.model_copy(update={"formato": "balda", "libros_candidatos": [*e.libros_candidatos,
                      *[LibroCandidato(titulo=f"Otro {i}", autor="Hannah Arendt") for i in range(3)]]})
    ok, _ = tuberia._verificar_libros(e3, set())
    assert len(ok) == 3


def test_proceder_comprueba_hechos_a_la_vez_que_el_arte(cfg, monkeypatch):
    """Ronda 1 de mejora: en «Proceder» la comprobación de hechos no espera a la dirección de arte (ni al revés).
    Cada una tarda 0,5 s simulados: juntas tienen que tardar bastante menos de 1 s, y los avisos de las dos quedan."""
    import time
    from folio import arte as arte_mod
    from folio import hechos as hechos_mod
    p, sel, al_jefe = _pipeline_tres(cfg, monkeypatch, lambda pid: guion_valido())
    cfg.pipeline.seleccion.desarrollar_al_inicio = 1
    piezas = p.piezas(sel, al_jefe)

    def comprobar(*a, **k):
        time.sleep(0.5)
        raise RuntimeError("Haiku caído")

    def dirigir(llm, cfg, pieza, *a, **k):
        time.sleep(0.5)
        raise ValueError("sin imágenes")

    monkeypatch.setattr(hechos_mod, "comprobar", comprobar)
    monkeypatch.setattr(arte_mod, "dirigir", dirigir)
    t = time.monotonic()
    hecha = p.desarrollar(piezas[1], al_jefe, piezas)
    assert time.monotonic() - t < 0.9
    assert hecha.estado == "propuesta" and hecha.hechos == [] and hecha.arte is None
    assert any(a.startswith("No se pudo comprobar los hechos: Haiku caído") for a in hecha.avisos)
    assert any(a.startswith("Director de arte: no se pudo") for a in hecha.avisos)
