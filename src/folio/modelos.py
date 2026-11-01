"""Esquemas de datos del pipeline.

Hay dos familias:
- Salidas de los modelos (ResumenHistoria, SeleccionJefe, GuionLLM): reflejan lo que piden
  los prompts de prompts/ y se usan como esquema de salida estructurada.
- Datos del pipeline (Articulo, Historia, LibroVerificado, Pieza, InformeDiario): los produce
  el código y forman el informe diario; la web de la Fase 3 los reutilizará.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel as _BaseModel, BeforeValidator, ConfigDict, Field


class BaseModel(_BaseModel):
    """Base de los esquemas: en el esquema de salida (OpenAPI de la web) los campos con valor por
    defecto figuran como obligatorios, porque siempre vienen."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


Acceso = Literal["abierto", "parcial", "muro"]
Seccion = Literal[
    "politica", "internacional", "economia", "ciencia", "tecnologia", "sociedad",
    "cultura", "deportes", "sucesos", "salud", "medio_ambiente", "otros",
]
# «pendiente»: propuesta de la mesa del día con su libro verificado, aún sin guion (se desarrolla al pulsar «Proceder»)
EstadoPieza = Literal["pendiente", "propuesta", "en_edicion", "aprobada", "descartada", "publicada", "fallida"]
Formato = Literal["lateral", "dialogo", "edicion", "curiosidad", "recomendado", "radar"]
# Formatos que pueden salir sin libro: la curiosidad del cajón y los temas del radar del libro
SIN_LIBRO_OBLIGATORIO = ("curiosidad", "radar")
# «cajon»: historias sin percha del cajón de curiosidades (config/cajon_curiosidades.yaml); «catalogo»: novedades de
# las editoriales independientes (formato «recomendado»); «radar»: historias del mundo del libro que no pasan al jefe
# pero sí a la lista del radar
Carril = Literal["actualidad", "editorial", "cajon", "catalogo", "radar"]
TipoDiapositiva = Literal["portada", "actualidad", "libro", "idea", "cierre"]


# --- Ingesta -----------------------------------------------------------------

class Articulo(BaseModel):
    id: str
    medio: str
    url: str
    titulo: str
    entradilla: str = ""
    publicado_en: datetime | None = None
    idioma: str
    acceso: Acceso
    carril: Carril = "actualidad"
    tier: int | None = None


class Historia(BaseModel):
    """Grupo de artículos de distintos medios sobre el mismo evento."""
    id: str
    articulos: list[Articulo]
    medios: list[str]
    n_medios: int
    ultima_publicacion: datetime | None = None
    titular_es: str | None = None
    resumen_es: str | None = None
    seccion: Seccion | None = None
    sobre_libros: bool | None = None
    carril: Carril = "actualidad"


class ResumenHistoria(BaseModel):
    """Salida del modelo barato para cada historia."""
    titular_es: str = Field(description="Titular neutro en español, una línea")
    resumen_es: str = Field(description="Qué ha pasado, en una o dos frases, en español")
    seccion: Seccion
    sobre_libros: bool = Field(description="Trata de libros, literatura, autores o la industria editorial")


# --- Selección (prompts/jefe_cultura.md) -------------------------------------

class LibroCandidato(BaseModel):
    titulo: str = Field(description="Título en español si hay edición española; si no, el original")
    autor: str
    titulo_original: str | None = Field(default=None, description="Título en la lengua original")
    idioma_original: str | None = Field(default=None, description="Lengua original de la obra, en español (inglés, alemán…)")


class HistoriaElegida(BaseModel):
    formato: Formato = Field(default="lateral", description="lateral (lectura lateral), dialogo (diálogo con la actualidad), edicion (mundo del libro), curiosidad (del cajón de curiosidades) o recomendado (del catálogo de las independientes)")
    historia_id: str = Field(description="Identificador de la historia tal como aparece en la lista")
    titular: str = Field(description="Titular en una línea")
    de_que_se_habla: str = Field(description="De qué se está hablando, en dos frases")
    cuestion_de_fondo: str = Field(description="La cuestión de fondo, en una frase")
    libros_candidatos: list[LibroCandidato] = Field(description="3–4 libros candidatos, por orden de preferencia (en una curiosidad, de 0 a 4)")
    gancho_libro: str = Field(default="", description="En una línea, cómo entra el libro desde la portada: qué vio, explicó o anticipó su autor")
    por_que: str = Field(description="Por qué esta historia y no otra, en dos líneas")


