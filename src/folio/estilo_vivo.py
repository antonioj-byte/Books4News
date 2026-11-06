"""El libro de estilo vivo (6/11, a petición del usuario: «me interesa mucho activar un proceso de retroalimentación
permanente, de tal forma que el equipo editorial vaya recursivamente mejorando su sistema editorial… al final, cada línea
de código es un nuevo if sobre las consideraciones editoriales»; propuesta en seis puntos, «adelante con todo»).

1. **Fichas**: cada regla de criterio es una ficha de la tabla `memoria` (rol, texto, ejemplo bueno y malo, de dónde
   sale, estado: propuesta, aceptada —activa, entra en el prompt de su agente—, aplicada —ya escrita en el prompt—,
   retirada o rechazada). `llm.reglas_aceptadas` las pega con sus ejemplos.
2. **Ejemplos antes que reglas**: las ediciones de la redacción (la primera versión con guion frente a la última,
   diapositiva a diapositiva) se cosechan como candidatos y, cada semana, un modelo barato elige los que enseñan criterio
   y escribe la lección; los activos (como mucho `estilo.ejemplos_max`) entran en el guionista y el chat
   (`llm.ejemplos_activos`).
3. **Prueba en el banco**: una ficha del guionista se prueba reescribiendo unas pocas piezas aprobadas con ella y sin
   ella (`llm.sin_fichas`) y un juez a ciegas compara (`prompts/juez_voz.md`). El resultado queda en la ficha; si
   empeora, se marca para revisar (aceptar sigue siendo aplicar: decisión del 2/11).
4. **Poda**: si un rol pasa de `estilo.max_activas_por_rol` fichas activas o hay fichas sin refuerzo en
   `estilo.dias_sin_refuerzo` días, un editor propone fundirlas o retirarlas (`prompts/estilo_poda.md`); son propuestas
   de origen «poda» que se aceptan en la web (aceptar una fusión retira las fundidas).
5. **El bucle sin la sesión**: una ficha aceptada que necesita código («codigo»), o una retirada que ya estaba escrita
   en un prompt, abre una issue en GitHub (con `FOLIO_GITHUB_TOKEN`), que una tarea programada recoge cada semana y
   resuelve en una rama, sin mergear.
6. **El público**: las métricas de Instagram de lo publicado (`folio.metricas`) llegan a la Memoria.
"""

from __future__ import annotations

import copy
import difflib
import json
import os
import random
from datetime import date, timedelta

from pydantic import BaseModel, Field

from folio.almacen import Almacen, Patron
from folio.config import Config
from folio.llm import LLM, ErrorLLM, cargar_prompt, sin_fichas
from folio.verificacion_texto import normalizar

ACTIVAS = ("aceptada", "aplicada")
# Los destinos cuyas fichas se pueden probar en el banco (reescribiendo guiones)
PROBABLES = ("guionista", "formatos")
ETIQUETA_GITHUB = "folio-memoria"


# --- 2. Ejemplos de la redacción ----------------------------------------------------------------

