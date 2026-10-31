from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from folio import edicion, informe
from folio.almacen import Almacen
from folio.modelos import InformeDiario, Pieza, SeleccionJefe
from folio_api.main import crear_app

from datos import ELECCION, FUENTES, LIBRO, guion_valido

RUTA = "/api/ejecuciones/1/piezas/2026-10-30-1"


@pytest.fixture
def app(cfg):
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    pieza = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1", eleccion=ELECCION,
                  n_medios=3, libros=[LIBRO], guion=guion_valido(), fuentes=FUENTES)
    informe.escribir(InformeDiario(fecha="2026-10-30", generado_en=datetime(2026, 10, 30, tzinfo=timezone.utc), stats={},
                                   top_historias=[], seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]), piezas=[pieza]),
                     cfg.dir_informes / "2026-10-30")
    return crear_app(cfg, Almacen(cfg.ruta_db))


def test_editar_una_diapositiva_es_una_version_manual(app):
    c = TestClient(app)
    r = c.put(f"{RUTA}/diapositivas/2", json={"texto": "Un  tribunal juzga\\na un funcionario que firmaba órdenes sin leerlas."})
    assert r.status_code == 200 and r.json()["version"] == 2
    ficha = c.get(RUTA).json()
    assert ficha["version"] == 2 and ficha["pieza"]["guion"]["diapositivas"][1]["texto"].startswith("Un tribunal juzga")
    assert ficha["versiones"][-1]["origen"] == "manual"
    assert "firmaba órdenes sin leerlas" in c.get(f"{RUTA}/diapositivas/2.html?version=2").text


def test_la_edicion_que_rompe_una_regla_se_guarda_con_aviso(app):
    c = TestClient(app)
    r = c.put(f"{RUTA}/diapositivas/1", json={"texto": "¿Obedecer es elegir?", "subtitulo": "Hannah Arendt lo vio en el juicio de Jerusalén: el mal puede ser obra de gente corriente."})
    assert r.status_code == 200 and any("pregunta" in a for a in r.json()["avisos"])
    assert c.get(RUTA).json()["pieza"]["guion"]["diapositivas"][0]["texto"] == "¿Obedecer es elegir?"


def test_el_cierre_editado_conserva_la_firma(cfg):
    p = Pieza(id="x", fecha="2026-10-30", estado="propuesta", historia_id="h1", eleccion=ELECCION, n_medios=1,
              libros=[LIBRO], guion=guion_valido(), fuentes=FUENTES)
    nueva, _ = edicion.editar_diapositiva(cfg, p, 5, "«Eichmann en Jerusalén», de Hannah Arendt. Léelo hoy")
    assert nueva.guion.diapositivas[4].texto.endswith("Léelo hoy. Folio.") and p.guion.diapositivas[4].texto.endswith("Folio.")


class ChatFalso:
    """Devuelve en orden las respuestas preparadas."""

    def __init__(self, respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        assert etapa_modelo == "chat" and esquema is edicion.RespuestaChat
        self.llamadas.append(mensajes)
        return self.respuestas.pop(0), []


def test_chat_que_solo_contesta_no_cambia_nada(app):
    app.state.folio.llm = ChatFalso([edicion.RespuestaChat(respuesta="El titular ya tiene 6 palabras.")])
    c = TestClient(app)
    r = c.post(f"{RUTA}/chat", json={"mensaje": "¿Cuántas palabras tiene el titular?"}).json()
    assert r == {"respuesta": "El titular ya tiene 6 palabras.", "version": None, "avisos": []}
    assert [m["rol"] for m in c.get(f"{RUTA}/chat").json()] == ["usuario", "editor"] and c.get(RUTA).json()["version"] == 1


def test_chat_corrige_en_el_mismo_turno_y_guarda_la_version(app):
    malo = guion_valido()
    malo.diapositivas[0].texto = "¿La obediencia también se elige?"
    bueno = guion_valido()
    bueno.diapositivas[0].texto = "Obedecer también es una elección"
    llm = ChatFalso([edicion.RespuestaChat(respuesta="Hecho.", guion=malo),
                     edicion.RespuestaChat(respuesta="Cambiado el titular, sin pregunta.", guion=bueno)])
    app.state.folio.llm = llm
    c = TestClient(app)
    r = c.post(f"{RUTA}/chat", json={"mensaje": "Haz el titular más directo"}).json()
    assert r["version"] == 2 and "Intento 1 rechazado" in r["avisos"][0] and "pregunta" in r["avisos"][0]
    assert "pregunta" in llm.llamadas[1][-1]["content"]                     # le devolvió los errores
    ficha = c.get(RUTA).json()
    assert ficha["pieza"]["guion"]["diapositivas"][0]["texto"] == "Obedecer también es una elección"
    assert ficha["versiones"][-1]["origen"] == "chat" and edicion.AVISO_CHAT in ficha["pieza"]["revision_humana"]
    assert c.get(f"{RUTA}/chat").json()[-1]["version_n"] == 2
    # El segundo turno lleva la conversación anterior
    llm.respuestas = [edicion.RespuestaChat(respuesta="Vale.")]
    c.post(f"{RUTA}/chat", json={"mensaje": "Gracias"})
    assert "Haz el titular más directo" in [m["content"] for m in llm.llamadas[-1]]


def test_chat_que_no_consigue_cumplir_las_reglas_no_cambia_nada(app, cfg):
    malo = guion_valido()
    malo.libros[0].titulo = "Libro inventado"
    app.state.folio.llm = ChatFalso([edicion.RespuestaChat(respuesta="Hecho.", guion=malo)] * (cfg.pipeline.guion.reintentos + 1))
    c = TestClient(app)
    r = c.post(f"{RUTA}/chat", json={"mensaje": "Cambia el libro por otro"}).json()
    assert r["version"] is None and r["respuesta"].startswith("No he podido hacer ese cambio")
    assert c.get(RUTA).json()["version"] == 1


def test_lo_que_ya_incumplia_no_bloquea_el_chat(app):
    c = TestClient(app)
    c.put(f"{RUTA}/diapositivas/1", json={"texto": "¿Obedecer es elegir?",
                                          "subtitulo": "Hannah Arendt lo vio en el juicio de Jerusalén: el mal puede ser obra de gente corriente."})
    revisado = guion_valido()
    revisado.diapositivas[0].texto = "¿Obedecer es elegir?"          # sigue con la pregunta de antes
    revisado.diapositivas[3].texto = "El mal administrativo necesita gente que no pregunta nada."
    app.state.folio.llm = ChatFalso([edicion.RespuestaChat(respuesta="Cambiada la idea.", guion=revisado)])
    r = c.post(f"{RUTA}/chat", json={"mensaje": "Afina la idea"}).json()
    assert r["version"] == 3 and r["avisos"] == []
