"""Esquemas de la API. Reutilizan los del pipeline (folio.modelos); de ellos salen los tipos
TypeScript de la web (npm run tipos)."""

from __future__ import annotations

from typing import Literal


from folio.almacen import Evaluacion, Version
from folio.modelos import BaseModel, EstadoPieza, HechoComprobado, Pieza


class Ejecucion(BaseModel):
    id: int
    generado_en: str
    coste_usd: float
    piezas: int


class Dia(BaseModel):
    fecha: str
    ejecuciones: list[Ejecucion]


class Marcas(BaseModel):
    """Avisos que tienen que verse en la portada del día."""
    revisar_edicion: bool = False
    hechos_no_verificados: int = 0
    revision_humana: int = 0
    error: str | None = None


class Lomo(BaseModel):
    """Un libro de la pieza tal como se recomienda: para la estantería de la portada del día."""
    titulo: str
    autor: str
    cubierta: str | None = None           # URL de la cubierta, si la etapa de arte o la mesa la encontró


class PiezaResumen(BaseModel):
    ejecucion_id: int
    pieza_id: str
    titular: str
    portada: str | None
    estado: EstadoPieza
    n_medios: int
    reserva: bool
    version: int
    marcas: Marcas
    evaluada: bool
    libros: list[Lomo]
    formato: str = "lateral"              # lateral, dialogo, edicion, curiosidad, recomendado o radar
    gancho: str = ""                      # el gancho del libro que propuso el jefe (lo que se ve en la mesa)
    radar: bool = False                   # tema del radar del libro: lista aparte, a un clic
    por_que: str = ""                     # por qué merece una pieza (lo que se ve en la lista del radar)


class DiaDetalle(BaseModel):
    fecha: str
    ejecucion: Ejecucion
    ejecuciones: list[Ejecucion]
    aviso_jefe: str | None
    avisos: list[str]
    coste_usd: float
    piezas: list[PiezaResumen]


class HechoLigado(BaseModel):
    """Hecho no verificado junto a la frase del guion que lo contiene."""
    hecho: HechoComprobado
    diapositiva: int | None      # None si está en el pie
    frase: str | None


class ProgramadaBuffer(BaseModel):
    hora: str | None                      # ISO, hora de Madrid; None si va a la cola
    borrador: bool
    canal: str = ""
    en: str | None = None                 # cuándo se programó
    version: int | None = None


class EstadoBuffer(BaseModel):
    """Lo que la ficha de la pieza enseña junto al botón «Programar en Buffer»."""
    disponible: bool                      # hay clave de Buffer, URL pública y clave de enlaces
    motivo: str | None = None             # por qué no, si no está disponible
    programada: ProgramadaBuffer | None = None
    mensaje: str | None = None            # el resultado de la última acción


class ProgramarBuffer(BaseModel):
    hora: str | None = None               # «HH:MM» o «AAAA-MM-DD HH:MM» (hora de Madrid); sin ella, a la cola de Buffer
    borrador: bool = False                # lo deja en borradores: no se publica
    reemplazar: bool = False              # ya estaba programada y esa publicación se ha borrado en Buffer


class VideoDiapositiva(BaseModel):
    n: int                                # número de la diapositiva
    url: str


class PiezaDetalle(BaseModel):
    ejecucion_id: int
    fecha: str
    version: int
    pieza: Pieza
    aviso_jefe: str | None
    hechos_no_verificados: list[HechoLigado]
    evaluacion: Evaluacion | None
    evaluacion_version: int | None
    versiones: list[Version]
    # URL del vídeo de portada (folio render --video), si existe y la pieza no se ha editado desde
    # entonces: el vídeo se hizo con la versión del informe del día
    video_portada: str | None = None
    # Todas las diapositivas en vídeo (portada, noticia, idea), con la misma condición
    videos: list[VideoDiapositiva] = []
    # Las del guion y, al final, el colofón (no se edita: lo pinta el código con datos comprobados)
    total_diapositivas: int = 0
    lomos: list[Lomo] = []                # los libros con su cubierta (la propuesta pendiente los enseña)


class EdicionDiapositiva(BaseModel):
    texto: str
    subtitulo: str | None = None          # solo la portada


class ResultadoEdicion(BaseModel):
    version: int
    avisos: list[str]                     # reglas del guion que la edición no cumple (se guarda igual)


class MensajeNuevo(BaseModel):
    mensaje: str


class RespuestaChat(BaseModel):
    respuesta: str
    version: int | None                   # la versión nueva, si el chat cambió la pieza
    avisos: list[str]


class CambioEstado(BaseModel):
    estado: EstadoPieza


class ResumenDia(BaseModel):
    fecha: str
    n: int
    seleccion: float | None
    libro: float | None
    idea: float | None
    voz: float | None
    publicaria: float | None


# --- Panel de gasto -----------------------------------------------------------------

class DiaGasto(BaseModel):
    fecha: str
    anthropic_usd: float
    magnific_eur: float
    magnific_imagenes: int


class ConceptoGasto(BaseModel):
    servicio: str
    concepto: str
    moneda: str
    coste: float
    n: int                                # llamadas o imágenes


class ApunteGasto(BaseModel):
    ts: str
    fecha: str
    servicio: str
    concepto: str
    modelo: str | None = None
    unidades: float
    coste: float
    moneda: str
    detalle: str | None = None


class PanelGasto(BaseModel):
    hoy: str
    mes: str                              # primer día del mes en curso
    registro_desde: str                   # desde cuándo se apunta todo (antes, solo las ejecuciones del día)
    anthropic_hoy_usd: float
    anthropic_mes_usd: float
    magnific_hoy_eur: float
    magnific_mes_eur: float
    magnific_mes_creditos: float
    magnific_mes_imagenes: int
    dias: list[DiaGasto]
    conceptos: list[ConceptoGasto]        # del mes en curso
    ultimos: list[ApunteGasto]            # los 40 apuntes más recientes


# --- Memoria del feedback -------------------------------------------------------------

class ResultadoMemoria(BaseModel):
    piezas: int                           # piezas con feedback leídas
    patrones: int                         # patrones guardados o reforzados
    aviso: str


class EstadoMemoria(BaseModel):
    ultimo: str | None                    # fecha y hora del último análisis (ISO), o None
    ultimo_origen: str | None             # manual | semanal
    proximo: str                          # día (AAAA-MM-DD) de la diaria en que toca el análisis semanal
    de_conversacion: int                  # reglas cargadas de las conversaciones


class DecisionPatron(BaseModel):
    estado: Literal["propuesta", "aceptada", "rechazada", "aplicada"]
    nota: str = ""
