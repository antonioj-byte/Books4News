"""«Perfil de autor» (6/11): frases literales, años de la trayectoria, corrección mecánica, render B y C y la mesa."""
import pytest

from folio import formatos, perfil, render, seleccion
from folio.modelos import (Arte, EdicionEspanola, FuenteNoticia, HistoriaElegida, LibroCandidato, LibroVerificado,
                           Pieza)
from folio.perfil import GuionPerfil, HitoPerfil, PrensaPerfil, VozPerfil

ENTREVISTA = ("Margarita García Robayo nació en Cartagena de Indias en 1980 y vive en Buenos Aires desde 2003. "
              "En 2014 publicó Hasta que pase un huracán. «Escribo sobre la familia porque es el lugar del que nunca "
              "terminamos de irnos», dice en la entrevista. Este año ha ganado el Premio Herralde.")
RESENA = "La crítica de El Cultural: una prosa afilada que no se aparta de lo incómodo. Margarita García Robayo, en 2026."
TEXTOS = [(FuenteNoticia(medio="El País", titulo="Entrevista", url="https://elpais.com/a", acceso="abierto", prensa=True),
           ENTREVISTA),
          (FuenteNoticia(medio="El Cultural", titulo="Reseña", url="https://elcultural.com/b", acceso="abierto",
                         prensa=True), RESENA)]
LIBRO = LibroVerificado(titulo="Hasta que pase un huracán", titulo_propuesto="Hasta que pase un huracán",
                        autores=["Margarita García Robayo"], anio_primera_edicion=2014, idioma_original="español",
                        edicion_es="si", edicion_es_detalle=EdicionEspanola(editorial="Charco Press", anio="2015"),
                        fuentes_verificacion=["openlibrary"], confianza="alta")


def _guion(**k) -> GuionPerfil:
    datos = dict(
        obituario=False, titular="Margarita García Robayo, la escritora que volvió a buscar a los suyos",
        remate="volvió a buscar a los suyos",
        subtitulo="El Premio Herralde reconoce una obra que lleva veinte años mirando la familia y la herencia que se calla",
        porque_titulo="De Cartagena a Buenos Aires", porque_remate="a Buenos Aires",
        porque_texto=("Nació en Cartagena de Indias en 1980 y vive en Buenos Aires desde 2003. Escribe novela, cuento y "
                      "ensayo, y este año ha ganado el Premio Herralde con una novela que viaja detrás de unos antepasados."),
        trayectoria_titulo="De su primer libro al Herralde", trayectoria_remate="al Herralde",
        hitos=[HitoPerfil(anio="1980", texto="Nace en Cartagena de Indias"),
               HitoPerfil(anio="2014", texto="Publica *Hasta que pase un huracán*"),
               HitoPerfil(anio="2026", texto="Premio Herralde")],
        obra_titulo="La familia como un país", obra_remate="un país",
        obra_texto=("En *Hasta que pase un huracán* una mujer quiere irse de su ciudad y de su familia, y no lo consigue "
                    "del todo. Esa tensión entre quedarse y escapar atraviesa todos sus libros, contada sin adornos."),
        voz=VozPerfil(texto="Escribo sobre la familia porque es el lugar del que nunca terminamos de irnos",
                      remate="nunca terminamos de irnos", origen="entrevista", atribucion="En una entrevista con El País",
                      fuente_url="https://elpais.com/a"),
        prensa=[PrensaPerfil(texto="una prosa afilada que no se aparta de lo incómodo", medio="El Cultural",
                             fuente_url="https://elcultural.com/b")],
        cierre="Si nunca la has leído, empieza por su libro más breve", remate_cierre="su libro más breve",
        cierre_texto="*Hasta que pase un huracán* tiene todo lo que el Herralde premia ahora: la familia, la vergüenza y una frase que no se aparta.",
        pie_instagram=" ".join(["García Robayo"] + ["palabra"] * 80), titulares_alternativos=["Uno", "Otro titular"])
    datos.update(k)
    return GuionPerfil(**datos)


def _pieza(**k) -> Pieza:
    e = HistoriaElegida(formato="perfil", historia_id="h1", titular="García Robayo gana el Herralde",
                        de_que_se_habla="El premio", cuestion_de_fondo="", protagonista="Margarita García Robayo",
                        libros_candidatos=[LibroCandidato(titulo="Hasta que pase un huracán", autor="Margarita García Robayo")],
                        por_que="Premio Herralde")
    datos = dict(id="2026-11-06-3", fecha="2026-11-06", estado="pendiente", historia_id="h1", eleccion=e, n_medios=2,
                 libros=[LIBRO])
    datos.update(k)
    return Pieza(**datos)


def _errores(g, **k):
    return [m for _, m in perfil.validar(g, TEXTOS, [LIBRO], "2026-11-06", "Margarita García Robayo", **k)]