class SeleccionJefe(BaseModel):
    elegidas: list[HistoriaElegida] = Field(description="Las propuestas del día, por orden de preferencia (la primera se escribe sola)")
    reserva: list[HistoriaElegida] = Field(default_factory=list, description="Vacía: ya no hay reserva, las propuestas sin desarrollar hacen de reserva")
    aviso: str | None = Field(
        default=None,
        description="Si propones menos de las pedidas porque no hay material, explícalo aquí; si no, null",
    )


# --- Libros ------------------------------------------------------------------

class EdicionEspanola(BaseModel):
    titulo: str | None = None
    editorial: str | None = None
    anio: str | None = None
    isbn: str | None = None
    traductor: str | None = None
    pais: str | None = None  # deducido del prefijo ISBN cuando es posible


class LibroVerificado(BaseModel):
    titulo: str                       # título de la obra en la fuente bibliográfica
    titulo_propuesto: str             # como lo propuso el jefe de cultura
    autores: list[str]
    anio_primera_edicion: int | None = None
    idioma_original: str | None = None
    editorial_original: str | None = None
    edicion_es: Literal["si", "no", "desconocido"]
    edicion_es_detalle: EdicionEspanola | None = None
    olid: str | None = None
    google_id: str | None = None
    isbn13: list[str] = Field(default_factory=list)
    fuentes_verificacion: list[Literal["openlibrary", "googlebooks", "todostuslibros"]]
    url_ficha: str | None = None
    confianza: Literal["alta", "media"]
    notas: list[str] = Field(default_factory=list)


class LibroDescartado(BaseModel):
    titulo: str
    autor: str
    motivo: str


# --- Guion (prompts/guionista.md) --------------------------------------------

class Diapositiva(BaseModel):
    n: int
    tipo: TipoDiapositiva
    texto: str
    subtitulo: str | None = Field(default=None, description="Solo en la portada: el subtítulo, que trae el libro o a su autor")


class LibroGuion(BaseModel):
    titulo: str
    autor: str
    editorial_espanola: str | None
    traductor: str | None
    edicion_original: str = Field(description="idioma, editorial, año")


class GuionLLM(BaseModel):
    idea_nueva_candidatas: list[str]
    idea_elegida: str
    por_que: str
    diapositivas: list[Diapositiva]
    justificacion_extra: list[str] = Field(
        default_factory=list,
        description="Solo si usas más de 5 diapositivas: una línea por cada diapositiva extra con lo que aporta",
    )
    pie_instagram: str = Field(description="Texto de 80–150 palabras, con fuente de la noticia")
    libros: list[LibroGuion]
    fuentes_noticia: list[str] = Field(description="medio + URL")


# --- Comprobación de hechos (prompts/comprobador_hechos.md) --------------------

class HechoComprobado(BaseModel):
    afirmacion: str = Field(description="La afirmación tal como aparece en el guion")
    donde: str = Field(description="«diapositiva N» o «pie»")
    tipo: Literal["cifra", "fecha", "nombre", "hecho"]
    verificado: bool
    medio: str | None = Field(default=None, description="Medio cuyo texto la sostiene; null si no está verificada")
    evidencia: str | None = Field(default=None, description="Fragmento literal del texto fuente; null si no está verificada")
    nota: str | None = Field(default=None, description="Si no está verificada, qué falta o qué dice la fuente")


class ComprobacionHechos(BaseModel):
    hechos: list[HechoComprobado]


# --- Pieza e informe ---------------------------------------------------------

class FuenteNoticia(BaseModel):
    medio: str
    titulo: str
    url: str
    acceso: Acceso
    texto_completo: bool = False
    critica: bool = False                # texto de crítica: lo único que se puede citar entre comillas además del libro


