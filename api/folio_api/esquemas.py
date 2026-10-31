"""Esquemas de la API. Reutilizan los del pipeline (folio.modelos); de ellos salen los tipos
TypeScript de la web (npm run tipos)."""

from __future__ import annotations


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
