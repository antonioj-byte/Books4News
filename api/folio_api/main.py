"""App FastAPI. Solo local: sin autenticación ni despliegue (Fase 3, versión mínima)."""

from __future__ import annotations

import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from folio import config as config_folio
from folio.almacen import Almacen, Evaluacion, escribir_evaluacion_md
from folio.config import Config
from folio.modelos import InformeDiario, Pieza
from folio.render import Plantillas, cargar_tokens, css_tokens, dir_diseno
from folio.verificacion_texto import normalizar
from folio_api.ejecutor import EstadoEjecucion, Ejecutor
from folio_api.esquemas import (
    CambioEstado, Dia, DiaDetalle, Ejecucion, HechoLigado, Marcas, PiezaDetalle, PiezaResumen, ResumenDia,
)

_FRASES = re.compile(r"(?<=[.!?…])\s+")


def _marcas(p: Pieza) -> Marcas:
    return Marcas(revisar_edicion=p.revisar_edicion, hechos_no_verificados=sum(not h.verificado for h in p.hechos),
                  revision_humana=len(p.revision_humana), error=p.error)


def hechos_ligados(p: Pieza) -> list[HechoLigado]:
    """Cada hecho no verificado con la frase del guion que lo contiene (o la que más se le parece)."""
    out = []
    for h in p.hechos:
        if h.verificado:
            continue
        m = re.search(r"\d+", h.donde)
        n = int(m.group()) if m and "diapositiva" in h.donde else None
        texto = ""
        if p.guion:
            if n and 1 <= n <= len(p.guion.diapositivas):
                texto = p.guion.diapositivas[n - 1].texto
            elif n is None:
                texto = p.guion.pie_instagram
        frases = [f for f in _FRASES.split(texto) if f.strip()]
        objetivo = normalizar(h.afirmacion)
        frase = next((f for f in frases if objetivo and objetivo in normalizar(f)), None)
        if frase is None and frases:
            palabras = set(objetivo.split())
            frase = max(frases, key=lambda f: len(palabras & set(normalizar(f).split())))
        out.append(HechoLigado(hecho=h, diapositiva=n, frase=frase))
    return out


