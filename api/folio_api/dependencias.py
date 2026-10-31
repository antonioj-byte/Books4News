"""Lo que comparten las rutas: configuración, almacén, ejecutor y plantillas (en app.state)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from folio.almacen import Almacen
from folio.config import Config
from folio.modelos import InformeDiario, Pieza
from folio.render import Plantillas
from folio_api.ejecutor import Ejecutor
from folio_api.programador import Programador


@dataclass
class Contexto:
    cfg: Config
    almacen: Almacen
    ejecutor: Ejecutor
    plantillas: Plantillas
    programador: Programador | None = field(default=None)
    llm: object | None = field(default=None)       # el del chat de edición; en los tests, uno falso

    def ejecucion(self, eid: int) -> tuple[str, InformeDiario]:
        e = self.almacen.ejecucion(eid)
        if not e:
            raise HTTPException(404, "Ejecución no encontrada")
        return e

    def pieza(self, eid: int, pid: str) -> tuple[Pieza, int]:
        r = self.almacen.pieza(eid, pid)
        if not r:
            raise HTTPException(404, "Pieza no encontrada")
        return r


def contexto(request: Request) -> Contexto:
    return request.app.state.folio
