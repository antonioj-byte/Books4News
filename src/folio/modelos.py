"""Esquemas de datos del pipeline.

Hay dos familias:
- Salidas de los modelos (ResumenHistoria, SeleccionJefe, GuionLLM): reflejan lo que piden
  los prompts de prompts/ y se usan como esquema de salida estructurada.
- Datos del pipeline (Articulo, Historia, LibroVerificado, Pieza, InformeDiario): los produce
  el código y forman el informe diario; la web de la Fase 3 los reutilizará.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel as _BaseModel, ConfigDict, Field


class BaseModel(_BaseModel):
    """Base de los esquemas: en el esquema de salida (OpenAPI de la web) los campos con valor por
    defecto figuran como obligatorios, porque siempre vienen."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


Acceso = Literal["abierto", "parcial", "muro"]
Seccion = Literal[
    "politica", "internacional", "economia", "ciencia", "tecnologia", "sociedad",
    "cultura", "deportes", "sucesos", "salud", "medio_ambiente", "otros",
]
EstadoPieza = Literal["propuesta", "en_edicion", "aprobada", "descartada", "publicada", "fallida"]
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


class ResumenHistoria(BaseModel):
    """Salida del modelo barato para cada historia."""
    titular_es: str = Field(description="Titular neutro en español, una línea")
    resumen_es: str = Field(description="Qué ha pasado, en una o dos frases, en español")
    seccion: Seccion


# --- Selección (prompts/jefe_cultura.md) -------------------------------------

class LibroCandidato(BaseModel):
    titulo: str = Field(description="Título en español si hay edición española; si no, el original")
    autor: str
    titulo_original: str | None = Field(default=None, description="Título en la lengua original")
    idioma_original: str | None = Field(default=None, description="Lengua original de la obra, en español (inglés, alemán…)")


class HistoriaElegida(BaseModel):
    historia_id: str = Field(description="Identificador de la historia tal como aparece en la lista")
    titular: str = Field(description="Titular en una línea")
    de_que_se_habla: str = Field(description="De qué se está hablando, en dos frases")
    cuestion_de_fondo: str = Field(description="La cuestión de fondo, en una frase")
    libros_candidatos: list[LibroCandidato] = Field(description="2–3 libros candidatos")
    por_que: str = Field(description="Por qué esta historia y no otra, en dos líneas")


class SeleccionJefe(BaseModel):
    elegidas: list[HistoriaElegida] = Field(description="Hasta 3 historias elegidas, por orden de preferencia")
    reserva: list[HistoriaElegida] = Field(description="Hasta 2 historias de reserva")
    aviso: str | None = Field(
        default=None,
        description="Si eliges menos de 3 porque no hay buena lectura lateral, explícalo aquí; si no, null",
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
    fuentes_verificacion: list[Literal["openlibrary", "googlebooks"]]
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


class Traza(BaseModel):
    paso: str
    modelo: str
    tokens_entrada: int = 0              # entrada no cacheada
    tokens_salida: int = 0
    tokens_cache_escritura: int = 0
    tokens_cache_lectura: int = 0
    coste_usd: float = 0.0
    nota: str | None = None


class DiscrepanciaEdicion(BaseModel):
    """Dato de edición en que el guionista y la fuente bibliográfica no coinciden."""
    libro: str
    campo: Literal["editorial española", "traductor", "editorial original", "año original"]
    modelo: str
    api: str


# --- Director de arte (prompts/director_arte.md) --------------------------------

class PropuestaArte(BaseModel):
    """Primera llamada: qué buscar y qué destacar. La imagen la busca el código."""
    tono: Literal["grave", "sereno", "reflexivo", "ironico", "luminoso"]
    suceso_con_victimas: bool = Field(description="La noticia trata de muertos, heridos o víctimas")
    recurso: Literal["foto", "grabado"] = Field(description="Foto de archivo o ilustración antigua (grabado, dibujo)")
    consultas: list[str] = Field(description="3 o 4 búsquedas de 1 a 3 palabras, en inglés, sueco o alemán")
    evitar: list[str] = Field(description="Lo que la imagen no debe mostrar")
    cifra: str | None = Field(default=None, description="Una cifra copiada literalmente de la diapositiva de actualidad, o null")
    cifra_rotulo: str | None = Field(default=None, description="De 2 a 6 palabras de esa misma diapositiva que explican la cifra")
    por_que: str


class EleccionImagen(BaseModel):
    """Segunda llamada: el modelo ve las candidatas (ya con licencia libre) y elige una o ninguna."""
    elegida: int | None = Field(description="Número de la candidata elegida, o null si ninguna sirve")
    personas_reconocibles: bool = Field(description="La elegida muestra caras reconocibles")
    enfoque_x: int = Field(description="0–100: dónde está lo importante en horizontal")
    enfoque_y: int = Field(description="0–100: dónde está lo importante en vertical")
    por_que: str


class Arte(BaseModel):
    """Lo que decidió la etapa de arte para una pieza (trazabilidad; la imagen vive en data/cache)."""
    tono: str
    recurso: str
    consultas: list[str] = Field(default_factory=list)
    cifra: str | None = None
    cifra_rotulo: str | None = None
    imagen: str | None = None            # clave de la imagen fijada («europeana:/…»)
    credito: str | None = None
    por_que: str = ""
    avisos: list[str] = Field(default_factory=list)


class Pieza(BaseModel):
    id: str
    fecha: str
    estado: EstadoPieza
    reserva: bool = False                # True si sale de una historia de reserva
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
