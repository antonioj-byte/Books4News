"""El fondo del mes (2/11, a petición del usuario): cosecha entre días, reparto por tandas, jefe, puentes y
verificación, y su uso desde la web. Sin red ni gasto."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from folio import fondo, informe, puentes
from folio.almacen import Almacen
from folio.etapas import EtapasGuardadas
from folio.llm import LLM
from folio.modelos import HistoriaResumida, InformeDiario, LibroCandidato, SeleccionJefe
from folio_api.main import crear_app

from datos import LIBRO


def test_reparto_por_tandas_hasta_el_mes():
    r = fondo.reparto_de_tanda({})
    assert sum(r.values()) == 25 and r["lateral"] > r["dialogo"] > r["edicion"]
    casi = {f: n - 1 for f, n in fondo.REPARTO_MES.items()}
    assert fondo.reparto_de_tanda(casi) == {f: 1 for f in fondo.REPARTO_MES}       # solo lo que falta
    assert fondo.reparto_de_tanda(dict(fondo.REPARTO_MES)) == {}


def _dia(cfg, fecha, titulares):
    rs = [HistoriaResumida(id=f"h{i}", titular_es=t, resumen_es=r, seccion=None, n_medios=len(m), medios=m)
          for i, (t, r, m) in enumerate(titulares)]
    EtapasGuardadas(cfg.dir_cache(fecha)).guardar_historias([], rs, {})


def test_la_cosecha_junta_lo_que_vuelve_varios_dias(cfg):
    gaza = ("Nueva ronda de negociaciones de alto el fuego en Gaza", "Mediadores de Egipto y Catar reúnen a las partes en Gaza", ["BBC", "El País"])
    _dia(cfg, "2026-10-30", [gaza, ("Gana el Real Madrid", "Partido de liga en el Bernabéu", ["As"])])
    _dia(cfg, "2026-10-31", [("Las negociaciones de alto el fuego en Gaza siguen sin acuerdo", "Egipto y Catar insisten en Gaza", ["DW"])])
    temas = fondo.cosecha(cfg, "2026-11-02")
    assert len(temas[0].dias) == 2 and temas[0].medios == {"BBC", "El País", "DW"}
    assert len(temas) == 2 and len(temas[1].dias) == 1


class LLMFondo(LLM):
    def __init__(self, cfg):
        super().__init__(cfg, cliente=object())
        self.llamadas = []

    def estructurado(self, paso, mensajes, esquema, **k):
        self.llamadas.append(paso)
        if esquema is fondo.TandaFondo:
            n = int(mensajes[0]["content"].split("Te pido ahora esta tanda: ")[1].split(" ")[0])
            return fondo.TandaFondo(propuestas=[fondo.PropuestaFondo(
                formato="lateral", historia="", titular=f"Propuesta {len(self.llamadas)}-{i}", de_que_se_habla="Algo que dura.",
                cuestion_de_fondo=f"Cuestión {len(self.llamadas)}-{i}", gancho_libro="El libro lo explica.",
                libros_candidatos=[LibroCandidato(titulo="Eichmann en Jerusalén", autor="Hannah Arendt")], protagonista="",
                potencial=6, por_que_dura="Debate abierto", meses=3, reactivar="Una sentencia", por_que="Porque sí")
                for i in range(n)]), []
        if esquema is puentes.Notas:
            return puentes.Notas(notas=[puentes.Nota(numero=i, puntuacion=2 if i == 1 else 4, por_que="x") for i in range(1, 11)]), []
        raise AssertionError(esquema)


def test_una_tanda_filtra_puentes_y_verifica_libros(cfg, monkeypatch):
    from folio.pipeline import Pipeline
    monkeypatch.setattr(fondo, "REPARTO_MES", {"lateral": 7})
    monkeypatch.setattr(Pipeline, "_preverificar", lambda self, e: None)
    monkeypatch.setattr(Pipeline, "_verificar_libros", lambda self, e, usados: ([LIBRO.model_copy()], []))
    a = Almacen(cfg.ruta_db)
    llm = LLMFondo(cfg)
    r = fondo.preparar_tanda(cfg, a, "2026-11-02", llm, n=7)
    # Dos llamadas al jefe (5 + 2), una al evaluador; la primera propuesta tiene puente 2 y se queda fuera
    assert [p for p in llm.llamadas if p.startswith("fondo")] == ["fondo:2026-11-02:0", "fondo:2026-11-02:5"]
    assert r.pedidas == 7 and r.guardadas == 6 and len(r.fuera) == 1
    xs = a.fondo(mes="2026-11")
    assert len(xs) == 6 and xs[0]["vale_hasta"] == "2027-01-31" and xs[0]["datos"]["libros"][0]["titulo_propuesto"]
    assert "Cuestión 1-0" not in {x["cuestion"] for x in xs}
    # Falta una para completar el mes: la siguiente tanda pide solo esa
    llm.llamadas.clear()
    assert fondo.preparar_tanda(cfg, a, "2026-11-02", llm, n=7).pedidas == 1


def test_la_web_lista_escribe_y_descarta(cfg, monkeypatch):
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    inf = InformeDiario(fecha="2026-11-02", generado_en=datetime(2026, 11, 2, 5, tzinfo=timezone.utc), stats={},
                        top_historias=[], seleccion=SeleccionJefe(elegidas=[], reserva=[]), piezas=[])
    informe.escribir(inf, cfg.dir_informes / "2026-11-02")
    a = Almacen(cfg.ruta_db)
    dato = {"propuesta": {"formato": "lateral", "titular": "La vivienda", "de_que_se_habla": "x", "cuestion_de_fondo": "y",
                          "gancho_libro": "z", "potencial": 7, "por_que_dura": "sigue", "reactivar": "una ley"},
            "libros": [LIBRO.model_dump(mode="json")], "puente": [4, "ok"], "cosecha": None}
    a.guardar_fondo("2026-11", [{"formato": "lateral", "titular": "La vivienda", "cuestion": "y", "vale_hasta": "2099-01-01", "datos": dato},
                                {"formato": "dialogo", "titular": "Caducada", "cuestion": "w", "vale_hasta": "2000-01-01", "datos": dato}])
    c = TestClient(crear_app(cfg, a))
    lista = c.get("/api/fondo").json()
    assert [p["titular"] for p in lista["propuestas"]] == ["La vivienda"] and lista["propuestas"][0]["puente"] == 4
    textos = []
    from folio_api.rutas import fondo as ruta
    from folio_api.rutas.temas import TemaCreado
    monkeypatch.setattr(ruta, "_resultado", lambda ctx, eid, tid: textos.append(next(t.texto for t in a.temas() if t.id == tid))
                        or TemaCreado(tema=next(t for t in a.temas() if t.id == tid), pieza_id="2026-11-02-7"))
    r = c.post("/api/fondo/1/escribir", json={"ejecucion": 1})
    assert r.status_code == 200 and r.json()["pieza_id"] == "2026-11-02-7"
    assert "Del fondo del mes" in textos[0] and "Eichmann en Jerusalén" in textos[0] and "con su fecha" in textos[0]
    assert a.fondo()[0]["estado"] == "usada" and a.fondo()[0]["tema_id"] == 1
    assert c.post("/api/fondo/1/escribir", json={"ejecucion": 1}).status_code == 409
    assert c.post("/api/fondo/2/descartar").json()["estado"] == "descartada"


def test_si_el_catalogo_no_responde_queda_por_confirmar(cfg, monkeypatch):
    """2/11: Google Books respondía 503 y las propuestas caían por «edición española: desconocido»."""
    from folio.modelos import LibroDescartado
    from folio.pipeline import Pipeline
    monkeypatch.setattr(fondo, "REPARTO_MES", {"lateral": 3})
    monkeypatch.setattr(Pipeline, "_preverificar", lambda self, e: None)
    caido = ([], [LibroDescartado(titulo="X", autor="Y", motivo="sin edición en castellano verificada (edición española: desconocido)")])
    monkeypatch.setattr(Pipeline, "_verificar_libros", lambda self, e, usados: caido)
    a = Almacen(cfg.ruta_db)
    llm = LLMFondo(cfg)
    monkeypatch.setattr(puentes, "evaluar", lambda llm, sel: (sel, {}, []))
    r = fondo.preparar_tanda(cfg, a, "2026-11-02", llm, n=3)
    xs = a.fondo(estado="disponible")
    assert r.guardadas == 3 and all(x["datos"]["por_verificar"] and not x["datos"]["libros"] for x in xs)
    assert "Eichmann" in fondo.texto_tema(xs[0]) and any("por confirmar" in av for av in r.avisos)
    # Al reverificar con el catálogo de vuelta, quedan completas; si el libro no está traducido, fuera
    respuestas = iter([([LIBRO.model_copy()], []), ([], [LibroDescartado(titulo="X", autor="Y", motivo="sin edición en castellano verificada (edición española: no)")]), caido])
    monkeypatch.setattr(Pipeline, "_verificar_libros", lambda self, e, usados: next(respuestas))
    avisos = fondo.reverificar(cfg, a, "2026-11-03", llm)
    assert "1 confirmados, 1 descartados, 1 siguen pendientes" in avisos[0]
    assert len([x for x in a.fondo(estado="disponible") if x["datos"]["libros"]]) == 1