def test_el_formato_es_de_la_mesa_en_el_hueco_del_mundo_del_libro():
    f = formatos.de("perfil")
    assert f.propio == "perfil" and f.en_mesa and not f.exige_novedad and not f.firma_folio
    assert not formatos.fuera_de_la_mesa("perfil") and formatos.fuera_de_la_mesa("newsletter")
    assert seleccion.ALIAS_REPARTO["perfil"] == "edicion" and "perfil" in seleccion.NOMBRES_FORMATO


def test_un_guion_bueno_valida():
    assert _errores(_guion()) == []


def test_la_frase_de_su_voz_y_la_prensa_tienen_que_ser_literales():
    mala = VozPerfil(texto="Escribo sobre la familia porque es el lugar del que siempre nos vamos", remate="nos vamos",
                     origen="entrevista", atribucion="", fuente_url="")
    errores = perfil.validar(_guion(voz=mala), TEXTOS, [LIBRO], "2026-11-06", "Margarita García Robayo")
    assert [p for p, _ in errores] == ["voz"]
    prensa = [PrensaPerfil(texto="una prosa sin miedo a nada", medio="El Cultural", fuente_url="")]
    assert [p for p, _ in perfil.validar(_guion(prensa=prensa), TEXTOS, [LIBRO], "2026-11-06", "García Robayo")] == ["prensa"]
    # Una frase de un libro vale si Google Books la encuentra
    del_libro = VozPerfil(texto="Una frase que solo está en el libro", remate="en el libro", origen="libro",
                          atribucion="En *Hasta que pase un huracán*", fuente_url="")
    assert _errores(_guion(voz=del_libro), cita_de_libro=lambda f, l: True) == []
    assert _errores(_guion(voz=del_libro), cita_de_libro=lambda f, l: False)


def test_los_anios_de_la_trayectoria_salen_de_los_textos_o_las_fichas():
    hitos = [HitoPerfil(anio="1980", texto="Nace en Cartagena"), HitoPerfil(anio="2009", texto="Primer libro"),
             HitoPerfil(anio="2026", texto="Premio Herralde")]
    assert any("2009" in e for e in _errores(_guion(hitos=hitos)))
    # 2015, el de la edición española de la ficha, sí vale
    hitos[1] = HitoPerfil(anio="2015", texto="Sale en España")
    assert _errores(_guion(hitos=hitos)) == []
    desordenados = [hitos[2], hitos[0], hitos[1]]
    assert any("orden cronológico" in e for e in _errores(_guion(hitos=desordenados)))


def test_nada_entre_comillas_fuera_de_la_voz_y_la_prensa():
    texto = _guion().porque_texto + " Dice que «la familia es un país»."
    assert any("entre comillas" in e for e in _errores(_guion(porque_texto=texto)))


class _LLM:
    def __init__(self, guiones):
        self.guiones, self.llamadas = list(guiones), []

    def estructurado(self, paso, mensajes, esquema, **k):
        self.llamadas.append((paso, k.get("etapa_modelo")))
        return self.guiones.pop(0), None


def test_si_solo_falla_la_voz_sale_sin_ella_con_aviso(cfg):
    mala = VozPerfil(texto="Una frase que no está en ninguna parte del texto", remate="del texto", origen="entrevista",
                     atribucion="", fuente_url="")
    llm = _LLM([_guion(voz=mala), _guion(voz=mala)])
    p = _pieza()
    perfil.preparar(llm, cfg, p, TEXTOS)
    assert [x[1] for x in llm.llamadas] == ["perfil", "perfil_correccion"]
    assert "cita" not in [d.tipo for d in p.guion.diapositivas]
    assert any(perfil.AVISO_SIN_VOZ in a for a in p.avisos) and p.revision_humana


def test_si_falla_otra_cosa_tras_el_reintento_no_sale(cfg):
    from folio.llm import ErrorLLM
    llm = _LLM([_guion(titular="Hola"), _guion(titular="Hola")])
    with pytest.raises(ErrorLLM):
        perfil.preparar(llm, cfg, _pieza(), TEXTOS)


def test_la_pieza_tiene_siete_diapositivas_y_sus_citas(cfg):
    p = _pieza()
    perfil.preparar(_LLM([_guion()]), cfg, p, TEXTOS)
    assert [d.tipo for d in p.guion.diapositivas] == ["portada", "actualidad", "trayectoria", "libro", "cita", "prensa", "cierre"]
    assert perfil.hitos_de(p.guion.diapositivas[2].texto)[1] == ("2014", "Publica *Hasta que pase un huracán*")
    assert perfil.prensa_de(p.guion.diapositivas[5].texto) == [("Una prosa afilada que no se aparta de lo incómodo", "El Cultural")]
    assert {c.tipo for c in p.citas} == {"prensa"} and len(p.citas) == 2
    assert p.arte.antetitulo == "Perfil" and p.arte.remates_noticias[perfil.R_VOZ] == "nunca terminamos de irnos"
    # Al editar: las frases solo pueden ser las verificadas
    assert perfil.validar_edicion(cfg, p, p.guion) == []
    g = p.guion.model_copy(deep=True)
    g.diapositivas[4].texto = "Otra frase inventada por el chat"
    assert perfil.validar_edicion(cfg, p, g)


