"""Objetos de prueba compartidos."""

from folio.modelos import (
    Diapositiva, EdicionEspanola, FuenteNoticia, GuionLLM, HistoriaElegida, LibroCandidato,
    LibroGuion, LibroVerificado,
)

URL = "https://www.theguardian.com/world/2026/oct/30/ejemplo"

LIBRO = LibroVerificado(
    titulo="Eichmann in Jerusalem", titulo_propuesto="Eichmann en Jerusalén", autores=["Hannah Arendt"],
    anio_primera_edicion=1963, idioma_original="inglés", editorial_original="Viking",
    edicion_es="si",
    edicion_es_detalle=EdicionEspanola(titulo="Eichmann en Jerusalén", editorial="Debolsillo", anio="2014",
                                       isbn="9788483460627", pais="España"),
    olid="OL1386647W", fuentes_verificacion=["openlibrary"], confianza="alta",
)

FUENTES = [FuenteNoticia(medio="The Guardian", titulo="Ejemplo", url=URL, acceso="abierto", texto_completo=True)]

ELECCION = HistoriaElegida(
    historia_id="h1", titular="Un juicio que mira al pasado", de_que_se_habla="Dos frases.",
    cuestion_de_fondo="La responsabilidad individual dentro de una maquinaria.",
    libros_candidatos=[LibroCandidato(titulo="Eichmann en Jerusalén", autor="Hannah Arendt"),
                       LibroCandidato(titulo="El jardín de las máquinas tristes", autor="Laura Ferrán")],
    por_que="Porque sí.",
)


def pie(palabras=100, extra=""):
    return ("Arendt lo explicó. Según The Guardian, " + " ".join(["palabra"] * (palabras - 6)) + " " + extra).strip()


def guion_valido(**cambios) -> GuionLLM:
    datos = dict(
        idea_nueva_candidatas=["a", "b", "c"], idea_elegida="b", por_que="Porque es la más defendible.",
        diapositivas=[
            Diapositiva(n=1, tipo="portada", texto="La obediencia también se elige",
                        subtitulo="Hannah Arendt lo vio en el juicio de Jerusalén: el mal puede ser obra de gente corriente."),
            Diapositiva(n=2, tipo="actualidad", texto="Un tribunal juzga a un funcionario que firmaba órdenes."),
            Diapositiva(n=3, tipo="libro", texto="Arendt vio en Eichmann en Jerusalén a un hombre corriente."),
            Diapositiva(n=4, tipo="idea", texto="El mal administrativo necesita gente que no se pregunte nada."),
            Diapositiva(n=5, tipo="cierre", texto="«Eichmann en Jerusalén», de Hannah Arendt. Léelo. Folio."),
        ],
        pie_instagram=pie(),
        libros=[LibroGuion(titulo="Eichmann en Jerusalén", autor="Hannah Arendt",
                           editorial_espanola="Inventada", traductor="Alguien", edicion_original="inglés, X, 1963")],
        fuentes_noticia=[f"The Guardian {URL}"],
    )
    datos.update(cambios)
    return GuionLLM(**datos)
