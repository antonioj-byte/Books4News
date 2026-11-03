"""El equipo de la agencia (3/11, a petición del usuario: «lo que estamos construyendo es una agencia… una serie de roles
que estamos entrenando recursivamente con el feedback, y cada cuenta tiene una memoria»).

Los roles están en config/equipo.yaml. De aquí salen:
- los créditos de cada pieza: quién trabajó en ella, qué hizo y cuánto costó (de los apuntes de gasto, que llevan el id de
  la pieza, y de lo que la propia pieza guarda: quién la propuso, la nota del puente, los hechos marcados, la imagen);
- el resumen de cada rol para la página «Equipo» y su ficha: modelo, coste de la semana, nota en la evaluación, reglas
  de la Memoria por capa (oficio, marca, celda) y lo que se le ha pedido.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from folio.config import Config
from folio.modelos import Pieza

CAPAS = ("oficio", "marca", "celda")


class Rol(BaseModel):
    id: str
    nombre: str
    departamento: str
    que_hace: str
    etapa: str | None = None
    conceptos: list[str] = Field(default_factory=list)
    destino: str | None = None
    criterios: list[str] = Field(default_factory=list)


class Equipo(BaseModel):
    departamentos: list[str]
    roles: list[Rol]


@lru_cache(maxsize=4)
def _cargar(ruta: str, _mtime: float) -> Equipo:
    e = Equipo(**yaml.safe_load(Path(ruta).read_text(encoding="utf-8")))
    ids = [r.id for r in e.roles]
    if len(ids) != len(set(ids)):
        raise ValueError("config/equipo.yaml: ids de rol repetidos")
    malos = [r.id for r in e.roles if r.departamento not in e.departamentos]
    if malos:
        raise ValueError(f"config/equipo.yaml: departamento desconocido en {malos}")
    return e


def equipo(cfg: Config) -> Equipo:
    ruta = cfg.raiz / "config" / "equipo.yaml"
    return _cargar(str(ruta), ruta.stat().st_mtime)


def rol_de_concepto(cfg: Config, concepto: str) -> Rol | None:
    for r in equipo(cfg).roles:
        if concepto in r.conceptos:
            return r
    return None


def rol(cfg: Config, rid: str) -> Rol | None:
    return next((r for r in equipo(cfg).roles if r.id == rid), None)


# ---------------------------------------------------------------- créditos de una pieza

class Credito(BaseModel):
    rol: str                     # id del rol (o «redaccion»)
    nombre: str
    que: str                     # qué hizo, en pocas palabras
    alerta: bool = False         # levantó la mano: un hecho sin verificar, un puente justo…
    coste_usd: float = 0.0
    coste_eur: float = 0.0
    llamadas: int = 0


_PUENTE = re.compile(r"Puente (\d)/5")
_REGISTROS = {"foto_autor": "foto del autor", "retrato_ia": "retrato 3D", "recorte": "recorte en collage",
              "ilustracion": "ilustración", "archivo": "imagen de archivo"}


def _proponente(p: Pieza) -> list[tuple[str, str, str]]:
    """Quién propuso la pieza: (rol, nombre, qué hizo)."""
    f = p.eleccion.formato
    if p.historia_id.startswith("tema-"):
        return [("redaccion", "Redacción", "propuso el tema" + (" · solo la noticia" if f == "noticia" else "")),
                ("jefe_cultura", "Jefe de cultura", f"lo planteó como {_FORMATOS.get(f, f)}")]
    if f == "cinco":
        return [("jefe_cultura", "Jefe de cultura", "eligió y tituló las cinco")]
    if p.radar or f in ("edicion", "curiosidad", "recomendado", "radar"):
        return [("editor_libro", "Editor del libro", f"propuso {_FORMATOS.get(f, f)}")]
    return [("jefe_cultura", "Jefe de cultura", f"propuso {_FORMATOS.get(f, f)}")]


_FORMATOS = {"lateral": "una lectura lateral", "dialogo": "un diálogo", "edicion": "una del mundo del libro",
             "curiosidad": "una historia editorial", "recomendado": "un libro recomendado", "radar": "un breve",
             "balda": "tres libros", "noticia": "una noticia", "cinco": "cinco del libro"}


_QUE_HIZO = {"comprobador": "comprobó los hechos", "lector_sin_contexto": "lo leyó sin contexto",
             "director_arte": "eligió la imagen", "ilustrador": "escribió la escena", "editor_chat": "editó en el chat",
             "revisor_letras": "revisó las imágenes", "guionista": "lo escribió", "documentalista": "buscó las fuentes"}


def creditos(cfg: Config, almacen, p: Pieza) -> list[Credito]:
    """Quién trabajó en la pieza, en el orden de la cadena. Lo que no deja rastro de gasto en esta pieza (la mesa es de
    todo el día) se cuenta por lo que la pieza guarda."""
    eq = equipo(cfg)
    por_rol: dict[str, Credito] = {}
    orden: list[str] = []

    def apuntar(rid: str, nombre: str, que: str, alerta: bool = False) -> Credito:
        if rid not in por_rol:
            por_rol[rid] = Credito(rol=rid, nombre=nombre, que=que, alerta=alerta)
            orden.append(rid)
        else:
            c = por_rol[rid]
            c.alerta = c.alerta or alerta
        return por_rol[rid]

    for rid, nombre, que in _proponente(p):
        apuntar(rid, nombre, que)
    nota = next((int(m.group(1)) for a in p.avisos for m in [_PUENTE.search(a)] if m), None)
    if nota is not None:
        apuntar("evaluador_puentes", "Evaluador de puentes", f"le dio {nota}/5 al puente", alerta=nota <= 3)
    prensa = sum(1 for f in p.fuentes if getattr(f, "prensa", False))
    if prensa:
        apuntar("documentalista", "Documentalista", f"encontró {prensa} artículo{'s' if prensa > 1 else ''} de prensa")

    gastos = almacen.gastos_de_pieza(p.id) if almacen is not None else []
    llamadas: dict[str, list] = {}
    for g in gastos:
        r = rol_de_concepto(cfg, g.concepto)
        if r:
            llamadas.setdefault(r.id, []).append(g)

    guion = llamadas.get("guionista", [])
    if p.guion or guion:
        intentos = sum(1 for g in guion if g.concepto == "guion")
        apuntar("guionista", "Guionista", f"lo escribió ({intentos} intento{'s' if intentos != 1 else ''})" if intentos else "lo escribió")
    if "lector_sin_contexto" in llamadas:
        apuntar("lector_sin_contexto", "Lector sin contexto", "lo leyó sin contexto")
    if p.hechos:
        malos = sum(1 for h in p.hechos if not h.verificado)
        apuntar("comprobador", "Comprobador de hechos",
                f"{malos} hecho{'s' if malos > 1 else ''} sin verificar" if malos else f"{len(p.hechos)} hechos verificados",
                alerta=bool(malos))
    if p.arte:
        que = _REGISTROS.get(p.arte.registro or "", "sin imagen")
        if p.arte.portada and p.arte.portada not in ("sangre", "panorama"):
            que += f" · {p.arte.portada}"
        apuntar("director_arte", "Director de arte", que)
    imagenes = [g for g in llamadas.get("ilustrador", []) if g.servicio == "magnific"]
    if imagenes or "ilustrador" in llamadas:
        apuntar("ilustrador", "Ilustrador", f"{len(imagenes)} imagen{'es' if len(imagenes) != 1 else ''}" if imagenes else "escribió la escena")
    if "revisor_letras" in llamadas:
        apuntar("revisor_letras", "Revisor de letras", f"revisó {len(llamadas['revisor_letras'])} imagen(es)")
    chat = [g for g in llamadas.get("editor_chat", [])]
    if chat:
        apuntar("editor_chat", "Editor del chat", f"{len(chat)} turno{'s' if len(chat) != 1 else ''} de edición")

    for rid, gs in llamadas.items():
        c = por_rol.get(rid)
        if c is None:
            r = rol(cfg, rid)
            c = apuntar(rid, r.nombre if r else rid, _QUE_HIZO.get(rid, "trabajó en ella"))
        c.llamadas = len(gs)
        c.coste_usd = round(sum(g.coste for g in gs if g.moneda == "USD"), 4)
        c.coste_eur = round(sum(g.coste for g in gs if g.moneda == "EUR"), 4)

    posicion = {r.id: i for i, r in enumerate(eq.roles)}
    proponentes = [x[0] for x in _proponente(p)]
    return sorted((por_rol[r] for r in orden),
                  key=lambda c: (0, proponentes.index(c.rol)) if c.rol in proponentes else (1, posicion.get(c.rol, 99)))


# ---------------------------------------------------------------- el equipo, para la web

class ReglaRol(BaseModel):
    id: int
    capa: str
    estado: str
    patron: str
    propuesta: str
    origen: str
    fecha: str


class Pedido(BaseModel):
    pieza: str
    texto: str
    fecha: str


class ResumenRol(BaseModel):
    id: str
    nombre: str
    departamento: str
    que_hace: str
    modelo: str | None = None
    esfuerzo: str | None = None
    coste_7d_usd: float = 0.0
    coste_7d_eur: float = 0.0
    llamadas_7d: int = 0
    nota: float | None = None            # media de sus criterios en la evaluación de los últimos 14 días
    criterios: list[str] = []
    reglas: dict[str, int] = {}          # por capa, solo las que están en vigor (aceptadas o aplicadas)
    pendientes: int = 0                  # reglas propuestas por la Memoria aún sin decidir
    pedidos_7d: int = 0                  # mensajes del chat dirigidos a él


class DetalleRol(ResumenRol):
    reglas_lista: list[ReglaRol] = []
    pedidos_lista: list[Pedido] = []
    comparte_reglas_con: list[str] = []  # roles con el mismo destino de la Memoria


def _media(almacen, criterios: list[str], desde: str) -> float | None:
    if not criterios:
        return None
    valores = []
    for f in almacen.db.execute("SELECT ev.* FROM evaluaciones ev JOIN ejecuciones e ON e.id = ev.ejecucion_id WHERE e.fecha >= ?",
                                (desde,)).fetchall():
        for c in criterios:
            if c in f.keys() and f[c] is not None:
                valores.append(f[c])
    return round(sum(valores) / len(valores), 1) if valores else None


def resumen(cfg: Config, almacen, r: Rol, hoy: date | None = None) -> ResumenRol:
    hoy = hoy or date.today()
    desde7 = (hoy - timedelta(days=7)).isoformat()
    gastos = [g for g in almacen.gastos(desde7) if g.concepto in r.conceptos]
    patrones = [x for x in almacen.patrones() if r.destino and x.destino == r.destino]
    en_vigor = [x for x in patrones if x.estado in ("aceptada", "aplicada")]
    return ResumenRol(
        id=r.id, nombre=r.nombre, departamento=r.departamento, que_hace=r.que_hace,
        modelo=cfg.pipeline.modelos.get(r.etapa) if r.etapa else None,
        esfuerzo=cfg.pipeline.esfuerzo.get(r.etapa) if r.etapa else None,
        coste_7d_usd=round(sum(g.coste for g in gastos if g.moneda == "USD"), 2),
        coste_7d_eur=round(sum(g.coste for g in gastos if g.moneda == "EUR"), 2),
        llamadas_7d=len(gastos), nota=_media(almacen, r.criterios, (hoy - timedelta(days=14)).isoformat()),
        criterios=r.criterios, reglas={c: sum(1 for x in en_vigor if x.capa == c) for c in CAPAS},
        pendientes=sum(1 for x in patrones if x.estado == "propuesta"),
        pedidos_7d=len(almacen.mensajes_para(r.id, desde7)))


def detalle(cfg: Config, almacen, r: Rol, hoy: date | None = None) -> DetalleRol:
    hoy = hoy or date.today()
    base = resumen(cfg, almacen, r, hoy)
    patrones = [x for x in almacen.patrones() if r.destino and x.destino == r.destino and x.estado != "rechazada"]
    orden = {"oficio": 0, "marca": 1, "celda": 2}
    reglas = sorted((ReglaRol(id=x.id, capa=x.capa, estado=x.estado, patron=x.patron, propuesta=x.propuesta, origen=x.origen,
                              fecha=x.creado_en[:10]) for x in patrones),
                    key=lambda x: (x.estado == "propuesta", orden.get(x.capa, 3), x.fecha))
    pedidos = [Pedido(pieza=m["pieza_id"], texto=m["texto"], fecha=m["creado_en"][:10])
               for m in almacen.mensajes_para(r.id, (hoy - timedelta(days=30)).isoformat())]
    comparten = [x.nombre for x in equipo(cfg).roles if r.destino and x.destino == r.destino and x.id != r.id]
    return DetalleRol(**base.model_dump(), reglas_lista=reglas, pedidos_lista=pedidos[:20], comparte_reglas_con=comparten)