def crear_app(cfg: Config | None = None, almacen: Almacen | None = None, importar: bool = True,
              ejecutor: Ejecutor | None = None) -> FastAPI:
    cfg = cfg or config_folio.cargar()
    almacen = almacen or Almacen(cfg.ruta_db)
    ejecutor = ejecutor or Ejecutor(cfg.dir_datos)
    if importar:
        almacen.importar_informes(cfg.dir_informes)
    plantillas = Plantillas(cfg)
    app = FastAPI(title="Folio · web local", version="0.1.0")
    app.mount("/diseno", StaticFiles(directory=dir_diseno(cfg)), name="diseno")

    def _ejecucion(eid: int) -> tuple[str, InformeDiario]:
        e = almacen.ejecucion(eid)
        if not e:
            raise HTTPException(404, "Ejecución no encontrada")
        return e

    def _pieza(eid: int, pid: str) -> tuple[Pieza, int]:
        r = almacen.pieza(eid, pid)
        if not r:
            raise HTTPException(404, "Pieza no encontrada")
        return r

    def _ejecuciones(fecha: str) -> list[Ejecucion]:
        dia = next((d for d in almacen.dias() if d["fecha"] == fecha), None)
        return [Ejecucion(**e) for e in dia["ejecuciones"]] if dia else []

    @app.get("/api/dias", response_model=list[Dia])
    def dias():
        return almacen.dias()

    @app.get("/api/dias/{fecha}", response_model=DiaDetalle)
    def dia(fecha: str, ejecucion: int | None = None):
        ejecuciones = _ejecuciones(fecha)
        eid = ejecucion or almacen.ultima_ejecucion(fecha)
        if not eid or eid not in {e.id for e in ejecuciones}:
            raise HTTPException(404, "No hay ejecuciones para esa fecha")
        _, inf = _ejecucion(eid)
        piezas = [PiezaResumen(
            ejecucion_id=eid, pieza_id=p.id, titular=p.eleccion.titular,
            portada=p.guion.diapositivas[0].texto if p.guion else None, estado=p.estado, n_medios=p.n_medios,
            reserva=p.reserva, version=v, marcas=_marcas(p), evaluada=almacen.evaluacion(eid, p.id) is not None,
        ) for p, v in almacen.piezas(eid)]
        return DiaDetalle(fecha=fecha, ejecucion=next(e for e in ejecuciones if e.id == eid), ejecuciones=ejecuciones,
                          aviso_jefe=inf.seleccion.aviso if inf.seleccion else None, avisos=inf.avisos,
                          coste_usd=inf.coste_total_usd, piezas=piezas)

    @app.get("/api/ejecuciones/{eid}/piezas/{pid}", response_model=PiezaDetalle)
    def pieza(eid: int, pid: str):
        fecha, inf = _ejecucion(eid)
        p, v = _pieza(eid, pid)
        ev = almacen.evaluacion(eid, pid)
        return PiezaDetalle(ejecucion_id=eid, fecha=fecha, version=v, pieza=p,
                            aviso_jefe=inf.seleccion.aviso if inf.seleccion else None,
                            hechos_no_verificados=hechos_ligados(p),
                            evaluacion=ev[0] if ev else None, evaluacion_version=ev[1] if ev else None,
                            versiones=almacen.versiones(eid, pid))

    @app.patch("/api/ejecuciones/{eid}/piezas/{pid}/estado", response_model=CambioEstado)
    def estado(eid: int, pid: str, cambio: CambioEstado):
        _pieza(eid, pid)
        almacen.cambiar_estado(eid, pid, cambio.estado)
        return cambio

    @app.get("/api/ejecuciones/{eid}/piezas/{pid}/diapositivas/{n}.html", response_class=HTMLResponse)
    def diapositiva(eid: int, pid: str, n: int, version: int | None = None):
        p, _ = _pieza(eid, pid)
        if version:
            p = almacen.version(eid, pid, version) or p
        if not p.guion or not 1 <= n <= len(p.guion.diapositivas):
            raise HTTPException(404, "Diapositiva no encontrada")
        return plantillas.html_diapositiva(p, n, base_url="/diseno/")

    @app.get("/api/diseno/tokens.css", response_class=PlainTextResponse)
    def tokens_css():
        """Variables CSS del design system, para que la web use los mismos colores y fuentes."""
        return PlainTextResponse(css_tokens(cargar_tokens(cfg)), media_type="text/css")

    @app.get("/api/ejecuciones/{eid}/piezas/{pid}/evaluacion", response_model=Evaluacion | None)
    def leer_evaluacion(eid: int, pid: str):
        ev = almacen.evaluacion(eid, pid)
        return ev[0] if ev else None

    @app.put("/api/ejecuciones/{eid}/piezas/{pid}/evaluacion", response_model=Evaluacion)
    def guardar_evaluacion(eid: int, pid: str, ev: Evaluacion):
        fecha, inf = _ejecucion(eid)
        _, v = _pieza(eid, pid)
        almacen.guardar_evaluacion(eid, pid, ev, v)
        # Copia en informe.md, si ese informe es el de esta ejecución (el formato de la Fase 1)
        ruta_json = cfg.dir_informes / fecha / "informe.json"
        if ruta_json.exists() and InformeDiario.model_validate_json(ruta_json.read_text(encoding="utf-8")).generado_en == inf.generado_en:
            escribir_evaluacion_md(cfg.dir_informes / fecha / "informe.md", pid, ev)
        return ev

    @app.get("/api/evaluaciones/resumen", response_model=list[ResumenDia])
    def resumen():
        return almacen.resumen_evaluaciones()

    @app.post("/api/ejecuciones/lanzar", response_model=EstadoEjecucion, status_code=202)
    def lanzar():
        """Lanza `folio run` (pipeline completo del día, ~1 $). Al terminar, la ejecución aparece en
        la portada del día: el pipeline la guarda en la base de datos."""
        if not ejecutor.lanzar():
            raise HTTPException(409, "Ya hay una ejecución en marcha")
        return ejecutor.estado()

    @app.get("/api/ejecuciones/en-marcha", response_model=EstadoEjecucion)
    def en_marcha():
        return ejecutor.estado()

    return app


def app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn (`folio web`)."""
    return crear_app()
