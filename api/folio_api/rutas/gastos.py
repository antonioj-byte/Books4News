"""Gasto en servicios de pago (panel «Gasto» de la web): Anthropic en dólares y Magnific en euros y créditos,
por día y por concepto, del registro de la base de datos (folio.gastos)."""

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from folio import gastos as registro
from folio_api.dependencias import Contexto, contexto
from folio_api.esquemas import ApunteGasto, ConceptoGasto, DiaGasto, PanelGasto

router = APIRouter()


@router.get("/api/gastos", response_model=PanelGasto)
def panel(dias: int = Query(30, ge=7, le=366), ctx: Contexto = Depends(contexto)):
    hoy = date.fromisoformat(registro.hoy())
    desde = min(hoy - timedelta(days=dias - 1), hoy.replace(day=1))
    apuntes = ctx.almacen.gastos(desde.isoformat())
    mes = hoy.replace(day=1).isoformat()

    def suma(servicio: str, desde_fecha: str, campo: str = "coste") -> float:
        return round(sum(getattr(a, campo) for a in apuntes if a.servicio == servicio and a.fecha >= desde_fecha), 4)

    por_dia: dict[str, dict] = {}
    for i in range(dias):
        f = (hoy - timedelta(days=dias - 1 - i)).isoformat()
        por_dia[f] = {"fecha": f, "anthropic_usd": 0.0, "magnific_eur": 0.0, "magnific_imagenes": 0}
    conceptos: dict[tuple, dict] = defaultdict(lambda: {"coste": 0.0, "n": 0})
    for a in apuntes:
        if a.fecha in por_dia:
            if a.servicio == "anthropic":
                por_dia[a.fecha]["anthropic_usd"] += a.coste
            elif a.servicio == "magnific":
                por_dia[a.fecha]["magnific_eur"] += a.coste
                por_dia[a.fecha]["magnific_imagenes"] += 1
        if a.fecha >= mes:
            c = conceptos[(a.servicio, a.concepto, a.moneda)]
            c["coste"] += a.coste
            c["n"] += 1
    return PanelGasto(
        hoy=hoy.isoformat(), mes=mes, registro_desde=ctx.almacen.inicio_gastos()[:10],
        anthropic_hoy_usd=suma("anthropic", hoy.isoformat()), anthropic_mes_usd=suma("anthropic", mes),
        magnific_hoy_eur=suma("magnific", hoy.isoformat()), magnific_mes_eur=suma("magnific", mes),
        magnific_mes_creditos=suma("magnific", mes, "unidades"),
        magnific_mes_imagenes=sum(1 for a in apuntes if a.servicio == "magnific" and a.fecha >= mes),
        dias=[DiaGasto(**{k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}) for d in por_dia.values()],
        conceptos=sorted((ConceptoGasto(servicio=k[0], concepto=k[1], moneda=k[2], coste=round(v["coste"], 4), n=v["n"])
                          for k, v in conceptos.items()), key=lambda c: (c.servicio, -c.coste)),
        ultimos=_agrupados(list(reversed(apuntes)))[:25],
    )


def _agrupados(apuntes) -> list[ApunteGasto]:
    """Los apuntes del más reciente al más antiguo, con las llamadas seguidas de la misma etapa juntas
    («Resúmenes de la ingesta · 38 llamadas»): una ejecución hace decenas de resúmenes."""
    out: list[ApunteGasto] = []
    n = 0
    for a in apuntes:
        ultimo = out[-1] if out else None
        if ultimo and (ultimo.servicio, ultimo.concepto, ultimo.fecha, ultimo.moneda) == (a.servicio, a.concepto, a.fecha, a.moneda):
            n += 1
            ultimo.coste = round(ultimo.coste + a.coste, 6)
            ultimo.unidades += a.unidades
            ultimo.detalle = f"{n} {'imágenes' if a.servicio == 'magnific' else 'llamadas'}"
            continue
        out.append(ApunteGasto(**a.model_dump()))
        n = 1
    return out
