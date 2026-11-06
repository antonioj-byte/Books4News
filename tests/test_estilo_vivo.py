"""El libro de estilo vivo (6/11): ejemplos de la redacción, fichas con ejemplos en los prompts, prueba en el banco,
poda, encargos de código y métricas de Instagram. Sin red ni gasto: modelos, GitHub e Instagram simulados."""

import json
from datetime import date, datetime, timezone

import httpx
import pytest

from folio import edicion, estilo_vivo, informe, metricas
from folio.almacen import Almacen
from folio.llm import cargar_prompt, sin_fichas
from folio.modelos import InformeDiario, Pieza, SeleccionJefe

from datos import ELECCION, LIBRO, guion_valido


def _almacen(cfg, estado="aprobada", editar=True) -> tuple[Almacen, int, Pieza]:
    p = Pieza(id="2026-11-01-1", fecha="2026-11-01", estado="propuesta", historia_id="h1", eleccion=ELECCION,
              n_medios=3, libros=[LIBRO], guion=guion_valido())
    inf = InformeDiario(fecha="2026-11-01", generado_en=datetime(2026, 11, 1, 5, tzinfo=timezone.utc), stats={}, top_historias=[],
                        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]), piezas=[p], coste_total_usd=0)
    informe.escribir(inf, cfg.dir_informes / "2026-11-01")
    a = Almacen(cfg.ruta_db)
    a.importar_informes(cfg.dir_informes)
    eid = a.ultima_ejecucion("2026-11-01")
    if editar:
        nueva, _ = edicion.editar_diapositiva(cfg, p, 2, "Un tribunal juzga desde hoy a un funcionario que firmaba órdenes sin preguntar nunca.")
        a.guardar_version(eid, p.id, nueva, "manual", "a mano", estado=estado)
    else:
        a.cambiar_estado(eid, p.id, estado)
    return a, eid, p


class LLM:
    """Responde según el esquema que le piden."""
    def __init__(self, cfg, respuestas: dict):
        self.cfg, self.respuestas, self.trazas, self.pasos = cfg, respuestas, [], []

    def estructurado(self, paso, mensajes, esquema, **k):
        self.pasos.append(paso)
        r = self.respuestas[esquema.__name__]
        return (r(paso, mensajes) if callable(r) else esquema.model_validate(r)), []


HOY = date(2026, 11, 6)


def test_las_ediciones_se_cosechan_y_las_que_ensenan_entran_en_el_guionista(cfg):
    a, _, _ = _almacen(cfg)
    assert estilo_vivo.cosechar(a, hoy=HOY) == 1
    assert estilo_vivo.cosechar(a, hoy=HOY) == 0                 # no se duplica
    e = a.ejemplos("candidato")[0]
    assert e.tipo == "actualidad" and e.antes.startswith("Un tribunal juzga") and "sin preguntar nunca" in e.despues
    llm = LLM(cfg, {"JuicioEjemplos": {"ejemplos": [{"id": e.id, "ensena": True,
                                                       "leccion": "Precisa lo que hacía la persona: el detalle concreto explica el caso"}]}})
    assert estilo_vivo.elegir_ejemplos(llm, cfg, a) == (1, 0)
    prompt = cargar_prompt(cfg, "chat_edicion", {"[pegar pieza]": "x"})
    assert "Ejemplos de la redacción" in prompt and "firmaba órdenes sin preguntar nunca" in prompt and "el detalle concreto" in prompt
    # El jefe de cultura no los recibe
    assert "Ejemplos de la redacción" not in cargar_prompt(cfg, "estilo_poda", {"[pegar rol]": "x", "[pegar tope]": "1", "[pegar fichas]": "x"})


def test_una_errata_o_un_cambio_de_tema_no_son_ejemplos():
    assert not estilo_vivo._vale_como_ejemplo("El libro salió en 2014 en Madrid.", "El libro salió en 2015 en Madrid.")
    assert not estilo_vivo._vale_como_ejemplo("El gato duerme en la alfombra del salón", "Hacienda publica las cuentas del año pasado")
    assert estilo_vivo._vale_como_ejemplo("En el día de hoy, el tribunal ha decidido juzgar al funcionario",
                                          "Hoy el tribunal juzga al funcionario")


def test_las_fichas_entran_con_sus_ejemplos_y_se_pueden_dejar_fuera(cfg):
    a, _, _ = _almacen(cfg, editar=False)
    fid = a.guardar_patron("Titulares largos", ["2026-11-01-1: titular de 14 palabras"], "Titulares de 8 palabras como mucho.",
                           "guionista", ejemplo_bueno="La obediencia se elige", ejemplo_malo="La obediencia también se elige siempre")
    a.decidir_patron(fid, "aceptada")
    prompt = cargar_prompt(cfg, "chat_edicion", {"[pegar pieza]": "x"})
    assert "Titulares de 8 palabras como mucho. Así sí: «La obediencia se elige». Así no:" in prompt
    with sin_fichas({fid}):
        assert "Titulares de 8 palabras" not in cargar_prompt(cfg, "chat_edicion", {"[pegar pieza]": "x"})
    estilo_vivo.retirar(cfg, a, fid)
    assert a.patron(fid).estado == "retirada"
    assert "Titulares de 8 palabras" not in cargar_prompt(cfg, "chat_edicion", {"[pegar pieza]": "x"})