def test_el_estilo_se_alterna_en_el_dia_y_el_obituario_va_en_revista():
    a = _pieza(id="2026-11-06-1", arte=Arte(tono="reflexivo", recurso="collage"))
    b = _pieza(id="2026-11-06-2", arte=Arte(tono="reflexivo", recurso=""))
    assert perfil.estilo_del_dia(b, [a]) == "revista"
    assert perfil.estilo_del_dia(_pieza(arte=Arte(tono="grave", recurso="")), [b]) == "revista"
    assert perfil.estilo_del_dia(b, []) in perfil.ESTILOS


@pytest.fixture
def cfg_diseno(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    return cfg


@pytest.mark.parametrize("estilo", perfil.ESTILOS)
def test_render_de_cada_diapositiva(cfg_diseno, estilo):
    p = _pieza()
    perfil.preparar(_LLM([_guion()]), cfg_diseno, p, TEXTOS)
    p.arte.recurso, p.arte.acento = estilo, "pluma"
    pl = render.Plantillas(cfg_diseno)
    html = [pl.html_diapositiva(p, n) for n in range(1, 9)]
    assert f"pf--{estilo}" in html[0] and "Perfil" in html[0]
    assert 'la escritora que <span class="remate">volvió a buscar a los suyos</span>' in html[0]
    assert "Quién es" in html[1] and html[2].count('class="pf-hito"') == 3
    assert "Su obra" in html[3] and "pf-cubiertas" in html[3]
    assert '<span class="remate">nunca terminamos de irnos</span>' in html[4] and "En una entrevista con El País" in html[4]
    assert "El Cultural" in html[5] and "Por dónde empezar" in html[6] and "Charco Press" in html[6]
    assert "colofon" in html[7]


def test_render_del_obituario(cfg_diseno):
    p = _pieza()
    perfil.preparar(_LLM([_guion(obituario=True)]), cfg_diseno, p, TEXTOS)
    pl = render.Plantillas(cfg_diseno)
    portada = pl.html_diapositiva(p, 1)
    assert "In memoriam" in portada and " grave" in portada and "acento--" not in portada
    assert "Para recordarla" in pl.html_diapositiva(p, 7)


def test_el_pipeline_busca_prensa_de_la_persona_y_escribe_con_el_modulo(cfg, monkeypatch):
    import httpx
    from folio import temas
    from folio.modelos import Historia
    from folio.pipeline import Pipeline
    html = "<html><body><article><p>" + ("Margarita García Robayo habla de su obra. " * 30) + "</p></article></body></html>"
    monkeypatch.setattr(temas, "_cliente", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html))))

    class LLM(_LLM):
        def __init__(self):
            super().__init__([_guion()])
            self.cfg, self.trazas, self.prompts = cfg, [], []

        def con_busqueda(self, paso, prompt, **k):
            self.prompts.append((paso, prompt))
            return "resultados", {"https://elpais.com/entrevista"}

        def estructurado(self, paso, mensajes, esquema, **k):
            if paso == "tema-fuentes-fichas":
                return esquema(fuentes=[{"medio": "El País", "titulo": "E", "url": "https://elpais.com/entrevista"}]), ""
            return super().estructurado(paso, mensajes, esquema, **k)

    llm = LLM()
    t = Pipeline(cfg, "2026-11-06", llm=llm)
    h = Historia(id="h1", articulos=[], n_medios=1, medios=["El País"], titular_es="T", resumen_es="R", carril="editorial")
    p = _pieza()
    textos = t._prensa_del_libro(p, h, [])
    assert llm.prompts[0][0] == "prensa-autor" and "Margarita García Robayo" in llm.prompts[0][1]
    assert [f.medio for f, _ in textos] == ["El País"] and textos[0][0].prensa
    t._escribir(p, TEXTOS)
    assert p.estado == "propuesta" and p.guion.diapositivas[2].tipo == "trayectoria"
    assert [x[0] for x in llm.llamadas] == ["perfil:2026-11-06-3:1"]
    assert perfil.fichas(p)[0][0].medio == "Fichas verificadas de los libros"


