"""La agencia (3/11): el Archivo de todas las piezas, el Equipo (los roles) y la Marca (la memoria de marca de Folio)."""

import re
from datetime import date

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from folio import formatos
from folio import archivo, equipo
from folio.publicacion import programar
from folio_api.dependencias import Contexto, contexto

router = APIRouter()

NOMBRES_FORMATO = {f.id: f.nombre for f in formatos.FORMATOS.values()}   # del registro de formatos (4/11)


# ---------------------------------------------------------------- Archivo

class PiezaArchivo(BaseModel):
    ejecucion_id: int
    pieza_id: str
    fecha: str
    titular: str
    formato: str
    estado: str
    categoria: str               # nevera | aprobada | programada | publicada | pendiente | descartada
    version: int
    tocada: str                  # cuándo se guardó su versión actual
    libro: str | None = None
    autor: str | None = None
    nota: float | None = None    # media de su evaluación, si la tiene
    vigencia: str
    vigencia_texto: str


@router.get("/api/archivo", response_model=list[PiezaArchivo])
def ver_archivo(ctx: Contexto = Depends(contexto)):
    """Todas las piezas, cada una en la última ejecución que la tiene, de la más reciente a la más antigua."""
    hoy = date.today()
    out = []
    for fecha, eid, p, v, tocada in ctx.almacen.archivo():
        if formatos.de(p.eleccion.formato).propio and not p.guion:
            continue
        ev = ctx.almacen.evaluacion(eid, p.id)
        notas = [x for x in ((ev[0].seleccion, ev[0].libro, ev[0].idea, ev[0].voz) if ev else ()) if x]
        libro = p.libros[0] if p.libros else None
        clave, texto = archivo.vigencia(p, fecha, hoy)
        out.append(PiezaArchivo(
            ejecucion_id=eid, pieza_id=p.id, fecha=fecha, version=v, tocada=tocada[:16],
            titular=p.guion.diapositivas[0].texto if p.guion else p.eleccion.titular,
            formato=p.eleccion.formato, estado=p.estado,
            categoria=archivo.categoria(p, p.estado == "aprobada" and programar.estado(ctx.cfg, fecha, p.id) is not None),
            libro=(libro.edicion_es_detalle.titulo if libro and libro.edicion_es_detalle and libro.edicion_es_detalle.titulo
                   else libro.titulo) if libro else None,
            autor=libro.autores[0] if libro and libro.autores else None,
            nota=round(sum(notas) / len(notas), 1) if notas else None, vigencia=clave, vigencia_texto=texto))
    return out


# ---------------------------------------------------------------- Equipo

class Departamento(BaseModel):
    nombre: str
    roles: list[equipo.ResumenRol]


@router.get("/api/equipo", response_model=list[Departamento])
def ver_equipo(ctx: Contexto = Depends(contexto)):
    eq = equipo.equipo(ctx.cfg)
    return [Departamento(nombre=d, roles=[equipo.resumen(ctx.cfg, ctx.almacen, r) for r in eq.roles if r.departamento == d])
            for d in eq.departamentos]


@router.get("/api/equipo/{rid}", response_model=equipo.DetalleRol)
def ver_rol(rid: str, ctx: Contexto = Depends(contexto)):
    r = equipo.rol(ctx.cfg, rid)
    if r is None:
        raise HTTPException(404, "No existe ese rol")
    return equipo.detalle(ctx.cfg, ctx.almacen, r)


# ---------------------------------------------------------------- Marca

class Apartado(BaseModel):
    titulo: str
    texto: str
    fuente: str


class Color(BaseModel):
    nombre: str
    valor: str


class FormatoMarca(BaseModel):
    id: str
    nombre: str
    descripcion: str


class ReglaMarca(BaseModel):
    patron: str
    propuesta: str
    destino: str


class Marca(BaseModel):
    nombre: str
    que_es: str
    linea_editorial: Apartado
    voz: Apartado
    diseno: Apartado
    colores: list[Color]
    letras: list[str]
    formatos: list[FormatoMarca]
    reglas: list[str]
    aprendidas: list[ReglaMarca]          # reglas de la Memoria con capa «marca», en vigor
    medios: int
    medios_libro: int
    editoriales: int


def _primera_frase(texto: str) -> str:
    """La primera frase que dice algo (la sección empieza por el nombre del formato: «Lectura lateral.»)."""
    t = " ".join(texto.split())
    for frase in re.split(r"(?<=[.:])\s+", t):
        if len(frase.split()) >= 6:
            frase = re.sub(r"\s*\(\d{1,2}/\d{1,2}[^)]*\)", "", frase).rstrip(":").rstrip(".")[:240]
            return frase[:1].upper() + frase[1:] + "."
    return t[:240]


@router.get("/api/marca", response_model=Marca)
def ver_marca(ctx: Contexto = Depends(contexto)):
    raiz = ctx.cfg.raiz
    m = yaml.safe_load((raiz / "config" / "marca.yaml").read_text(encoding="utf-8"))
    tokens = yaml.safe_load((raiz / "diseno" / "tokens.yaml").read_text(encoding="utf-8"))
    principales = ("papel", "tinta", "pluma", "marcador")
    colores = [Color(nombre=k, valor=v) for k, v in tokens.get("colores", {}).items() if k in principales]
    letras = [str(v).split(",")[0].strip("' ") for k, v in tokens.get("fuentes", {}).items() if k in ("titular", "remate", "texto")]
    secciones = re.split(r"^## ", (ctx.cfg.dir_prompts / "formatos.md").read_text(encoding="utf-8"), flags=re.M)[1:]
    formatos = []
    for s in secciones:
        fid, _, cuerpo = s.partition("\n")
        fid = fid.strip()
        if fid in NOMBRES_FORMATO:
            formatos.append(FormatoMarca(id=fid, nombre=NOMBRES_FORMATO[fid], descripcion=_primera_frase(cuerpo)))
    if "cinco" not in {f.id for f in formatos}:
        formatos.append(FormatoMarca(id="cinco", nombre=NOMBRES_FORMATO["cinco"],
                                     descripcion="Las cinco noticias del mundo del libro del día, cada una con su ilustración."))
    formatos.append(FormatoMarca(id="newsletter", nombre=NOMBRES_FORMATO["newsletter"],
                                 descripcion="La versión corta del ensayo de los jueves: titular entre comillas, percha, cuatro frases ilustradas y el enlace a la newsletter."))

    def contar(nombre: str, clave: str) -> int:
        f = raiz / "config" / nombre
        datos = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None
        lista = datos.get(clave, []) if isinstance(datos, dict) else (datos or [])
        return len([x for x in lista if not (isinstance(x, dict) and x.get("excluir"))])

    aprendidas = [ReglaMarca(patron=p.patron, propuesta=p.propuesta, destino=p.destino) for p in ctx.almacen.patrones()
                  if p.capa == "marca" and p.estado in ("aceptada", "aplicada")]
    return Marca(nombre=m["nombre"], que_es=m["que_es"], linea_editorial=Apartado(**m["linea_editorial"]),
                 voz=Apartado(**m["voz"]), diseno=Apartado(**m["diseno"]), colores=colores, letras=letras,
                 formatos=formatos, reglas=m.get("reglas", []), aprendidas=aprendidas,
                 medios=contar("fuentes.yaml", "fuentes"), medios_libro=contar("fuentes_editoriales.yaml", "fuentes"),
                 editoriales=contar("editoriales_independientes.yaml", "editoriales"))