class Traza(BaseModel):
    paso: str
    modelo: str
    tokens_entrada: int = 0              # entrada no cacheada
    tokens_salida: int = 0
    tokens_cache_escritura: int = 0
    tokens_cache_lectura: int = 0
    coste_usd: float = 0.0
    segundos: float = 0.0                # lo que tardó la llamada (para saber dónde se va el tiempo)
    nota: str | None = None


class DiscrepanciaEdicion(BaseModel):
    """Dato de edición en que el guionista y la fuente bibliográfica no coinciden."""
    libro: str
    campo: Literal["editorial española", "traductor", "editorial original", "año original"]
    modelo: str
    api: str


# --- Director de arte (prompts/director_arte.md) --------------------------------

RecursoSinFoto = Literal["golpe", "gigante", "teletipo", "collage"]

# Texto opcional en los esquemas de salida del director de arte: cadena, vacía si no hay. Con null en cada
# campo, el esquema es demasiado complejo para las salidas estructuradas; lo guardado con null se sigue leyendo.
Texto = Annotated[str, BeforeValidator(lambda v: "" if v is None else v)]


class _TodoObligatorio(BaseModel):
    """Esquema de salida de un agente con todos los campos en «required»: la API compila el esquema en una
    gramática y cada campo opcional la dobla; con los opcionales anidados del director de arte respondía
    «Schema is too complex». El modelo rellena siempre cada campo (vacío o null si no hay); en Python
    siguen los valores por defecto, para construirlos a mano."""
    model_config = ConfigDict(json_schema_extra=lambda esquema, _: esquema.update(required=list(esquema.get("properties", {}))))


class SinFoto(_TodoObligatorio):
    """Recurso gráfico de la diapositiva de actualidad cuando no lleva foto ni cifra (31/10). Todo lo
    que se pinta sale literalmente del texto de esa diapositiva: el código lo comprueba al validar y
    otra vez al pintar (el texto puede editarse en la web)."""
    recurso: RecursoSinFoto = Field(description="golpe, gigante, teletipo o collage (ver el prompt)")
    golpe: Texto = Field(default="", description="La frase final de la diapositiva de actualidad, copiada literalmente (de 3 a 14 palabras)")
    golpe_remate: Texto = Field(default="", description="El final del golpe, copiado literalmente (de 1 a 4 palabras), que irá en cursiva con marcador")
    palabra: Texto = Field(default="", description="Una palabra de la diapositiva de actualidad, copiada literalmente (de 4 a 12 letras)")
    etiquetas: list[str] = Field(default_factory=list, description="De 2 a 3 etiquetas de 1 o 2 palabras copiadas literalmente de la diapositiva de actualidad")
    numero: Texto = Field(default="", description="Un número de la diapositiva de actualidad (un año, una edad, una cantidad), copiado literalmente, o vacío")
    numero_rotulo: Texto = Field(default="", description="De 1 a 5 palabras de esa misma diapositiva que dicen qué es el número")
    sello: Texto = Field(default="", description="De 1 a 3 palabras de la diapositiva de actualidad, copiadas literalmente, para un sello de estampilla")


class Infografia(_TodoObligatorio):
    """Infografía de la diapositiva de la idea (31/10): «linea» (línea de tiempo del libro y la noticia,
    con los años verificados), «mapa» (noticia → idea → libro, con dos rótulos del guion) o «esquema»
    (ilustración técnica de Magnific a partir de la imagen de la pieza, con tres rótulos del guion). Los
    años los pone el código; los rótulos salen literalmente del guion (folio.infografia)."""
    tipo: Literal["linea", "mapa", "esquema", "ninguna"] = Field(description="linea, mapa, esquema o ninguna (ver el prompt)")
    titulo: Texto = Field(default="", description="De 3 a 8 palabras, sin cifras: lo que cuenta la infografía")
    etiquetas: list[str] = Field(default_factory=list, description="Rótulos copiados literalmente del guion: 2 en el mapa (de 2 a 4 palabras), 3 en el esquema (de 1 a 3 palabras)")


