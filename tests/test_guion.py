from folio import guion
from folio.modelos import Diapositiva, LibroGuion

from datos import ELECCION, FUENTES, LIBRO, guion_valido, pie


def errores(cfg, g):
    return guion.validar(cfg, g, [LIBRO], FUENTES)


def test_guion_valido(cfg):
    assert errores(cfg, guion_valido()) == []


def test_cita_entre_comillas_rechazada(cfg):
    g = guion_valido()
    g.diapositivas[2].texto = "Arendt escribió «la banalidad del mal es lo que nos rodea»."
    assert any("comillas" in e for e in errores(cfg, g))


def test_titulo_entre_comillas_permitido(cfg):
    g = guion_valido()
    g.diapositivas[2].texto = "En «Eichmann en Jerusalén» Arendt describe a un burócrata."
    assert errores(cfg, g) == []


def test_extension_y_estructura(cfg):
    g = guion_valido()
    g.diapositivas[0].texto = "Una portada demasiado larga que tiene bastante más de doce palabras en total aquí"
    g.diapositivas = g.diapositivas[:3]
    es = errores(cfg, g)
    assert any("entre 4 y 7" in e for e in es)
    assert any("máximo 12" in e for e in es)
    assert any("cierre" in e for e in es)


def test_portada_pregunta_y_frase_vetada(cfg):
    g = guion_valido()
    g.diapositivas[0].texto = "¿Quién obedece?"
    g.diapositivas[3].texto = "En un mundo donde todos obedecen, nadie decide."
    es = errores(cfg, g)
    assert any("pregunta" in e for e in es) and any("vetada" in e for e in es)


def test_libro_no_verificado(cfg):
    g = guion_valido(libros=[LibroGuion(titulo="El jardín de las máquinas tristes", autor="Laura Ferrán",
                                        editorial_espanola=None, traductor=None, edicion_original="x")])
    assert any("no está entre los verificados" in e for e in errores(cfg, g))


def test_fuente_inventada_y_pie(cfg):
    g = guion_valido(fuentes_noticia=["El País https://elpais.com/inventada"], pie_instagram=pie(30))
    es = errores(cfg, g)
    assert any("Fuente no reconocida" in e for e in es)
    assert any("entre 80 y 150" in e for e in es)


def test_ajustar_libros_usa_datos_verificados_y_marca_discrepancias():
    g = guion_valido()
    discrepancias = guion.ajustar_libros(g, [LIBRO])
    assert g.libros[0].editorial_espanola == "Debolsillo"
    assert g.libros[0].traductor is None
    assert g.libros[0].edicion_original == "inglés, Viking, 1963"
    # El guionista decía «Inventada» y «X»: no se sobrescribe en silencio
    campos = {(d.campo, d.modelo, d.api) for d in discrepancias}
    assert ("editorial española", "Inventada", "Debolsillo") in campos
    assert ("editorial original", "X", "Viking") in campos


def test_sin_discrepancias_si_los_datos_coinciden():
    g = guion_valido(libros=[LibroGuion(titulo="Eichmann en Jerusalén", autor="Hannah Arendt",
                                        editorial_espanola="DeBolsillo", traductor=None,
                                        edicion_original="inglés, The Viking Press, 1963")])
    assert guion.ajustar_libros(g, [LIBRO]) == []


def test_discrepancia_de_anio_y_editorial_espanola_sin_verificar():
    sin_es = LIBRO.model_copy(update={"edicion_es": "desconocido", "edicion_es_detalle": None})
    g = guion_valido(libros=[LibroGuion(titulo="Eichmann en Jerusalén", autor="Hannah Arendt",
                                        editorial_espanola="Lumen", traductor=None,
                                        edicion_original="inglés, Viking, 1961")])
    campos = {(d.campo, d.modelo, d.api) for d in guion.ajustar_libros(g, [sin_es])}
    assert ("año original", "1961", "1963") in campos
    assert ("editorial española", "Lumen", "sin edición española verificada") in campos


