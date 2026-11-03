"""La agencia (3/11): créditos de cada pieza, Archivo con vigencia, Equipo, Marca, capas de la memoria y «Para» del chat."""

from datetime import date, datetime

from folio import archivo, edicion, equipo
from folio.almacen import Almacen, Gasto
from folio.modelos import Arte, FuenteNoticia, HechoComprobado, Pieza

from datos import ELECCION, LIBRO, guion_valido


def _pieza(pid="2026-11-03-1", **k):
    base = dict(id=pid, fecha="2026-11-03", estado="propuesta", historia_id="h1", eleccion=ELECCION, n_medios=3,
                libros=[LIBRO], guion=guion_valido(), arte=Arte(tono="sereno", recurso="foto", portada="sangre", registro="foto_autor"))
    return Pieza(**{**base, **k})


def _enlazar(cfg):
    """Los archivos de la plataforma (equipo, marca, fuentes, diseño) en la raíz de pruebas."""
    real = type(cfg)(pipeline={}, fuentes=[]).raiz
    (cfg.raiz / "config").mkdir(parents=True, exist_ok=True)
    for nombre in ("equipo.yaml", "marca.yaml", "fuentes.yaml", "fuentes_editoriales.yaml", "editoriales_independientes.yaml"):
        destino = cfg.raiz / "config" / nombre
        if not destino.exists():
            destino.symlink_to((real / "config" / nombre).resolve())
    if not (cfg.raiz / "diseno").exists():
        (cfg.raiz / "diseno").symlink_to((real / "diseno").resolve())


def _gasto(concepto, detalle, coste=0.1, servicio="anthropic", moneda="USD"):
    return Gasto(ts=datetime.now().isoformat(), fecha=date.today().isoformat(), servicio=servicio, concepto=concepto,
                 unidades=1, coste=coste, moneda=moneda, detalle=detalle)


def test_el_equipo_se_carga_y_cada_concepto_tiene_un_solo_rol(cfg):
    _enlazar(cfg)
    eq = equipo.equipo(cfg)
    assert len(eq.roles) >= 10 and set(eq.departamentos) == {"Estrategia", "Creatividad", "Arte", "Calidad"}
    conceptos = [c for r in eq.roles for c in r.conceptos]
    assert len(conceptos) == len(set(conceptos))
    assert equipo.rol_de_concepto(cfg, "guion").id == "guionista" and equipo.rol_de_concepto(cfg, "ilustración").id == "ilustrador"
    for r in eq.roles:
        assert r.etapa is None or r.etapa in cfg.pipeline.modelos, r.id


def test_creditos_de_una_pieza(cfg, tmp_path):
    _enlazar(cfg)
    a = Almacen(tmp_path / "f.db")
    pid = "2026-11-03-1"
    for g in (_gasto("guion", f"guion:{pid}:1", 0.3), _gasto("guion", f"guion:{pid}:2", 0.1), _gasto("hechos", f"hechos:{pid}", 0.002),
              _gasto("claridad", f"claridad:{pid}"), _gasto("ilustración", pid, 0.025, "magnific", "EUR"),
              _gasto("guion", "guion:2026-11-03-10:1", 9.0)):            # otra pieza con un id que empieza igual
        a.apuntar_gasto(g)
    p = _pieza(pid, avisos=["Puente 3/5: une por el tema"],
               hechos=[HechoComprobado(afirmacion="x", donde="diapositiva 2", tipo="cifra", verificado=False)],
               fuentes=[FuenteNoticia(medio="El Cultural", titulo="Reseña", url="https://x.es", acceso="abierto", prensa=True)])
    c = {x.rol: x for x in equipo.creditos(cfg, a, p)}
    assert list(c)[0] == "jefe_cultura"
    assert c["guionista"].que == "lo escribió (2 intentos)" and c["guionista"].coste_usd == 0.4
    assert c["comprobador"].alerta and "1 hecho" in c["comprobador"].que
    assert c["evaluador_puentes"].alerta and c["documentalista"].que.startswith("encontró 1")
    assert c["ilustrador"].coste_eur == 0.025 and "lector_sin_contexto" in c
    assert c["director_arte"].que == "foto del autor"
    # Un tema de la redacción lo propone la redacción
    t = equipo.creditos(cfg, None, _pieza("tema-3", historia_id="tema-3", eleccion=ELECCION.model_copy(update={"formato": "noticia"})))
    assert t[0].rol == "redaccion" and "solo la noticia" in t[0].que