def _vale_como_ejemplo(antes: str, despues: str) -> bool:
    """Ni una errata (casi igual) ni otra cosa (nada que ver): un cambio de escritura sobre lo mismo."""
    a, b = normalizar(antes), normalizar(despues)
    if len(a.split()) < 4 or len(b.split()) < 4 or a == b:
        return False
    sm = difflib.SequenceMatcher(None, a.split(), b.split())               # por palabras: las letras se parecen siempre
    cambiadas = [w for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal" for w in a.split()[i1:i2] + b.split()[j1:j2]]
    if len(cambiadas) <= 2 or all(w.isdigit() for w in cambiadas):        # una errata o un dato (un año, una cifra)
        return False
    return 0.2 <= sm.ratio() <= 0.9


def cosechar(almacen: Almacen, dias: int = 30, hoy: date | None = None) -> int:
    """Guarda como candidatos los pares antes/después de las ediciones de la redacción. Devuelve cuántos son nuevos."""
    desde = ((hoy or date.today()) - timedelta(days=dias)).isoformat()
    nuevos = 0
    for par in almacen.pares_de_edicion(desde):
        if _vale_como_ejemplo(par["antes"], par["despues"]) and almacen.guardar_ejemplo(par):
            nuevos += 1
    return nuevos


class JuicioEjemplo(BaseModel):
    id: int
    ensena: bool = Field(description="True si el cambio enseña criterio de escritura que vale para otras piezas; false si "
                                     "solo corrige un dato de esta pieza, cambia el tema o es cuestión de gusto suelto")
    leccion: str = Field(description="Lo que enseña, en una frase de 8 a 25 palabras, como consejo al guionista; vacía si no enseña")


class JuicioEjemplos(BaseModel):
    ejemplos: list[JuicioEjemplo]


def elegir_ejemplos(llm: LLM, cfg: Config, almacen: Almacen) -> tuple[int, int]:
    """Juzga los candidatos (Haiku, ~0,003 $), activa los que enseñan y deja activos solo los `ejemplos_max` más
    recientes. Devuelve (activados, descartados)."""
    candidatos = almacen.ejemplos("candidato")[:20]
    activados = descartados = 0
    if candidatos:
        bloque = "\n\n".join(f"<ejemplo id=\"{e.id}\" diapositiva=\"{e.tipo}\" formato=\"{e.formato}\">\nAntes: {e.antes}\n"
                             f"Después: {e.despues}\n</ejemplo>" for e in candidatos)
        prompt = cargar_prompt(cfg, "estilo_ejemplos", {"[pegar ejemplos]": bloque})
        r, _ = llm.estructurado("estilo-ejemplos", [{"role": "user", "content": prompt}], JuicioEjemplos,
                                etapa_modelo="estilo_ejemplos", max_tokens=8000)
        juicios = {j.id: j for j in r.ejemplos}
        for e in candidatos:
            j = juicios.get(e.id)
            if j and j.ensena and j.leccion.strip():
                almacen.decidir_ejemplo(e.id, "activo", j.leccion.strip())
                activados += 1
            elif j:
                almacen.decidir_ejemplo(e.id, "descartado", j.leccion.strip())
                descartados += 1
    for e in almacen.ejemplos("activo")[cfg.pipeline.estilo.ejemplos_max:]:
        almacen.decidir_ejemplo(e.id, "retirado")
    return activados, descartados


# --- 3. Prueba en el banco -------------------------------------------------------------------------

def banco(cfg: Config, almacen: Almacen, n: int) -> list:
    """Las últimas piezas aprobadas o publicadas que escribe el guionista y tienen sus textos congelados."""
    from folio import formatos
    from folio.etapas import EtapasGuardadas
    out, vistas = [], set()
    for _fecha, _eid, p, _v, _t in almacen.archivo():
        if p.id in vistas or p.estado not in ("aprobada", "publicada") or not p.guion:
            continue
        if formatos.de(p.eleccion.formato).propio:
            continue
        textos = EtapasGuardadas(cfg.dir_cache(p.fecha)).textos(p.historia_id)
        if not textos:
            continue
        vistas.add(p.id)
        out.append((p, textos))
        if len(out) >= n:
            break
    return out


def _cfg_prueba(cfg: Config) -> Config:
    """La configuración de la prueba: el guionista en esfuerzo medio y sin el lector sin contexto (más barato; lo que
    se compara es la ficha, no el esfuerzo)."""
    c = copy.copy(cfg)
    c.pipeline = cfg.pipeline.model_copy(deep=True)
    c.pipeline.esfuerzo["guion"] = "medium"
    c.pipeline.guion.lector_sin_contexto = False
    return c


def _con_cfg(llm, cfg_p: Config):
    """El mismo cliente y las mismas trazas, con otra configuración."""
    if isinstance(llm, LLM):
        otro = LLM(cfg_p, cliente=llm._cliente, reutilizar=llm.reutilizar)
        otro.trazas = llm.trazas
        return otro
    otro = copy.copy(llm)
    otro.cfg = cfg_p
    if not hasattr(otro, "trazas"):
        otro.trazas = []
    return otro


def _texto_guion(g) -> str:
    return "\n".join(f"[{d.n} · {d.tipo}] {d.texto}" + (f"\n{d.subtitulo}" if d.subtitulo else "") for d in g.diapositivas) \
        + f"\n[pie] {g.pie_instagram}"


def probar(llm: LLM, cfg: Config, almacen: Almacen, ficha_id: int, semilla: int | None = None) -> dict:
    """Escribe unas pocas piezas del banco con la ficha y sin ella y las juzga a ciegas. Guarda el resultado en la ficha
    y lo devuelve: {"veredicto": mejora|igual|empeora|sin_banco, "con": media, "sin": media, "piezas": […], "coste_usd"}."""
    from folio import guion as guionista
    from folio.juez import Juicio
    f = almacen.patron(ficha_id)
    if not f:
        raise ValueError(f"No existe la ficha {ficha_id}")
    if f.destino not in PROBABLES:
        raise ValueError("Solo se prueban en el banco las fichas del guionista y de los formatos")
    piezas = banco(cfg, almacen, cfg.pipeline.estilo.prueba_piezas)
    if not piezas:
        res = {"veredicto": "sin_banco", "nota": "No hay piezas aprobadas con sus textos guardados para probar", "fecha": date.today().isoformat()}
        almacen.guardar_ficha(ficha_id, prueba=json.dumps(res, ensure_ascii=False))
        return res
    llm_p = _con_cfg(llm, _cfg_prueba(cfg))
    antes = len(llm_p.trazas)
    rnd = random.Random(semilla if semilla is not None else ficha_id)
    voz = (cfg.dir_prompts / "voz_folio.md").read_text(encoding="utf-8").strip()
    notas = {"con": [], "sin": []}
    detalle = []
    for p, textos in piezas:
        versiones = {}
        for cual in ("con", "sin"):
            ids = set() if cual == "con" else {ficha_id}
            with sin_fichas(ids):
                try:
                    g, _, _ = guionista.escribir(llm_p, f"{p.id}-prueba-{ficha_id}-{cual}", p.eleccion, textos, p.libros)
                except Exception as exc:                 # un guion que no sale cuenta como el peor
                    g = None
                    detalle.append(f"{p.id} ({cual}): no salió ({type(exc).__name__})")
            versiones[cual] = g
        letras = ["A", "B"]
        rnd.shuffle(letras)
        clave = dict(zip(("con", "sin"), letras))
        bloque = "\n\n".join(f"<version letra=\"{clave[c]}\">\n{_texto_guion(g) if g else '(no salió)'}\n</version>"
                             for c, g in sorted(versiones.items(), key=lambda x: clave[x[0]]))
        prompt = cargar_prompt(cfg, "juez_voz", {"[pegar voz]": voz, "[pegar versiones]": bloque})
        juicio, _ = llm.estructurado(f"estilo-juez:{ficha_id}:{p.id}", [{"role": "user", "content": prompt}], Juicio,
                                     etapa_modelo="juez", max_tokens=8000)
        por_letra = {n.letra.strip().upper()[:1]: n for n in juicio.versiones}
        for c in ("con", "sin"):
            n = por_letra.get(clave[c])
            puntos = (n.idea + n.voz) / 2 if n and versiones[c] else 1.0
            notas[c].append(puntos)
        detalle.append(f"{p.id}: con {notas['con'][-1]:.1f}, sin {notas['sin'][-1]:.1f}")
    con, sin = sum(notas["con"]) / len(notas["con"]), sum(notas["sin"]) / len(notas["sin"])
    umbral = cfg.pipeline.estilo.prueba_umbral
    veredicto = "mejora" if con - sin >= umbral else "empeora" if sin - con >= umbral else "igual"
    res = {"veredicto": veredicto, "con": round(con, 2), "sin": round(sin, 2), "piezas": detalle,
           "coste_usd": round(sum(t.coste_usd or 0 for t in llm_p.trazas[antes:]), 3), "fecha": date.today().isoformat()}
    almacen.guardar_ficha(ficha_id, prueba=json.dumps(res, ensure_ascii=False))
    return res


def por_probar(almacen: Almacen, maximo: int) -> list[Patron]:
    """Las fichas activas del guionista aceptadas desde la web que aún no se han probado (las de las conversaciones ya
    están escritas en el prompt y no se pueden quitar para comparar)."""
    return [f for f in almacen.patrones() if f.estado == "aceptada" and f.destino in PROBABLES and not f.prueba][:maximo]


# --- 4. Poda ------------------------------------------------------------------------------------

class Fusion(BaseModel):
    ids: list[int] = Field(description="Las fichas que se funden (dos o más)")
    regla: str = Field(description="La regla que las sustituye, como iría en las instrucciones del agente")
    por_que: str = Field(description="Por qué se pueden fundir, en una línea")


class Retiro(BaseModel):
    id: int
    motivo: str = Field(description="Por qué sobra: repetida, contradicha por otra, ya no se da el caso…")


class Poda(BaseModel):
    fusiones: list[Fusion]
    retiros: list[Retiro]


def _activas_por_destino(almacen: Almacen) -> dict[str, list[Patron]]:
    out: dict[str, list[Patron]] = {}
    for f in almacen.patrones():
        if f.estado in ACTIVAS and f.origen != "poda":
            out.setdefault("guionista" if f.destino == "formatos" else f.destino, []).append(f)
    return out


def a_podar(cfg: Config, almacen: Almacen, hoy: date | None = None) -> dict[str, tuple[list[Patron], list[Patron]]]:
    """Por destino: (activas, viejas sin refuerzo), solo de los destinos que pasan del tope o tienen viejas."""
    hoy = hoy or date.today()
    limite = (hoy - timedelta(days=cfg.pipeline.estilo.dias_sin_refuerzo)).isoformat()
    out = {}
    for destino, activas in _activas_por_destino(almacen).items():
        viejas = [f for f in activas if f.origen == "feedback" and f.actualizado_en[:10] < limite]
        if len(activas) > cfg.pipeline.estilo.max_activas_por_rol or viejas:
            out[destino] = (activas, viejas)
    return out


def podar(llm: LLM, cfg: Config, almacen: Almacen, hoy: date | None = None) -> list[int]:
    """Propone fusiones y retiros para los destinos que lo necesitan (una llamada por destino, ~0,03 $). Las propuestas
    quedan como fichas «propuesta» de origen «poda»; la nota guarda qué fichas retira al aceptarse."""
    ya = {json.dumps(json.loads(f.nota).get("retira", []), sort_keys=True) for f in almacen.patrones()
          if f.origen == "poda" and f.estado == "propuesta" and f.nota.startswith("{")}
    nuevas = []
    for destino, (activas, viejas) in a_podar(cfg, almacen, hoy).items():
        bloque = "\n".join(f"{f.id}. [{f.estado}{', sin refuerzo' if f in viejas else ''}] {f.propuesta}" for f in activas)
        prompt = cargar_prompt(cfg, "estilo_poda", {"[pegar rol]": destino, "[pegar tope]": str(cfg.pipeline.estilo.max_activas_por_rol),
                                                    "[pegar fichas]": bloque})
        r, _ = llm.estructurado(f"estilo-poda:{destino}", [{"role": "user", "content": prompt}], Poda,
                                etapa_modelo="memoria", max_tokens=12000)
        validos = {f.id for f in activas}
        for fu in r.fusiones:
            ids = sorted({i for i in fu.ids if i in validos})
            clave = json.dumps(ids, sort_keys=True)
            if len(ids) < 2 or not fu.regla.strip() or clave in ya:
                continue
            ya.add(clave)
            nuevas.append(_propuesta_poda(almacen, destino, f"Fundir {len(ids)} fichas: {fu.por_que}", fu.regla, ids))
        for re_ in r.retiros:
            clave = json.dumps([re_.id], sort_keys=True)
            if re_.id not in validos or clave in ya:
                continue
            ya.add(clave)
            nuevas.append(_propuesta_poda(almacen, destino, f"Retirar la ficha {re_.id}: {re_.motivo}", "", [re_.id]))
    return nuevas


def _propuesta_poda(almacen: Almacen, destino: str, patron: str, regla: str, retira: list[int]) -> int:
    textos = {f.id: f.propuesta for f in almacen.patrones()}
    pid = almacen.guardar_patron(patron, [f"#{i}: {textos.get(i, '')[:140]}" for i in retira],
                                 regla or f"(Retirar: {textos.get(retira[0], '')[:200]})", destino)
    almacen.guardar_ficha(pid, origen="poda", nota=json.dumps({"retira": retira}))
    return pid


def al_aceptar(cfg: Config, almacen: Almacen, ficha_id: int) -> list[str]:
    """Lo que pasa al aceptar una ficha: una de poda retira las que funde o retira; una de código abre su encargo.
    Devuelve avisos."""
    f = almacen.patron(ficha_id)
    if not f:
        return []
    avisos = []
    if f.origen == "poda" and f.nota.startswith("{"):
        for i in json.loads(f.nota).get("retira", []):
            avisos += retirar(cfg, almacen, i, f"Por la poda #{ficha_id}")
        if f.propuesta.startswith("(Retirar:"):            # una propuesta de retiro no deja regla nueva
            almacen.decidir_patron(ficha_id, "aplicada", f.nota)
    elif f.destino == "codigo":
        avisos += encargar(cfg, almacen, f, "Implementar esta regla aceptada en la Memoria")
    return avisos


def retirar(cfg: Config, almacen: Almacen, ficha_id: int, motivo: str = "") -> list[str]:
    """Retira una ficha. Si ya estaba escrita en un prompt (aplicada), además encarga quitarla de ahí."""
    f = almacen.patron(ficha_id)
    if not f or f.estado == "retirada":
        return []
    almacen.decidir_patron(ficha_id, "retirada", motivo or f.nota)
    if f.estado == "aplicada":
        return encargar(cfg, almacen, f, "Quitar esta regla de los prompts (retirada en el libro de estilo)")
    return []


# --- 5. Encargos de código -----------------------------------------------------------------------

def texto_encargo(f: Patron, que: str) -> str:
    return (f"{que}.\n\n**Ficha #{f.id}** ({f.destino}, {f.capa}, origen {f.origen})\n\n**Regla**: {f.propuesta}\n\n"
            f"**Lo que se repetía**: {f.patron}\n\n**Evidencia**:\n" + "\n".join(f"- {e}" for e in f.evidencia[:8])
            + (f"\n\nAsí sí: «{f.ejemplo_bueno}»" if f.ejemplo_bueno else "")
            + (f"\n\nAsí no: «{f.ejemplo_malo}»" if f.ejemplo_malo else "")
            + "\n\nHazlo en una rama `memoria/…`, con tests y la entrada en CLAUDE.md y config/memoria_conversacion.yaml; "
              "no mergees: la redacción dirá «mergea».")


def encargar(cfg: Config, almacen: Almacen, f: Patron, que: str, cliente=None) -> list[str]:
    """Abre una issue en GitHub con el encargo (etiqueta `folio-memoria`), que recoge la tarea semanal. Sin
    FOLIO_GITHUB_TOKEN, el encargo queda en la ficha para pasarlo a mano. Nunca falla."""
    import httpx
    texto = texto_encargo(f, que)
    token, repo = os.getenv("FOLIO_GITHUB_TOKEN"), cfg.pipeline.estilo.github_repo
    if not token or not repo:
        almacen.guardar_ficha(f.id, encargo="pendiente: " + que)
        return [f"Encargo de código de la ficha #{f.id} guardado en la ficha (sin FOLIO_GITHUB_TOKEN no se abre la issue)"]
    try:
        c = cliente or httpx.Client(timeout=20)
        r = c.post(f"https://api.github.com/repos/{repo}/issues",
                   headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                   json={"title": f"[Memoria #{f.id}] {que}: {f.propuesta[:70]}", "body": texto, "labels": [ETIQUETA_GITHUB]})
        if r.status_code in (403, 429):
            almacen.guardar_ficha(f.id, encargo="pendiente: " + que)
            return [f"GitHub respondió {r.status_code}: el encargo de la ficha #{f.id} queda en la ficha, sin reintentar"]
        r.raise_for_status()
        url = r.json().get("html_url", "")
        almacen.guardar_ficha(f.id, encargo=url)
        return [f"Encargo de código de la ficha #{f.id}: {url}"]
    except Exception as exc:                            # noqa: BLE001
        almacen.guardar_ficha(f.id, encargo="pendiente: " + que)
        return [f"No se pudo abrir la issue de la ficha #{f.id} ({type(exc).__name__}); el encargo queda en la ficha"]


# --- El ciclo semanal -------------------------------------------------------------------------

def ciclo(llm: LLM, cfg: Config, almacen: Almacen, probar_pendientes: bool = True, hoy: date | None = None) -> list[str]:
    """Lo que hace el libro de estilo cada semana, tras el análisis de la Memoria: cosechar y elegir ejemplos, podar y
    probar en el banco las fichas nuevas del guionista (como mucho `estilo.prueba_max_semana`). Cada paso, aparte: un
    fallo no para los demás. Devuelve líneas para el registro."""
    lineas = []
    try:
        n = cosechar(almacen, hoy=hoy)
        act, desc = elegir_ejemplos(llm, cfg, almacen)
        lineas.append(f"Ejemplos: {n} candidatos nuevos; {act} activados, {desc} descartados")
    except Exception as exc:                            # noqa: BLE001
        lineas.append(f"Ejemplos: no se pudo ({type(exc).__name__}: {exc})")
    try:
        nuevas = podar(llm, cfg, almacen, hoy)
        lineas.append(f"Poda: {len(nuevas)} propuestas")
    except Exception as exc:                            # noqa: BLE001
        lineas.append(f"Poda: no se pudo ({type(exc).__name__}: {exc})")
    if probar_pendientes:
        for f in por_probar(almacen, cfg.pipeline.estilo.prueba_max_semana):
            try:
                r = probar(llm, cfg, almacen, f.id)
                lineas.append(f"Prueba de la ficha #{f.id}: {r['veredicto']} (con {r.get('con')}, sin {r.get('sin')})")
            except (ErrorLLM, ValueError) as exc:
                lineas.append(f"Prueba de la ficha #{f.id}: no se pudo ({exc})")
    return lineas