def test_la_prueba_en_el_banco_compara_a_ciegas_con_y_sin_la_ficha(cfg, monkeypatch):
    from folio import guion as guionista
    from folio.etapas import EtapasGuardadas
    from folio.modelos import FuenteNoticia
    a, _, p = _almacen(cfg, editar=False)
    EtapasGuardadas(cfg.dir_cache(p.fecha)).guardar_textos(p.historia_id, [(FuenteNoticia(medio="El País", titulo="T", url="https://e.es",
                                                                                         acceso="abierto"), "texto")])
    fid = a.guardar_patron("Cierres flojos", ["x"], "El cierre acaba con una imagen, no con un consejo.", "guionista")
    a.decidir_patron(fid, "aceptada")
    vistos = []

    def escribir(llm, pid, eleccion, textos, libros, *args, **k):
        prompt = cargar_prompt(llm.cfg, "chat_edicion", {"[pegar pieza]": "x"})
        con = "acaba con una imagen" in prompt
        vistos.append((pid, con, llm.cfg.pipeline.esfuerzo["guion"]))
        g = guion_valido()
        g.diapositivas[4].texto = "Con la ficha. Folio." if con else "Sin la ficha. Folio."
        return g, [], []
    monkeypatch.setattr(guionista, "escribir", escribir)

    def juez(paso, mensajes):
        from folio.juez import Juicio
        texto = mensajes[0]["content"]
        bloques = texto.split('<version letra="')[1:]
        notas = [{"letra": b[0], "idea": 4 if "Con la ficha" in b else 3, "voz": 4 if "Con la ficha" in b else 2, "publicaria": True,
                  "mejor_frase": "", "peor_frase": "", "por_que_idea": "", "por_que_voz": ""} for b in bloques]
        return Juicio(versiones=notas)
    r = estilo_vivo.probar(LLM(cfg, {"Juicio": juez}), cfg, a, fid)
    assert r["veredicto"] == "mejora" and r["con"] == 4.0 and r["sin"] == 2.5
    assert [v[1] for v in vistos] == [True, False] and all(v[2] == "medium" for v in vistos)
    assert json.loads(a.patron(fid).prueba)["veredicto"] == "mejora"
    assert estilo_vivo.por_probar(a, 5) == []                     # ya probada


def test_la_poda_propone_fusiones_y_al_aceptarla_retira_las_fundidas(cfg):
    cfg.pipeline.estilo.max_activas_por_rol = 5
    a, _, _ = _almacen(cfg, editar=False)
    ids = []
    for i in range(6):
        fid = a.guardar_patron(f"Patrón {i}", ["x"], f"Regla número {i} sobre titulares.", "guionista")
        a.decidir_patron(fid, "aceptada")
        ids.append(fid)
    assert "guionista" in estilo_vivo.a_podar(cfg, a, HOY)
    llm = LLM(cfg, {"Poda": {"fusiones": [{"ids": ids[:2], "regla": "Una sola regla de titulares.", "por_que": "dicen lo mismo"}],
                             "retiros": [{"id": ids[5], "motivo": "repetida"}, {"id": 999, "motivo": "no existe"}]}})
    nuevas = estilo_vivo.podar(llm, cfg, a, HOY)
    assert len(nuevas) == 2
    assert estilo_vivo.podar(llm, cfg, a, HOY) == []               # no repite las mismas propuestas
    fusion = a.patron(nuevas[0])
    assert fusion.origen == "poda" and fusion.estado == "propuesta" and json.loads(fusion.nota) == {"retira": ids[:2]}
    a.decidir_patron(fusion.id, "aceptada")
    estilo_vivo.al_aceptar(cfg, a, fusion.id)
    assert [a.patron(i).estado for i in ids[:3]] == ["retirada", "retirada", "aceptada"]
    retiro = a.patron(nuevas[1])
    a.decidir_patron(retiro.id, "aceptada")
    estilo_vivo.al_aceptar(cfg, a, retiro.id)
    assert a.patron(ids[5]).estado == "retirada" and a.patron(retiro.id).estado == "aplicada"