def test_vigencia_y_categoria():
    hoy = date(2026, 11, 20)
    reciente = _pieza(fuentes=[FuenteNoticia(medio="m", titulo="t", url="u", acceso="abierto", publicado="2026-11-18")])
    vieja = _pieza(fuentes=[FuenteNoticia(medio="m", titulo="t", url="u", acceso="abierto", publicado="2026-11-01")])
    assert archivo.vigencia(reciente, "2026-11-18", hoy)[0] == "vigente"
    assert archivo.vigencia(vieja, "2026-11-03", hoy) == ("revisar", "Revisar fechas · 19 días")
    assert archivo.vigencia(_pieza(), "2026-10-01", hoy)[0] == "caducada"
    assert archivo.vigencia(_pieza(eleccion=ELECCION.model_copy(update={"formato": "curiosidad"})), "2026-09-01", hoy)[0] == "atemporal"
    assert archivo.categoria(_pieza(), False) == "nevera"
    assert archivo.categoria(_pieza(estado="aprobada"), True) == "programada"
    assert archivo.categoria(_pieza(estado="pendiente", guion=None), False) == "pendiente"
    assert archivo.categoria(_pieza(estado="descartada"), False) == "descartada"


def test_capa_de_la_memoria_y_para_del_chat(tmp_path):
    a = Almacen(tmp_path / "f.db")
    pid = a.guardar_patron("Cierres solemnes", ["x"], "Cierre ligero", "guionista", capa="marca")
    assert next(p for p in a.patrones() if p.id == pid).capa == "marca"
    a.decidir_patron(pid, "aceptada", capa="oficio")
    assert next(p for p in a.patrones() if p.id == pid).capa == "oficio"
    a.importar_conversacion([{"clave": "k", "fecha": "2026-11-03", "destino": "guionista", "patron": "p" * 12,
                              "propuesta": "q" * 12, "evidencia": ["e"], "capa": "marca"}])
    assert next(p for p in a.patrones() if p.origen == "conversacion").capa == "marca"
    a.anadir_mensaje(1, "x", "usuario", "más corto", para="guionista")
    a.anadir_mensaje(1, "x", "editor", "Hecho", 2, agente="guionista")
    m = a.chat(1, "x")
    assert m[0].para == "guionista" and m[1].agente == "guionista"
    assert a.mensajes_para("guionista", "2000-01-01")[0]["texto"] == "más corto"


def test_el_chat_dice_para_quien_y_quien_respondio(cfg):
    vistos = []

    class LLM:
        def estructurado(self, paso, mensajes, esquema, **k):
            vistos.append(mensajes[-1]["content"])
            return esquema(respuesta="Visto.", guion=None, imagen=None), []

    meta = {}
    edicion.chat(LLM(), cfg, _pieza(), [], "el cierre, más ligero", para="guionista", meta=meta)
    assert str(vistos[0]).startswith("(Para el guionista") and meta["agente"] == "editor_chat"


def test_rutas_de_la_agencia(cfg, monkeypatch):
    from fastapi.testclient import TestClient
    from folio import informe
    from folio.modelos import InformeDiario, SeleccionJefe
    from folio_api.main import crear_app
    p = _pieza()
    inf = InformeDiario(fecha=p.fecha, generado_en=datetime(2026, 11, 3, 5), stats={}, top_historias=[],
                        seleccion=SeleccionJefe(elegidas=[ELECCION], reserva=[]), piezas=[p], coste_total_usd=0)
    informe.escribir(inf, cfg.dir_informes / p.fecha)
    almacen = Almacen(cfg.ruta_db)
    almacen.importar_informes(cfg.dir_informes)
    _enlazar(cfg)
    c = TestClient(crear_app(cfg, almacen))
    arch = c.get("/api/archivo").json()
    assert arch[0]["pieza_id"] == p.id and arch[0]["categoria"] == "nevera"
    eq = c.get("/api/equipo").json()
    assert [d["nombre"] for d in eq] == ["Estrategia", "Creatividad", "Arte", "Calidad"]
    assert c.get("/api/equipo/guionista").json()["modelo"] == cfg.pipeline.modelos["guion"]
    assert c.get("/api/equipo/nadie").status_code == 404
    marca = c.get("/api/marca").json()
    assert marca["nombre"] == "Folio" and {x["nombre"] for x in marca["colores"]} == {"papel", "tinta", "pluma", "marcador"}
    assert any(f["id"] == "noticia" for f in marca["formatos"])
    detalle = c.get(f"/api/ejecuciones/{almacen.ultima_ejecucion(p.fecha)}/piezas/{p.id}").json()
    assert detalle["creditos"][0]["rol"] == "jefe_cultura"
