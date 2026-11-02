"""El fondo del mes (2/11, a petición del usuario: «una selección de 150 historias más o menos reciclables, porque no
es de actualidad urgente sino de actualidad lateral; eso nos permite tener un mayor margen de previsión»).

Una despensa de propuestas de pieza que valen unos meses: titular, gancho, cuestión de fondo y libros ya verificados.
Se prepara el día 1 de cada mes en tandas (`preparar_tanda`):

1. **Cosecha** (sin modelo): las historias de los últimos 30 días (data/cache/<fecha>/historias.json) agrupadas entre
   días por las palabras de su titular y su resumen; puntúa más lo que vuelve muchos días y en muchos medios.
2. **El jefe de cultura en versión fondo** (Opus, prompts/jefe_fondo.md, con la línea editorial y las reglas de libros
   de la mesa) propone la tanda con el reparto de formatos que toque, sin repetir lo que ya está en el fondo.
3. **Filtro**: el evaluador de puentes deja fuera las forzadas y la verificación de libros, las que no tienen libro en
   castellano (o novedad, salvo los perfiles de «Tres libros»).

Lo que pasa queda «disponible» en la tabla `fondo` hasta su fecha de caducidad. Escribir una propuesta la convierte en
un tema de la redacción (folio.temas), que busca las noticias más recientes del tema: así la pieza cuenta lo último.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from pydantic import BaseModel, Field

from folio.config import Config
from folio.llm import LLM, ErrorLLM, cargar_prompt
from folio.modelos import Formato, HistoriaElegida, LibroCandidato, SeleccionJefe
from folio.verificacion_texto import apellido, autor_coincide, clave_libro, normalizar

PREFIJO = "fondo-"
DIAS_COSECHA = 30
# Reparto del mes (2/11, propuesta aprobada por el usuario: «adelante»): 150 propuestas
REPARTO_MES = {"lateral": 60, "dialogo": 35, "balda": 20, "recomendado": 20, "edicion": 15}
POR_TANDA = 25
MAX_COSECHA = 80                      # temas de la cosecha que ve el jefe en cada tanda
_VACIAS = set("""a al ante bajo cabe con contra de del desde durante en entre hacia hasta mediante para por segun sin so
sobre tras y e ni o u que el la los las un una unos unas lo su sus se es son ha han como mas pero muy ya no si este esta
estos estas ese esa esos esas le les nos tras tras cuando donde quien cual sobre tambien""".split())


class PropuestaFondo(BaseModel):
    formato: Formato = Field(description="lateral, dialogo, balda, recomendado o edicion")
    historia: str = Field(description="El id del tema de la cosecha en que se basa; vacío si sale de un debate que no está en la cosecha")
    titular: str = Field(description="Titular de portada, 12 palabras como máximo, que siga valiendo dentro de dos meses")
    de_que_se_habla: str = Field(description="De qué se habla, en dos frases")
    cuestion_de_fondo: str = Field(description="La cuestión de fondo, en una frase")
    gancho_libro: str = Field(description="El puente entre el tema y el libro, en una línea")
    libros_candidatos: list[LibroCandidato] = Field(description="3–4 libros candidatos por orden de preferencia (4–6 en balda)")
    protagonista: str = Field(description="Solo en mundo del libro: nombre completo de quien la protagoniza; si no, vacío")
    potencial: int = Field(description="De 1 a 10, cuánto puede circular")
    por_que_dura: str = Field(description="En una línea, por qué esta conversación seguirá abierta")
    meses: int = Field(description="De 1 a 3, cuántos meses vale")
    reactivar: str = Field(description="En una línea, qué noticia la volvería urgente")
    por_que: str = Field(description="Por qué esta propuesta, en dos líneas")


class TandaFondo(BaseModel):
    propuestas: list[PropuestaFondo]
    aviso: str | None = Field(default=None, description="Si propones menos de las pedidas, por qué; si no, null")


# --- Cosecha -----------------------------------------------------------------------------

@dataclass
class TemaCosecha:
    id: str
    titular: str
    resumen: str
    dias: list[str]
    medios: set[str]

    @property
    def peso(self) -> float:
        return len(self.dias) * 2 + len(self.medios) * 0.5


def _palabras(texto: str) -> set[str]:
    return {w for w in normalizar(texto).split() if len(w) > 3 and w not in _VACIAS}


def cosecha(cfg: Config, fecha: str, dias: int = DIAS_COSECHA) -> list[TemaCosecha]:
    """Las historias de los `dias` anteriores a `fecha`, agrupadas entre días (dos se juntan si comparten un tercio de las
    palabras de su titular y resumen), ordenadas por peso: días distintos y medios. Sin modelo ni red."""
    from folio.etapas import EtapasGuardadas
    temas: list[tuple[TemaCosecha, set[str]]] = []
    hoy = date.fromisoformat(fecha)
    for i in range(1, dias + 1):
        d = (hoy - timedelta(days=i)).isoformat()
        try:
            _, resumidas, _ = EtapasGuardadas(cfg.dir_cache(d)).historias()
        except (FileNotFoundError, KeyError, ValueError):
            continue
        for r in resumidas:
            if not r.titular_es:
                continue
            pal = _palabras(f"{r.titular_es} {r.resumen_es or ''}")
            if len(pal) < 3:
                continue
            igual = next((t for t, p in temas if len(pal & p) >= max(3, len(pal | p) // 3)), None)
            if igual:
                if d not in igual.dias:
                    igual.dias.append(d)
                igual.medios |= set(r.medios)
                for t, p in temas:
                    if t is igual:
                        p |= pal
                        break
            else:
                temas.append((TemaCosecha(id=f"c{len(temas) + 1}", titular=r.titular_es, resumen=r.resumen_es or "",
                                          dias=[d], medios=set(r.medios)), pal))
    return sorted((t for t, _ in temas), key=lambda t: -t.peso)


def _bloque_cosecha(temas: list[TemaCosecha]) -> str:
    if not temas:
        return "(vacía: Folio lleva pocos días guardando historias; propón a partir de los debates abiertos que conozcas)"
    return "\n".join(f"- [{t.id}] {t.titular} — {t.resumen[:220]} ({len(t.dias)} días, {len(t.medios)} medios)"
                     for t in temas[:MAX_COSECHA])


def _bloque_fondo(existentes: list[dict]) -> str:
    if not existentes:
        return "(vacío)"
    return "\n".join(f"- [{x['formato']}] {x['titular']} — {x['cuestion']}" for x in existentes)


# --- Tanda ---------------------------------------------------------------------------------

def reparto_de_tanda(hechas: dict[str, int], n: int = POR_TANDA, mes: dict[str, int] | None = None) -> dict[str, int]:
    """Lo que toca pedir en la próxima tanda: lo que falta de cada formato, repartido en proporción y sin pasarse."""
    mes = REPARTO_MES if mes is None else mes
    falta = {f: max(0, mes[f] - hechas.get(f, 0)) for f in mes}
    total = sum(falta.values())
    if total == 0:
        return {}
    n = min(n, total)
    reparto = {f: min(falta[f], round(n * falta[f] / total)) for f in mes}
    # Ajuste por redondeo: añade o quita de los que más faltan
    while sum(reparto.values()) < n:
        f = max((f for f in mes if reparto[f] < falta[f]), key=lambda f: falta[f] - reparto[f])
        reparto[f] += 1
    while sum(reparto.values()) > n:
        f = max((f for f in mes if reparto[f] > 0), key=lambda f: reparto[f])
        reparto[f] -= 1
    return {f: k for f, k in reparto.items() if k}


_NOMBRES = {"lateral": "lectura lateral", "dialogo": "diálogo con la actualidad", "balda": "tres libros",
            "recomendado": "libro recomendado", "edicion": "mundo del libro"}


POR_LLAMADA = 6                       # 25, y aun 8 con esfuerzo alto, no caben en 21.000 tokens (probado el 2/11)


def proponer(llm: LLM, cfg: Config, fecha: str, reparto: dict[str, int], temas: list[TemaCosecha],
             existentes: list[dict]) -> TandaFondo:
    """La tanda, en llamadas de `POR_LLAMADA` propuestas; cada una ve las anteriores para no repetirlas."""
    from folio.seleccion import criterios
    propuestas, avisos = [], []
    ya = list(existentes)
    pendiente = dict(reparto)
    while sum(pendiente.values()) > 0:
        trozo = reparto_de_tanda({}, min(POR_LLAMADA, sum(pendiente.values())), pendiente)
        texto_reparto = ", ".join(f"{k} de {_NOMBRES[f]} (`{f}`)" for f, k in trozo.items())
        prompt = cargar_prompt(cfg, "jefe_fondo", {
            "[pegar reparto]": texto_reparto, "[pegar criterios]": criterios(cfg, fecha),
            "[pegar cosecha]": _bloque_cosecha(temas), "[pegar fondo]": _bloque_fondo(ya)})
        try:
            r, _ = llm.estructurado(f"fondo:{fecha}:{len(propuestas)}", [{"role": "user", "content": prompt}], TandaFondo,
                                    etapa_modelo="fondo", max_tokens=21000)
        except ErrorLLM as exc:
            if not propuestas:
                raise
            avisos.append(f"una llamada falló ({exc}); la tanda se queda con {len(propuestas)}")
            break
        propuestas += r.propuestas
        if r.aviso:
            avisos.append(r.aviso)
        ya += [{"formato": p.formato, "titular": p.titular, "cuestion": p.cuestion_de_fondo} for p in r.propuestas]
        for f, k in trozo.items():
            pendiente[f] -= k
        pendiente = {f: k for f, k in pendiente.items() if k > 0}
    return TandaFondo(propuestas=propuestas, aviso=" ".join(avisos) or None)


def a_elegida(p: PropuestaFondo, n: int) -> HistoriaElegida:
    return HistoriaElegida(formato=p.formato, historia_id=f"{PREFIJO}{n}", titular=p.titular,
                           de_que_se_habla=p.de_que_se_habla, cuestion_de_fondo=p.cuestion_de_fondo,
                           libros_candidatos=p.libros_candidatos, gancho_libro=p.gancho_libro,
                           protagonista=p.protagonista, potencial=p.potencial, por_que=p.por_que)


@dataclass
class ResultadoTanda:
    guardadas: int
    pedidas: int
    fuera: list[str]
    avisos: list[str]


def preparar_tanda(cfg: Config, almacen, fecha: str, llm: LLM | None = None, n: int = POR_TANDA) -> ResultadoTanda:
    """Una tanda del fondo del mes de `fecha`: cosecha, jefe, puentes y verificación; guarda lo que pasa."""
    from folio import puentes
    from folio.pipeline import Pipeline
    llm = llm or LLM(cfg)
    mes = fecha[:7]
    del_mes = almacen.fondo(mes=mes)
    reparto = reparto_de_tanda({f: sum(1 for x in del_mes if x["formato"] == f) for f in REPARTO_MES}, n, REPARTO_MES)
    if not reparto:
        return ResultadoTanda(0, 0, [], [f"El fondo de {mes} ya está completo ({len(del_mes)} propuestas)"])
    existentes = almacen.fondo(estado="disponible")
    temas = cosecha(cfg, fecha)
    tanda = proponer(llm, cfg, fecha, reparto, temas, existentes)
    avisos = [f"Jefe (fondo): {tanda.aviso}"] if tanda.aviso else []
    base = almacen.siguiente_fondo()
    elegidas = [a_elegida(p, base + i) for i, p in enumerate(tanda.propuestas)]
    por_id = {e.historia_id: p for e, p in zip(elegidas, tanda.propuestas)}
    # Puentes: de diez en diez, que el evaluador puntúa listas cortas
    fuera: list[str] = []
    notas: dict[str, tuple[int, str]] = {}
    quedan: list[HistoriaElegida] = []
    for i in range(0, len(elegidas), 10):
        sel, ns, av = puentes.evaluar(llm, SeleccionJefe(elegidas=elegidas[i:i + 10]))
        quedan += sel.elegidas
        notas.update(ns)
        fuera += [a.split("fuera ", 1)[1] for a in av if "fuera «" in a]
    tuberia = Pipeline(cfg, fecha, llm=llm)
    tuberia._preverificar(quedan)
    usados: set[str] = set()
    guardar = []
    for e in quedan:
        tuberia.sin_novedad = e.formato == "balda"          # un perfil necesita la obra, no solo novedades
        libros, descartes = tuberia._verificar_libros(e, usados)
        if not libros:
            motivos = "; ".join(f"«{d.titulo}»: {d.motivo}" for d in descartes) or "sin libros"
            fuera.append(f"«{e.titular}» (ningún libro pasó: {motivos})")
            continue
        primero = e.libros_candidatos[0] if e.libros_candidatos else None
        if primero and e.formato != "balda" and _nombra(e, primero) and not any(
                autor_coincide(primero.autor, l.autores) for l in libros):
            # 2/11: «Naomi Klein y el mundo espejo…» salió con el libro de Da Empoli porque el de Klein ya estaba en otra
            # propuesta: si el titular o el gancho nombran el primer libro, una reserva de otro autor no vale
            fuera.append(f"«{e.titular}» (el libro que nombra, «{primero.titulo}», no pasó y la reserva es de otro autor)")
            continue
        usados |= {clave_libro(l.titulo_propuesto, l.autores[0] if l.autores else "") for l in libros}
        p = por_id[e.historia_id]
        puente = notas.get(e.historia_id)
        guardar.append({
            "formato": p.formato, "titular": p.titular, "cuestion": p.cuestion_de_fondo,
            "vale_hasta": (date.fromisoformat(fecha) + timedelta(days=30 * max(1, min(3, p.meses)))).isoformat(),
            "datos": {"propuesta": p.model_dump(), "libros": [l.model_dump(mode="json") for l in libros],
                      "puente": list(puente) if puente else None,
                      "cosecha": next(({"titular": t.titular, "dias": len(t.dias), "medios": len(t.medios)}
                                       for t in temas if t.id == p.historia), None)},
        })
    almacen.guardar_fondo(mes, guardar)
    return ResultadoTanda(len(guardar), len(tanda.propuestas), fuera, avisos)


def _nombra(e: HistoriaElegida, c: LibroCandidato) -> bool:
    """Si el titular o el gancho nombran el libro (su título o el apellido de su autor)."""
    texto = f" {normalizar(e.titular + ' ' + e.gancho_libro)} "
    return f" {normalizar(apellido(c.autor))} " in texto or f" {normalizar(c.titulo)} " in texto


def texto_tema(x: dict) -> str:
    """El texto del tema de la redacción con que se escribe una propuesta del fondo: el jefe lo respeta y busca las
    noticias más recientes del tema."""
    p, libros = x["datos"]["propuesta"], x["datos"]["libros"]
    libro = "; ".join(f"*{l['titulo_propuesto']}*, de {', '.join(l['autores'][:2])}" for l in libros)
    return (f"Del fondo del mes ({_NOMBRES.get(p['formato'], p['formato'])}): {p['titular']}. {p['de_que_se_habla']} "
            f"Cuestión de fondo: {p['cuestion_de_fondo']} Gancho: {p['gancho_libro']} Libro: {libro}. "
            "Cuenta lo último que haya pasado sobre el tema, con su fecha.")


def resumen_para_cli(x: dict) -> str:
    p = x["datos"]["propuesta"]
    libros = ", ".join(l["titulo_propuesto"] for l in x["datos"]["libros"])
    return f"[{x['id']}] {p['formato']:<11} {p['titular']}  ·  {libros}  ·  hasta {x['vale_hasta']}"