def test_una_ficha_de_codigo_abre_su_encargo_en_github(cfg, monkeypatch):
    a, _, _ = _almacen(cfg, editar=False)
    fid = a.guardar_patron("Hace falta un control", ["x"], "Comprobar que el pie no pasa de 2.200 caracteres.", "codigo")
    a.decidir_patron(fid, "aceptada")
    # Sin token, el encargo queda en la ficha
    monkeypatch.delenv("FOLIO_GITHUB_TOKEN", raising=False)
    assert "sin FOLIO_GITHUB_TOKEN" in estilo_vivo.al_aceptar(cfg, a, fid)[0]
    assert a.patron(fid).encargo.startswith("pendiente")
    pedidos = []

    def responder(r):
        pedidos.append(json.loads(r.content))
        return httpx.Response(201, json={"html_url": "https://github.com/x/y/issues/7"})
    monkeypatch.setenv("FOLIO_GITHUB_TOKEN", "t")
    avisos = estilo_vivo.encargar(cfg, a, a.patron(fid), "Implementar", cliente=httpx.Client(transport=httpx.MockTransport(responder)))
    assert avisos == [f"Encargo de código de la ficha #{fid}: https://github.com/x/y/issues/7"]
    assert pedidos[0]["labels"] == ["folio-memoria"] and "2.200 caracteres" in pedidos[0]["body"] and "no mergees" in pedidos[0]["body"]
    # Ante 403, se para y se dice
    avisos = estilo_vivo.encargar(cfg, a, a.patron(fid), "Implementar",
                                  cliente=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))))
    assert "403" in avisos[0]


def test_retirar_una_regla_escrita_en_el_prompt_encarga_quitarla(cfg, monkeypatch):
    monkeypatch.delenv("FOLIO_GITHUB_TOKEN", raising=False)
    a, _, _ = _almacen(cfg, editar=False)
    a.importar_conversacion([{"clave": "una-regla", "fecha": "2026-11-01", "destino": "guionista", "patron": "Lo que pidió el usuario",
                              "propuesta": "Una regla que ya está en el prompt.", "evidencia": ["conversación"]}])
    f = next(p for p in a.patrones() if p.clave == "una-regla")
    avisos = estilo_vivo.retirar(cfg, a, f.id)
    assert a.patron(f.id).estado == "retirada" and "Quitar esta regla" in a.patron(f.id).encargo and avisos


# --- Métricas de Instagram ------------------------------------------------------------------

def test_las_metricas_se_casan_por_el_pie_y_llegan_a_la_memoria(cfg, monkeypatch):
    from folio.historial import Historial
    from folio.publicacion.instagram import Instagram
    a, eid, p = _almacen(cfg, estado="publicada", editar=False)
    Historial(cfg.ruta_db).anadir_publicada("2026-11-02", p.id, "t", "texto")
    pie = p.guion.pie_instagram

    def responder(r):
        if r.url.path.endswith("/media"):
            return httpx.Response(200, json={"data": [{"id": "m1", "caption": "Otra cosa distinta del todo, nada que ver aquí ni allí"},
                                                      {"id": "m2", "caption": pie + "\n\nRetrato: …", "permalink": "https://instagram.com/p/x",
                                                       "timestamp": "2026-11-02T09:00:00+0000"}]})
        if r.url.path.endswith("/m2/insights"):
            return httpx.Response(200, json={"data": [{"name": "reach", "values": [{"value": 1234}]},
                                                      {"name": "saved", "values": [{"value": 56}]},
                                                      {"name": "shares", "total_value": {"value": 12}}]})
        return httpx.Response(404, json={"error": {"message": "no"}})
    ig = Instagram("tok", "u1", cliente=httpx.Client(transport=httpx.MockTransport(responder)))
    n, avisos = metricas.medir(cfg, a, date(2026, 11, 6), ig=ig)
    assert n == 1, avisos
    m = a.metricas()[p.id]
    assert (m.alcance, m.guardados, m.compartidos, m.media_id) == (1234, 56, 12, "m2")
    datos = a.feedback("2026-10-20")
    assert datos[0]["publico"]["alcance"] == 1234
    from folio import memoria
    assert "Público en Instagram: alcance 1234, guardados 56, compartidos 12" in memoria._bloque_feedback(datos)


def test_sin_permiso_de_metricas_se_para(cfg):
    from folio.historial import Historial
    from folio.publicacion.instagram import Instagram
    a, _, p = _almacen(cfg, estado="publicada", editar=False)
    Historial(cfg.ruta_db).anadir_publicada("2026-11-02", p.id, "t", "texto")

    def responder(r):
        if r.url.path.endswith("/media"):
            return httpx.Response(200, json={"data": [{"id": "m2", "caption": p.guion.pie_instagram}]})
        return httpx.Response(403, json={"error": {"code": 10, "message": "Application does not have permission"}})
    ig = Instagram("tok", "u1", cliente=httpx.Client(transport=httpx.MockTransport(responder)))
    n, avisos = metricas.medir(cfg, a, date(2026, 11, 6), ig=ig)
    assert n == 0 and any("se para" in x for x in avisos)


def test_sin_token_no_se_mide(cfg, monkeypatch):
    monkeypatch.delenv("INSTAGRAM_TOKEN", raising=False)
    a, _, _ = _almacen(cfg, editar=False)
    assert metricas.medir(cfg, a)[0] == 0


@pytest.fixture(autouse=True)
def _sin_github(monkeypatch):
    monkeypatch.delenv("FOLIO_GITHUB_TOKEN", raising=False)