class PropuestaArte(_TodoObligatorio):
    """Primera llamada: qué buscar y qué destacar. La imagen la busca el código."""
    tono: Literal["grave", "sereno", "reflexivo", "ironico", "luminoso"]
    portada: Literal["sangre", "banda", "caja", "neon", "ilustracion", "circulo", "collage"] = Field(
        description="Composición de la portada (ver el prompt)")
    antetitulo: str | None = Field(default=None, description="De 1 a 3 palabras: el tema de la pieza, en mayúsculas")
    remate: str | None = Field(default=None, description="El final del titular de portada, copiado literalmente (de 2 a 6 palabras), que irá en cursiva")
    acento: Literal["pluma", "marcador"] | None = Field(default=None, description="Color de la pieza: pluma (magenta) o marcador (amarillo); null si es grave")
    suceso_con_victimas: bool = Field(description="La noticia trata de muertos, heridos o víctimas")
    recurso: Literal["foto", "grabado", "ilustracion"] = Field(description="Foto de archivo, ilustración antigua (grabado, dibujo) o ilustración editorial nueva (ver el prompt)")
    escena: Texto = Field(default="", description="Con recurso «ilustracion»: la metáfora visual, en inglés, de 12 a 70 palabras, sin nombres propios, personas reales, texto ni marcas")
    pregunta: Texto = Field(default="", description="La pregunta que la noticia deja en el aire, para el buscador de la portada: de 3 a 9 palabras, en minúsculas, sin cifras ni nombres propios")
    consultas: list[str] = Field(default_factory=list, description="3 o 4 búsquedas de 1 a 3 palabras, en inglés, sueco o alemán")
    evitar: list[str] = Field(default_factory=list, description="Lo que la imagen no debe mostrar")
    cifra: str | None = Field(default=None, description="Una cifra copiada literalmente de la diapositiva de actualidad, o null")
    cifra_rotulo: str | None = Field(default=None, description="De 2 a 6 palabras de esa misma diapositiva que explican la cifra")
    sin_foto: SinFoto = Field(description="Recurso gráfico de la diapositiva de actualidad si se queda sin foto ni cifra")
    infografia: Infografia = Field(description="Infografía de la diapositiva de la idea (tipo «ninguna» si ninguna aporta)")
    por_que: str


class EscenaLLM(_TodoObligatorio):
    escena: str = Field(description="Lo que se ve, en inglés, de 20 a 60 palabras, sin nombres propios, personas reales, texto, cifras ni comillas")
    idea: str = Field(description="La metáfora, en español, en una frase")


class EscenasLLM(_TodoObligatorio):
    """El ilustrador (prompts/escena_editorial.md): escenas distintas para la ilustración editorial de la pieza."""
    escenas: list[EscenaLLM] = Field(description="Escenas distintas, cada una con su metáfora")


class EleccionIlustracion(_TodoObligatorio):
    """El director de arte elige una de las ilustraciones dibujadas viendo la hoja de contactos."""
    elegida: int = Field(description="El número de la elegida, o 0 si ninguna está a la altura")
    por_que: str = Field(description="Una frase")


class EleccionImagen(BaseModel):
    """Segunda llamada: el modelo ve las candidatas (ya con licencia libre) y elige una o ninguna."""
    elegida: int | None = Field(description="Número de la candidata elegida, o null si ninguna sirve")
    personas_reconocibles: bool = Field(description="La elegida muestra caras reconocibles")
    enfoque_x: int = Field(description="0–100: dónde está lo importante en horizontal")
    enfoque_y: int = Field(description="0–100: dónde está lo importante en vertical")
    por_que: str


class IlustracionLLM(BaseModel):
    """Ilustración vectorial de portada (prompts/ilustrador.md)."""
    concepto: str = Field(description="La metáfora elegida y por qué funciona, en una frase")
    svg: str = Field(description="El SVG completo, de <svg> a </svg>")