def test_mas_de_cinco_diapositivas_exigen_justificacion(cfg):
    g = guion_valido()
    g.diapositivas.insert(3, Diapositiva(n=4, tipo="libro", texto="Otra diapositiva sobre el libro."))
    for i, d in enumerate(g.diapositivas, 1):
        d.n = i
    assert any("justificacion_extra" in e for e in errores(cfg, g))
    g.justificacion_extra = ["4: el segundo argumento del libro, que la idea necesita."]
    assert errores(cfg, g) == []


def test_no_habla_de_traduccion_si_no_esta_verificado(cfg):
    sin_es = LIBRO.model_copy(update={"edicion_es": "desconocido", "edicion_es_detalle": None})
    g = guion_valido()
    g.diapositivas[-1].texto = "Eichmann en Jerusalén, de Hannah Arendt, aún sin traducir. Léelo. Folio."
    assert any("traducción" in e for e in guion.validar(cfg, g, [sin_es], FUENTES))
    no_es = LIBRO.model_copy(update={"edicion_es": "no", "edicion_es_detalle": None})
    assert guion.validar(cfg, g, [no_es], FUENTES) == []


def test_titulo_para_pieza():
    assert guion.titulo_para_pieza(LIBRO) == "Eichmann en Jerusalén"
    alice = LIBRO.model_copy(update={"edicion_es_detalle": LIBRO.edicion_es_detalle.model_copy(
        update={"titulo": "Siempre Alice / Still Alice"})})
    assert guion.titulo_para_pieza(alice) == "Siempre Alice"
    sin_es = LIBRO.model_copy(update={"edicion_es": "no", "edicion_es_detalle": None})
    assert guion.titulo_para_pieza(sin_es) == "Eichmann in Jerusalem"


def test_prompt_contiene_datos_delimitados(cfg):
    p = guion.construir_prompt(cfg, ELECCION, [(FUENTES[0], "Texto de la noticia")], [LIBRO])
    assert "[pegar]" not in p and "<noticia>" in p and "<libros_verificados>" in p
    assert "Debolsillo" in p


def test_discrepancia_de_traductor():
    con_trad = LIBRO.model_copy(update={"edicion_es_detalle": LIBRO.edicion_es_detalle.model_copy(
        update={"traductor": "Carlos Ribalta"})})
    def g(trad):
        return guion_valido(libros=[LibroGuion(titulo="Eichmann en Jerusalén", autor="Hannah Arendt",
                                               editorial_espanola="Debolsillo", traductor=trad,
                                               edicion_original="inglés, Viking, 1963")])
    assert guion.ajustar_libros(g("Carlos Ribalta"), [con_trad]) == []
    assert [(d.campo, d.api) for d in guion.ajustar_libros(g("Otra Persona"), [con_trad])] == [("traductor", "Carlos Ribalta")]
    assert [(d.campo, d.api) for d in guion.ajustar_libros(g("Carlos Ribalta"), [LIBRO])] == [("traductor", "sin traductor verificado")]


def test_titulo_para_pieza_quita_el_autor_como_subtitulo():
    havel = LIBRO.model_copy(update={"autores": ["Václav Havel"], "edicion_es_detalle": LIBRO.edicion_es_detalle.model_copy(
        update={"titulo": "El poder de los sin poder: Václav Havel"})})
    assert guion.titulo_para_pieza(havel) == "El poder de los sin poder"
    con_subtitulo = LIBRO.model_copy(update={"edicion_es_detalle": LIBRO.edicion_es_detalle.model_copy(
        update={"titulo": "Eichmann en Jerusalén: un estudio sobre la banalidad del mal"})})
    assert guion.titulo_para_pieza(con_subtitulo) == "Eichmann en Jerusalén: un estudio sobre la banalidad del mal"