def test_la_comprobacion_cortada_se_repite_con_esfuerzo_bajo(cfg):
    """6/11: en el perfil real, el razonamiento de Haiku se comía el tope y el JSON llegaba sin cerrar."""
    from folio import hechos
    from folio.llm import RespuestaCortada
    from folio.modelos import ComprobacionHechos

    class LLM:
        def __init__(self):
            self.cfg, self.etapas = cfg, []

        def estructurado(self, paso, mensajes, esquema, **k):
            self.etapas.append((k["etapa_modelo"], k["max_tokens"]))
            if len(self.etapas) == 1:
                raise RespuestaCortada("cortada")
            return ComprobacionHechos(hechos=[]), None

    llm = LLM()
    p = _pieza()
    perfil.preparar(_LLM([_guion()]), cfg, p, TEXTOS)
    assert hechos.comprobar(llm, p.id, p.guion, TEXTOS) == []
    assert llm.etapas == [("comprobacion", hechos.MAX_TOKENS), ("comprobacion_corta", hechos.MAX_TOKENS)]


def _accion(**k):
    from folio import edicion
    base = dict(tipo="libros", enfoque_x=50, enfoque_y=50, composicion="", consultas=[], escena="", persona="", estilo="",
                material="", como="", destacado="", antetitulo="", acento="", libro="", autor="", sin_castellano="",
                editorial="", isbn="", desde=0)
    return edicion.AccionImagen(**{**base, **k})


@pytest.fixture
def verificador_simulado(monkeypatch):
    """Tiempo muerto pasa; cualquier otro libro nuevo, no."""
    from folio.modelos import LibroDescartado
    from folio.pipeline import Pipeline

    def verificar(self, pieza, reservados):
        c = pieza.eleccion.libros_candidatos[0]
        if c.titulo == "Tiempo muerto":
            pieza.libros = [LIBRO.model_copy(update={"titulo": "Tiempo muerto", "titulo_propuesto": "Tiempo muerto",
                                                     "anio_primera_edicion": 2017})]
            return True
        pieza.libros_descartados = [LibroDescartado(titulo=c.titulo, autor=c.autor, motivo="no aparece en los catálogos")]
        return False
    monkeypatch.setattr(Pipeline, "_verificar", verificar)
    monkeypatch.setattr(Pipeline, "_cubiertas_de", lambda self, p: None)


def test_el_chat_fija_los_libros_sin_dejar_la_pieza_pendiente(cfg, verificador_simulado):
    """6/11 («me irrita increíblemente la estrechez»): «usa estos libros para la diapo 4» se verifica al momento."""
    from folio import edicion
    p = _pieza()
    perfil.preparar(_LLM([_guion()]), cfg, p, TEXTOS)
    p.estado = "propuesta"
    a = _accion(libros=["Tiempo muerto — Margarita García Robayo", "*Hasta que pase un huracán*", "La encomienda"])
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, a)
    assert [l.titulo_propuesto for l in nueva.libros] == ["Tiempo muerto", "Hasta que pase un huracán"]
    assert [lg.titulo for lg in nueva.guion.libros] == ["*Tiempo muerto*", "*Hasta que pase un huracán*"]
    assert nueva.estado == "propuesta" and nueva.guion is not None
    assert "Verificados ahora: Tiempo muerto" in nota and "«La encomienda»: no aparece" in nota
    # En un perfil, «cambiar_libro» ya no la deja pendiente: el nuevo va primero y los demás se quedan
    nueva, _ = edicion.aplicar_imagen(None, cfg, p, _accion(tipo="cambiar_libro", libro="Tiempo muerto",
                                                            autor="Margarita García Robayo"))
    assert nueva.estado == "propuesta" and nueva.libros[0].titulo_propuesto == "Tiempo muerto"


def test_el_turno_del_chat_aplica_los_libros_antes_de_validar_el_guion(cfg, verificador_simulado):
    from folio import edicion

    p = _pieza()
    perfil.preparar(_LLM([_guion()]), cfg, p, TEXTOS)
    g = p.guion.model_copy(deep=True)
    g.diapositivas[3].texto += " Y *Tiempo muerto* lo lleva al matrimonio."

    class LLM:
        def estructurado(self, paso, mensajes, esquema, **k):
            return edicion.RespuestaChat(respuesta="Hecho: la 4 nombra los dos libros.", guion=g,
                                         imagen=_accion(libros=["Hasta que pase un huracán — Margarita García Robayo",
                                                                "Tiempo muerto — Margarita García Robayo"]), opciones=[]), None

    respuesta, nueva, _ = edicion.chat(LLM(), cfg, p, [], "Usa estos libros para la diapo 4: Hasta que pase un huracán y Tiempo muerto")
    assert nueva is not None and "Tiempo muerto" in nueva.guion.diapositivas[3].texto
    assert [l.titulo_propuesto for l in nueva.libros] == ["Hasta que pase un huracán", "Tiempo muerto"]
    assert len(nueva.guion.libros) == 2 and "Verificados ahora: Tiempo muerto" in respuesta