class Arte(BaseModel):
    """Lo que decidió la etapa de arte para una pieza (trazabilidad; la imagen vive en data/cache)."""
    tono: str
    recurso: str
    consultas: list[str] = Field(default_factory=list)
    cifra: str | None = None
    cifra_rotulo: str | None = None
    imagen: str | None = None            # clave de la imagen fijada («europeana:/…»)
    # Composición de la portada: «circulo» (imagen en círculo), «collage» (grabado a sangre sobre
    # campo de color) o «ilustracion» (ilustración vectorial del ilustrador)
    portada: Literal["sangre", "banda", "caja", "neon", "circulo", "collage", "ilustracion", "panorama"] = "sangre"
    antetitulo: str | None = None
    remate: str | None = None            # final del titular que va en cursiva (marca Alighieria)
    acento: Literal["pluma", "marcador"] | None = None   # color de la pieza; sin color en las graves
    concepto: str | None = None          # metáfora de la ilustración
    retrato: str | None = None           # crédito del retrato del autor, si lo hay
    sin_foto: SinFoto | None = None    # recurso de la diapositiva de actualidad sin foto ni cifra
    infografia: Infografia | None = None  # infografía de la diapositiva de la idea
    esquema: str | None = None           # crédito de la ilustración técnica de Magnific (infografía «esquema»)
    escena: str | None = None            # escena (en inglés) de la ilustración editorial (recurso «ilustracion», portada «panorama»)
    escena_idea: str | None = None       # su metáfora, en español, para enseñarla en la web
    pregunta: str | None = None          # la del buscador de la portada (B2)
    # Registro de la imagen de portada, para barajar en el día (31/10): la foto real del autor, su retrato
    # generado con IA, la ilustración editorial o la imagen de archivo
    registro: Literal["foto_autor", "retrato_ia", "ilustracion", "archivo"] | None = None
    credito: str | None = None
    por_que: str = ""
    avisos: list[str] = Field(default_factory=list)


class CitaVerificada(BaseModel):
    """Cita literal encontrada letra por letra: del libro, en su texto (búsqueda de Google Books), o de la crítica,
    en el texto de crítica recibido (1/11, a petición del usuario: «admite citas a la crítica»)."""
    texto: str
    libro: str                           # título del libro verificado al que pertenece (o del que habla la crítica)
    autor: str
    volumen_google: str = ""             # id del volumen de Google Books en cuyo texto aparece (citas del libro)
    fragmento: str                       # el fragmento del texto que la contiene
    tipo: Literal["libro", "critica"] = "libro"
    fuente: str | None = None            # citas de la crítica: URL del texto donde aparece


class Pieza(BaseModel):
    id: str
    fecha: str
    estado: EstadoPieza
    reserva: bool = False                # True si sale de una historia de reserva
    radar: bool = False                  # True si es un tema del radar del libro (lista aparte, a un clic)
    historia_id: str
    eleccion: HistoriaElegida
    n_medios: int
    libros: list[LibroVerificado] = Field(default_factory=list)
    libros_descartados: list[LibroDescartado] = Field(default_factory=list)
    guion: GuionLLM | None = None
    fuentes: list[FuenteNoticia] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    # «Revisar edición»: el guionista dio datos de edición distintos de los verificados. La ficha
    # usa los verificados, pero el texto de las diapositivas puede arrastrar los del modelo.
    revisar_edicion: bool = False
    discrepancias_edicion: list[DiscrepanciaEdicion] = Field(default_factory=list)
    # Afirmaciones que siempre necesitan ojos humanos antes de publicar («todavía sin traducir»).
    revision_humana: list[str] = Field(default_factory=list)
    # Datos de la noticia en el guion cotejados con los textos fuente (etapa de comprobación).
    hechos: list[HechoComprobado] = Field(default_factory=list)
    # Citas literales del guion, verificadas en el texto del libro
    citas: list[CitaVerificada] = Field(default_factory=list)
    # Imagen, cifra destacada y tono (etapa de arte)
    arte: Arte | None = None
    error: str | None = None


class HistoriaResumida(BaseModel):
    id: str
    titular_es: str | None
    resumen_es: str | None
    seccion: str | None
    n_medios: int
    medios: list[str]
    excluida: str | None = None          # motivo si no pasó al jefe de cultura
    carril: Carril = "actualidad"


class InformeDiario(BaseModel):
    fecha: str
    generado_en: datetime
    stats: dict[str, int | float]
    top_historias: list[HistoriaResumida]
    seleccion: SeleccionJefe | None = None
    piezas: list[Pieza] = Field(default_factory=list)
    trazas: list[Traza] = Field(default_factory=list)
    coste_total_usd: float = 0.0
    avisos: list[str] = Field(default_factory=list)