def test_portada_abre_con_la_noticia_y_el_pie_nombra_el_libro(cfg):
    g = guion_valido()
    g.diapositivas[0].texto = "Arendt: la obediencia también se elige"
    g.pie_instagram = pie().replace("Arendt lo explicó.", "Un tribunal juzga.")
    es = errores(cfg, g)
    assert any("portada abre con la noticia" in e for e in es)
    assert any("pie debe nombrar el libro" in e for e in es)
    g.diapositivas[0].texto = "*Eichmann en Jerusalén* y la obediencia"
    assert any("portada abre con la noticia" in e for e in errores(cfg, g))
    # El pie puede empezar por la noticia si el libro aparece después
    g.diapositivas[0].texto = "La obediencia también se elige"
    g.pie_instagram = pie().replace("Arendt lo explicó.", "Un tribunal juzga.") + " Lo leemos con Arendt."
    assert errores(cfg, g) == []


def test_una_sola_actualidad_y_libro_pronto(cfg):
    g = guion_valido()
    g.diapositivas = [
        Diapositiva(n=1, tipo="portada", texto="Un juicio a la obediencia"),
        Diapositiva(n=2, tipo="actualidad", texto="Un tribunal juzga a un funcionario."),
        Diapositiva(n=3, tipo="actualidad", texto="El funcionario dice que obedecía."),
        Diapositiva(n=4, tipo="libro", texto="Arendt vio en Eichmann en Jerusalén a un hombre corriente."),
        Diapositiva(n=5, tipo="idea", texto="El mal administrativo necesita gente que no se pregunte nada."),
        Diapositiva(n=6, tipo="cierre", texto="Eichmann en Jerusalén, de Hannah Arendt. Léelo. Folio."),
    ]
    g.justificacion_extra = ["3: el segundo dato de la noticia."]
    es = errores(cfg, g)
    assert any("2 diapositivas de actualidad" in e for e in es)
    assert any("entra en la diapositiva 4" in e for e in es)


def test_cierre_nombra_el_libro(cfg):
    g = guion_valido()
    g.diapositivas[-1].texto = "Léelo ahora: un ensayo breve sobre la obediencia. Folio."
    assert any("cierre es la recomendación" in e for e in errores(cfg, g))


def test_afirmaciones_de_traduccion_van_a_revision_humana():
    g = guion_valido()
    g.diapositivas[-1].texto = "Eichmann en Jerusalén, de Hannah Arendt, todavía sin traducir. Folio."
    afirmaciones = guion.afirmaciones_traduccion(g)
    assert len(afirmaciones) == 1 and afirmaciones[0].startswith("diapositiva 5")
    assert guion.afirmaciones_traduccion(guion_valido()) == []


def test_libro_verificado_un_solo_criterio_para_todo():
    """Validación, ficha del informe y PNG emparejan igual un libro del guion con su ficha."""
    from folio import informe, render
    from folio.modelos import Pieza
    from datos import ELECCION
    alice = LIBRO.model_copy(update={
        "titulo": "Still Alice", "titulo_propuesto": "Siempre Alice", "autores": ["Lisa Genova"],
        "edicion_es_detalle": LIBRO.edicion_es_detalle.model_copy(update={"titulo": "Siempre Alice / Still Alice",
                                                                          "editorial": "Ediciones B"})})
    lg = LibroGuion(titulo="Siempre Alice", autor="Lisa Genova", editorial_espanola="Ediciones B",
                    traductor=None, edicion_original="inglés, iUniverse, 2007")
    assert guion.libro_verificado(lg, [LIBRO, alice]) is alice
    assert guion.libro_verificado(lg.model_copy(update={"autor": "Otra Persona"}), [alice]) is None
    assert informe._edicion_es_guion(lg, [alice]) == "sí, Ediciones B"
    g = guion_valido(libros=[lg])
    pieza = Pieza(id="p", fecha="2026-10-30", estado="propuesta", historia_id="h", eleccion=ELECCION,
                  n_medios=1, libros=[alice], guion=g)
    assert render.ficha_libros(pieza)[0]["datos"].startswith("Ediciones B")
