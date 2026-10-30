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
