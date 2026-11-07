"""«Cinco del libro» (2/11, prueba de cinco días pedida por el usuario: «las cinco noticias del mundo literario y
editorial más importantes del día»; la dirección «a sangre» del Wired original, con un subtítulo en cada noticia y una
ilustración por noticia en el estilo «con descaro» elegido en el Artifact «Cinco del libro»: el collage conceptual).

Cada madrugada, después de la mesa:
1. El jefe de cultura (Opus, `prompts/cinco.md`) elige cinco noticias del carril editorial y escribe para cada una
   titular, subtítulo, remate y la escena de su ilustración (una metáfora visual en inglés); el código lo valida y
   reintenta una vez con los errores.
2. Cinco ilustraciones, una por noticia, a la vez: Flux 2 Pro en vertical con el estilo de `prompts/cinco_estilo.md`
   y el revisor de letras (dos intentos cada una). La portada lleva la de la primera noticia.
3. Comprobación de hechos contra los textos de las cinco noticias.
La pieza entra en la mesa escrita («propuesta»), con su colofón de fuentes.

**Con elección de la redacción** (5/11, a petición del usuario: «tengo dudas si lo mejor es que me dé el post ya hecho
o me haga una propuesta de noticias; yo elijo las más importantes y finalmente monta el post»; `cinco.modo: propuesta`):
la madrugada solo hace la lista (`proponer`, Haiku, `prompts/cinco_propuesta.md`): unas diez noticias con una línea de
por qué importan y las cinco que el jefe publicaría ya marcadas, en `data/cache/<fecha>/cinco_propuesta.json`. En la
mesa se marcan las cinco y «Montar el post» hace los pasos 1–3 con esas, en ese orden (`escribir(elegidas=…)`): las
ilustraciones solo se pagan de lo elegido. Lo que la redacción cambió de la preselección queda en los avisos de la pieza
y en la Memoria. Con `cinco.modo: automatico`, como antes.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from folio.config import Config
from folio.etapas import guardar_json
from folio.llm import LLM, ErrorLLM, cache_al_final, cargar_prompt
from folio.modelos import Arte, Diapositiva, FuenteNoticia, GuionLLM, Historia, HistoriaElegida, Pieza

FORMATO = "cinco"
PREFIJO = "cinco-"
SUFIJO_IMAGEN = "-cinco"          # <pieza>-cinco-1.jpg … <pieza>-cinco-5.jpg
N = 7                             # como mucho; desde el 7/11 («Breves del libro») van de `cinco.minimo` a `cinco.maximo`
CARRILES = ("editorial", "radar")
DIAS_ESCENAS = 7
ANCHO, ALTO = 1088, 1360          # 4:5, múltiplos de 16 (Flux 2 Pro)
_PROHIBIDOS = re.compile(r"\b(medal|medallion|coin|plaque|sign|newspaper|screen|poster|banner)s?\b", re.I)


class NoticiaCinco(BaseModel):
    historia: str = Field(description="El id exacto de la noticia en la lista")
    titular: str = Field(description="De 12 palabras como máximo, sin pregunta")
    subtitulo: str = Field(description="De 10 a 20 palabras: qué ha pasado y por qué importa, sin repetir el titular")
    remate: str = Field(description="El final literal del titular, de 2 a 5 palabras")
    escena: str = Field(description="En inglés, de 15 a 45 palabras: la metáfora visual de la ilustración, sin nombres, letras ni cifras")


class GuionCinco(BaseModel):
    titular: str = Field(description="Titular de portada, de 12 palabras como máximo")
    subtitulo: str = Field(description="Subtítulo de portada, de 10 a 22 palabras")
    remate: str = Field(description="El final literal del titular de portada, de 2 a 5 palabras")
    noticias: list[NoticiaCinco] = Field(description="Las noticias, de 3 a 5, de más a menos importante")
    pie_instagram: str = Field(description="De 80 a 150 palabras")


def _palabras(t: str) -> int:
    return len(t.split())


def _remate_valido(titular: str, remate: str) -> bool:
    t, r = titular.strip().rstrip(".").strip(), remate.strip().rstrip(".").strip()
    return bool(r) and 2 <= _palabras(r) <= 5 and t.endswith(r)


def validar(g: GuionCinco, ids: set[str], minimo: int = 3, maximo: int = N, exactas: int | None = None) -> list[str]:
    """Los errores del guion de «Cinco del libro» (lista vacía si vale). Con `exactas`, tienen que ser esas."""
    from folio.imagenes.editorial import validar_escena
    errores = []
    if _palabras(g.titular) > 12 or g.titular.strip().endswith("?"):
        errores.append("El titular de portada tiene que tener 12 palabras como máximo y no ser una pregunta.")
    if not 10 <= _palabras(g.subtitulo) <= 22:
        errores.append(f"El subtítulo de portada tiene que tener de 10 a 22 palabras (tiene {_palabras(g.subtitulo)}).")
    if not _remate_valido(g.titular, g.remate):
        errores.append("El remate de portada tiene que ser el final literal del titular, de 2 a 5 palabras.")
    if exactas is not None and len(g.noticias) != exactas:
        errores.append(f"Tienen que ser exactamente {exactas} noticias (hay {len(g.noticias)}).")
    elif exactas is None and not minimo <= len(g.noticias) <= maximo:
        errores.append(f"Tienen que ser de {minimo} a {maximo} noticias (hay {len(g.noticias)}).")
    vistos = set()
    for i, x in enumerate(g.noticias, 1):
        if x.historia not in ids:
            errores.append(f"Noticia {i}: «{x.historia}» no es un id de la lista.")
        elif x.historia in vistos:
            errores.append(f"Noticia {i}: repite la historia {x.historia}.")
        vistos.add(x.historia)
        if _palabras(x.titular) > 12 or x.titular.strip().endswith("?"):
            errores.append(f"Noticia {i}: el titular tiene que tener 12 palabras como máximo y no ser una pregunta.")
        if not 10 <= _palabras(x.subtitulo) <= 20:
            errores.append(f"Noticia {i}: el subtítulo tiene que tener de 10 a 20 palabras (tiene {_palabras(x.subtitulo)}).")
        if not _remate_valido(x.titular, x.remate):
            errores.append(f"Noticia {i}: el remate tiene que ser el final literal del titular, de 2 a 5 palabras.")
        if _PROHIBIDOS.search(x.escena):
            errores.append(f"Noticia {i}: la escena no puede llevar medallas, monedas, placas, carteles, periódicos ni pantallas.")
        _, motivo = validar_escena(x.escena, max_palabras=45)
        if motivo:
            errores.append(f"Noticia {i}: {motivo}.")
    if not 60 <= _palabras(g.pie_instagram) <= 160:
        errores.append(f"El pie tiene que tener de 80 a 150 palabras (tiene {_palabras(g.pie_instagram)}).")
    return errores


# --- Escenas de los últimos días (para no repetir ideas) ---------------------------------------

def _ruta_escenas(cfg: Config) -> Path:
    return cfg.dir_datos / "cinco_escenas.json"


def escenas_recientes(cfg: Config, fecha: str) -> list[str]:
    try:
        datos = json.loads(_ruta_escenas(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hoy = date.fromisoformat(fecha)
    return [e for f, es in datos.items() if 0 < (hoy - date.fromisoformat(f)).days <= DIAS_ESCENAS for e in es]


def guardar_escenas(cfg: Config, fecha: str, escenas: list[str]) -> None:
    ruta = _ruta_escenas(cfg)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    datos[fecha] = escenas
    hoy = date.fromisoformat(fecha)
    datos = {f: e for f, e in datos.items() if (hoy - date.fromisoformat(f)).days <= 30}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


# --- Escribir ---------------------------------------------------------------------------------

def candidatas(historias: list[Historia]) -> list[Historia]:
    """Las del carril del libro y el radar y, desde el 5/11, las de la actualidad que tratan de libros (un premio
    Cervantes o un Planeta salen en la prensa general, no en los medios del sector)."""
    return [h for h in historias if h.titular_es and (h.carril in CARRILES or (h.carril == "actualidad" and h.sobre_libros))]


def cuantas(cfg: Config) -> tuple[int, int]:
    c = cfg.pipeline.cinco
    return min(c.minimo, c.maximo, N), min(c.maximo, N)


def en_espanol(h: Historia) -> bool:
    return any(a.idioma == "es" for a in h.articulos)


def _bloque(historias: list[Historia]) -> str:
    """La lista para el modelo, primero las del mundo en español (6/11: el Femina salía y el Herralde, fallado el
    mismo día, no; el orden por número de medios favorece lo de fuera), con la lengua de sus medios."""
    def linea(h: Historia) -> str:
        desde = min((a.publicado_en for a in h.articulos if a.publicado_en), default=None)
        lenguas = ", ".join(sorted({a.idioma for a in h.articulos}))
        return (f"- [{h.id}] {h.n_medios} medio{'s' if h.n_medios != 1 else ''} ({', '.join(h.medios[:4])}; en {lenguas})"
                + (f", desde el {desde.date().isoformat()}" if desde else "") + f": {h.titular_es}. {h.resumen_es or ''}")
    orden = sorted(historias, key=lambda h: not en_espanol(h))
    return "<noticias>\n" + "\n".join(linea(h) for h in orden) + "\n</noticias>"


ELEGIDAS_POR_LA_REDACCION = ("La redacción ya ha elegido las noticias: son exactamente las de la lista, todas, y en ese "
                             "orden (la primera abre). No elijas ni cambies el orden: escríbelas. Los criterios de "
                             "elección de abajo no aplican; el resto, sí.")


def escribir(llm: LLM, cfg: Config, fecha: str, historias: list[Historia],
             elegidas: list[str] | None = None) -> tuple[GuionCinco, list[str]]:
    """El guion de «Cinco del libro». Con `elegidas` (ids de historia, en orden), escribe esas cinco tal cual las eligió
    la redacción. ErrorLLM si no hay noticias bastantes o si no valida tras un reintento."""
    from folio.guion import linea_hoy
    lista = candidatas(historias)
    minimo, maximo = cuantas(cfg)
    if elegidas is not None:
        por_id = {h.id: h for h in lista}
        faltan = [i for i in elegidas if i not in por_id]
        if faltan or not minimo <= len(elegidas) <= maximo or len(set(elegidas)) != len(elegidas):
            raise ErrorLLM(f"Breves del libro: hay que elegir de {minimo} a {maximo} noticias distintas de la lista del día"
                           + (f" (no están: {', '.join(faltan)})" if faltan else ""))
        lista = [por_id[i] for i in elegidas]
    if len(lista) < minimo:
        raise ErrorLLM(f"Breves del libro: solo hay {len(lista)} noticias del mundo del libro hoy")
    usadas = escenas_recientes(cfg, fecha)
    prompt = cargar_prompt(cfg, "cinco", {"[pegar hoy]": linea_hoy(fecha), "[pegar noticias]": _bloque(lista),
                                          "[pegar cuantas]": f"de {minimo} a {maximo}",
                                          "[pegar eleccion]": ELEGIDAS_POR_LA_REDACCION if elegidas else "",
                                          "[pegar objetos]": "\n".join(f"- {e}" for e in usadas) or "(ninguna)"})
    mensajes = [{"role": "user", "content": prompt}]
    ids = {h.id for h in lista}
    avisos = []
    errores: list[str] = []
    for intento in range(2):
        g, _ = llm.estructurado(f"cinco:{fecha}:{intento + 1}", cache_al_final(mensajes, hasta=0), GuionCinco,
                                etapa_modelo="cinco", max_tokens=16000)
        errores = validar(g, ids, minimo, maximo, exactas=len(elegidas) if elegidas else None)
        if elegidas and not errores and [x.historia for x in g.noticias] != elegidas:
            errores = ["Las noticias tienen que ser las elegidas por la redacción, en su orden: " + ", ".join(elegidas) + "."]
        if not errores:
            return g, avisos
        avisos.append(f"Cinco del libro: rechazado en el intento {intento + 1}: " + " | ".join(errores))
        mensajes += [{"role": "assistant", "content": json.dumps(g.model_dump(), ensure_ascii=False)},
                     {"role": "user", "content": "No cumple estas condiciones:\n" + "\n".join(f"- {e}" for e in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    raise ErrorLLM("Breves del libro: el guion no cumple las reglas tras un reintento (" + " | ".join(errores) + ")")


def a_pieza(g: GuionCinco, pieza_id: str, fecha: str, historias: list[Historia]) -> Pieza:
    por_id = {h.id: h for h in historias}
    diapositivas = [Diapositiva(n=1, tipo="portada", texto=g.titular.strip(), subtitulo=g.subtitulo.strip())]
    fuentes = []
    for i, x in enumerate(g.noticias, 2):
        diapositivas.append(Diapositiva(n=i, tipo="noticia", texto=x.titular.strip(), subtitulo=x.subtitulo.strip()))
        a = por_id[x.historia].articulos[0]
        fuentes.append(FuenteNoticia(medio=a.medio, titulo=a.titulo, url=a.url, acceso=a.acceso,
                                     publicado=a.publicado_en.date().isoformat() if a.publicado_en else None))
    guion = GuionLLM(idea_nueva_candidatas=[], idea_elegida="", por_que="Las cinco noticias del día del mundo del libro",
                     diapositivas=diapositivas, pie_instagram=g.pie_instagram.strip(), libros=[],
                     fuentes_noticia=[f"{f.medio} {f.url}" for f in fuentes])
    eleccion = HistoriaElegida(formato=FORMATO, historia_id=PREFIJO + fecha, titular=g.titular.strip(),
                               de_que_se_habla=" / ".join(x.titular for x in g.noticias),
                               cuestion_de_fondo="Lo más importante del día en el mundo del libro", libros_candidatos=[],
                               gancho_libro="", por_que="Prueba de «Cinco del libro» (2/11)")
    return Pieza(id=pieza_id, fecha=fecha, estado="propuesta", historia_id=PREFIJO + fecha, eleccion=eleccion,
                 n_medios=sum(por_id[x.historia].n_medios for x in g.noticias), guion=guion, fuentes=fuentes,
                 avisos=["Cinco del libro: prueba de formato (2/11)"],
                 arte=Arte(tono="luminoso", recurso="ilustracion", portada="sangre", remate=g.remate.strip(),
                           remates_noticias=[x.remate.strip() for x in g.noticias],
                           escenas_noticias=[x.escena.strip() for x in g.noticias]))


# --- Las ilustraciones ------------------------------------------------------------------------

def estilo(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "cinco_estilo.md").read_text(encoding="utf-8")
    m = re.search(r"^## estilo\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m or not m.group(1).strip():
        raise ValueError("prompts/cinco_estilo.md no tiene la sección «## estilo»")
    return m.group(1).strip()


def clave_imagen(pieza_id: str, i: int) -> str:
    return f"{pieza_id}{SUFIJO_IMAGEN}-{i}"


def _dibujar(cfg: Config, pieza_id: str, texto: str) -> Path:
    """Una ilustración vertical con Flux 2 Pro, en la caché común (la misma escena no se vuelve a pagar)."""
    import hashlib

    from folio.imagenes import magnific
    ie = cfg.pipeline.arte.ilustracion_editorial
    cache = cfg.dir_cache("x").parent / "ilustraciones" / f"cinco-{hashlib.sha256(texto.encode()).hexdigest()[:20]}.jpg"
    return magnific.imagen(cfg, ruta=magnific.FLUX_2_PRO, cuerpo={"prompt": texto, "width": ANCHO, "height": ALTO},
                           cache=cache, pieza_id=pieza_id, concepto="cinco", modelo="Flux 2 Pro", creditos=ie.creditos_imagen)


def _una(llm: LLM, cfg: Config, pieza: Pieza, i: int, intentos: int) -> str | None:
    from PIL import Image

    from folio.imagenes import editorial, libres
    from folio.imagenes import retrato_generado as rg
    texto = f"{pieza.arte.escenas_noticias[i - 1]} {estilo(cfg)}"
    descartes = []
    for _ in range(intentos):
        try:
            dibujo = _dibujar(cfg, pieza.id, texto)
        except rg.ErrorMagnific as exc:
            return f"noticia {i}: no se pudo dibujar ({exc})"
        motivo = editorial.revisar(llm, cfg, pieza.id, dibujo, manchas=False)   # en el collage, los bloques son el estilo
        if motivo is None:
            fecha_dir = cfg.dir_cache(pieza.fecha)
            carpeta = libres.dir_imagenes(fecha_dir)
            carpeta.mkdir(parents=True, exist_ok=True)
            clave = clave_imagen(pieza.id, i)
            (carpeta / f"{clave}.jpg").write_bytes(dibujo.read_bytes())
            with Image.open(dibujo) as im:
                ancho, alto = im.size
            libres.guardar_metadatos(libres.ImagenLibre(
                archivo="magnific:cinco", pagina="", url="", ancho=ancho, alto=alto, licencia="generada con IA (Magnific) para Folio",
                licencia_url=None, autor="Folio", descripcion=texto, libre=True, motivo="", local=f"{clave}.jpg", fuente=""),
                clave, fecha_dir)
            return None
        descartes.append(motivo)
    return f"noticia {i}: el revisor encontró letras ({' | '.join(descartes)})"


def ilustrar(llm: LLM, cfg: Config, pieza: Pieza, intentos: int = 2) -> list[str]:
    """Las cinco ilustraciones, a la vez. Devuelve los motivos de las que no salieron (esas noticias van tipográficas)."""
    with ThreadPoolExecutor(max_workers=N) as pool:
        motivos = list(pool.map(lambda i: _una(llm, cfg, pieza, i, intentos), range(1, len(pieza.arte.escenas_noticias) + 1)))
    if len(motivos) > sum(m is not None for m in motivos):
        pieza.arte.credito = "generadas con IA (Magnific) para Folio"
    return [m for m in motivos if m]


# --- Todo junto -------------------------------------------------------------------------------

def preparar(tuberia, historias: list[Historia], pieza_id: str, dibujar: bool = True,
             elegidas: list[str] | None = None) -> Pieza:
    """Escribe, ilustra y comprueba la pieza de «Cinco del libro». Si falla el guion, la pieza sale «fallida» con el
    motivo; las ilustraciones y la comprobación nunca la paran."""
    from folio import hechos
    cfg, llm, fecha = tuberia.cfg, tuberia.llm, tuberia.fecha
    try:
        g, avisos = escribir(llm, cfg, fecha, historias, elegidas)
    except ErrorLLM as exc:
        e = HistoriaElegida(formato=FORMATO, historia_id=PREFIJO + fecha, titular="Breves del libro", de_que_se_habla="",
                            cuestion_de_fondo="", libros_candidatos=[], por_que="")
        return Pieza(id=pieza_id, fecha=fecha, estado="fallida", historia_id=PREFIJO + fecha, eleccion=e, n_medios=0,
                     error=str(exc)[:400])
    pieza = a_pieza(g, pieza_id, fecha, historias)
    pieza.avisos += avisos
    if elegidas is not None:
        pieza.avisos.append(cambios_de_la_redaccion(cfg, fecha, elegidas, historias))
    if dibujar:
        for motivo in ilustrar(llm, cfg, pieza):
            pieza.avisos.append(f"Cinco del libro: sin ilustración en la {motivo}")
    guardar_escenas(cfg, fecha, pieza.arte.escenas_noticias)
    por_id = {h.id: h for h in historias}
    try:
        textos = [t for x in g.noticias for t in tuberia.textos_de_historia(por_id[x.historia])[:2]]
        pieza.hechos = hechos.comprobar(llm, pieza.id, pieza.guion, textos)
    except Exception as exc:                        # la comprobación nunca para la pieza
        pieza.avisos.append(f"No se pudo comprobar los hechos: {type(exc).__name__}: {exc}"[:300])
    return pieza


# --- La lista para elegir (5/11) -----------------------------------------------------------------

N_LISTA = 10                      # noticias que se proponen como mínimo, si hay material (hasta `cinco.propuestas`)
PREFIJO_CAMBIOS = "Cinco del libro: elección de la redacción"


class CandidataCinco(BaseModel):
    historia: str = Field(description="El id exacto de la noticia en la lista")
    titular: str = Field(description="En español, de 12 palabras como máximo, que diga qué ha pasado")
    por_que: str = Field(description="Una línea, de 8 a 25 palabras: por qué importa a un lector de Folio")


class ListaCinco(BaseModel):
    candidatas: list[CandidataCinco] = Field(description="Las noticias para elegir, de más a menos importante: las primeras son las que publicarías")
    publicar: int = Field(description="Cuántas de las primeras publicarías hoy: las que valgan, de 0 (hoy no hay ninguna que merezca el post) a 7")


class Candidata(BaseModel):
    """Una noticia de la lista, como la ve la web."""
    historia: str
    titular: str
    por_que: str
    medio: str = ""
    url: str = ""
    n_medios: int = 1
    marcada: bool = False         # preseleccionada por el jefe


class PropuestaCinco(BaseModel):
    fecha: str
    candidatas: list[Candidata]
    minimo: int = 3                       # cuántas puede llevar el post (5/11)
    maximo: int = N
    elegidas: list[str] | None = None     # lo que eligió la redacción al montar el post
    coste_usd: float = 0.0


def ruta_propuesta(cfg: Config, fecha: str) -> Path:
    return cfg.dir_cache(fecha) / "cinco_propuesta.json"


def cargar_propuesta(cfg: Config, fecha: str) -> PropuestaCinco | None:
    try:
        return PropuestaCinco.model_validate_json(ruta_propuesta(cfg, fecha).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def guardar_propuesta(cfg: Config, p: PropuestaCinco) -> None:
    guardar_json(ruta_propuesta(cfg, p.fecha), p.model_dump())


def validar_lista(lista: ListaCinco, ids: set[str], maximo: int = 15, publicar: tuple[int, int] = (0, N)) -> list[str]:
    errores = []
    # 6/11: «Rehacer la lista» falló en producción. Pocas noticias no es un error (mejor pocas que relleno); demasiadas,
    # sí. 7/11 («Breves del libro»): un día puede no haber ninguna que publicar
    if len(lista.candidatas) > maximo:
        errores.append(f"Como mucho {maximo} noticias (hay {len(lista.candidatas)}).")
    if not publicar[0] <= lista.publicar <= min(publicar[1], len(lista.candidatas)):
        errores.append(f"`publicar` tiene que ser de {publicar[0]} a {publicar[1]}, y no más que las noticias de la lista.")
    vistos = set()
    for i, c in enumerate(lista.candidatas, 1):
        if c.historia not in ids:
            errores.append(f"Noticia {i}: «{c.historia}» no es un id de la lista.")
        elif c.historia in vistos:
            errores.append(f"Noticia {i}: repite la historia {c.historia}.")
        vistos.add(c.historia)
        if _palabras(c.titular) > 12 or c.titular.strip().endswith("?"):
            errores.append(f"Noticia {i}: el titular tiene que tener 12 palabras como máximo y no ser una pregunta.")
    return errores


def proponer(llm: LLM, cfg: Config, fecha: str, historias: list[Historia]) -> PropuestaCinco:
    """La lista para elegir: unas diez noticias con su porqué y las cinco primeras marcadas. ErrorLLM si no hay noticias
    bastantes o si la lista no valida tras un reintento."""
    from folio.guion import linea_hoy
    lista = candidatas(historias)
    minimo, maximo = cuantas(cfg)
    tope = cfg.pipeline.cinco.propuestas
    if len(lista) < minimo:
        raise ErrorLLM(f"Breves del libro: solo hay {len(lista)} noticias del mundo del libro hoy")
    prompt = cargar_prompt(cfg, "cinco_propuesta", {"[pegar hoy]": linea_hoy(fecha), "[pegar noticias]": _bloque(lista),
                                                    "[pegar cuantas]": f"de {minimo} a {maximo}",
                                                    "[pegar propuestas]": f"de {min(N_LISTA, len(lista))} a {max(tope, min(N_LISTA, len(lista)))}"})
    mensajes = [{"role": "user", "content": prompt}]
    ids = {h.id for h in lista}
    errores: list[str] = []
    antes = len(llm.trazas)
    for intento in range(2):
        r, _ = llm.estructurado(f"cinco-propuesta:{fecha}:{intento + 1}", cache_al_final(mensajes, hasta=0), ListaCinco,
                                etapa_modelo="cinco_propuesta", max_tokens=8000)
        errores = validar_lista(r, ids, tope, (0, maximo))
        if not errores:
            por_id = {h.id: h for h in lista}
            out = []
            for i, c in enumerate(r.candidatas):
                h = por_id[c.historia]
                a = h.articulos[0] if h.articulos else None
                out.append(Candidata(historia=c.historia, titular=c.titular.strip(), por_que=c.por_que.strip(),
                                     medio=a.medio if a else "", url=a.url if a else "", n_medios=h.n_medios, marcada=i < r.publicar))
            coste = round(sum(t.coste_usd for t in llm.trazas[antes:]), 4)
            return PropuestaCinco(fecha=fecha, candidatas=out, coste_usd=coste, minimo=minimo, maximo=maximo)
        mensajes += [{"role": "assistant", "content": json.dumps(r.model_dump(), ensure_ascii=False)},
                     {"role": "user", "content": "No cumple estas condiciones:\n" + "\n".join(f"- {e}" for e in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    # Lo que se pueda salvar de la última respuesta: sin ids inventados ni repetidos, los titulares largos recortados
    vistos, buenas = set(), []
    for c in r.candidatas:
        if c.historia in ids and c.historia not in vistos:
            vistos.add(c.historia)
            buenas.append(c.model_copy(update={"titular": " ".join(c.titular.split()[:12])}))
    if buenas:
        por_id = {h.id: h for h in lista}
        publicar = max(0, min(r.publicar, maximo, len(buenas)))
        out = [Candidata(historia=c.historia, titular=c.titular.strip(), por_que=c.por_que.strip(),
                         medio=por_id[c.historia].articulos[0].medio if por_id[c.historia].articulos else "",
                         url=por_id[c.historia].articulos[0].url if por_id[c.historia].articulos else "",
                         n_medios=por_id[c.historia].n_medios, marcada=i < publicar) for i, c in enumerate(buenas[:tope])]
        return PropuestaCinco(fecha=fecha, candidatas=out, coste_usd=round(sum(t.coste_usd for t in llm.trazas[antes:]), 4),
                              minimo=minimo, maximo=maximo)
    raise ErrorLLM("Breves del libro: la lista no cumple las reglas tras un reintento (" + " | ".join(errores) + ")")


def cambios_de_la_redaccion(cfg: Config, fecha: str, elegidas: list[str], historias: list[Historia]) -> str:
    """Qué cambió la redacción respecto a las cinco del jefe (para los avisos de la pieza y la Memoria). Guarda la
    elección en la propuesta del día."""
    p = cargar_propuesta(cfg, fecha)
    titulares = {h.id: h.titular_es or h.id for h in historias}
    if p is None:
        return f"{PREFIJO_CAMBIOS}: sin lista del jefe"
    titulares.update({c.historia: c.titular for c in p.candidatas})
    jefe = [c.historia for c in p.candidatas if c.marcada]
    p.elegidas = list(elegidas)
    guardar_propuesta(cfg, p)
    quitadas = [titulares[i] for i in jefe if i not in elegidas]
    anadidas = [titulares.get(i, i) for i in elegidas if i not in jefe]
    if not quitadas and not anadidas:
        return f"{PREFIJO_CAMBIOS}: las cinco del jefe" + ("" if elegidas == jefe else ", en otro orden")
    return (f"{PREFIJO_CAMBIOS}: quitó " + ("; ".join(f"«{t}»" for t in quitadas) or "nada")
            + " y puso " + ("; ".join(f"«{t}»" for t in anadidas) or "nada"))


# --- Ampliar la lista con lo que leyó la madrugada (5/11) ----------------------------------------
# «¿Puedes permitir que lo pruebe hoy? Solo me deja seleccionar los 5 de hoy, a partir de los 7»: un día ya leído
# tiene resumidas pocas noticias del libro. Al rehacer la lista, se completa con los artículos en español del carril
# del libro que leyó la madrugada y no entraron en ninguna historia (uno por historia, con su titular y su entradilla;
# sin modelo), hasta `cinco.en_espanol`. Se guardan en `cinco_extra.json` para que el post las encuentre al montarse.

def _ruta_extra(cfg: Config, fecha: str) -> Path:
    return cfg.dir_cache(fecha) / "cinco_extra.json"


def _normal(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


def ampliar(cfg: Config, fecha: str, historias: list[Historia]) -> list[Historia]:
    """Historias de un artículo con las noticias del libro en español que no entraron (vacío si ya hay bastantes)."""
    from folio.etapas import EtapasGuardadas
    c = cfg.pipeline.cinco
    if len(candidatas(historias)) >= c.propuestas or not c.en_espanol:
        return []
    etapas = EtapasGuardadas(cfg.dir_cache(fecha))
    if not etapas.hay_articulos():
        return []
    usados = {a.id for h in historias for a in h.articulos}
    titulares = {_normal(h.titular_es or "") for h in historias} | {_normal(a.titulo) for h in historias for a in h.articulos}
    sueltos = [a for a in etapas.articulos() if a.carril == "editorial" and a.idioma == "es" and a.id not in usados
               and a.titulo.strip() and _normal(a.titulo) not in titulares]
    sueltos.sort(key=lambda a: a.publicado_en.timestamp() if a.publicado_en else 0, reverse=True)
    out, vistos = [], set()
    for a in sueltos:
        if _normal(a.titulo) in vistos:
            continue
        vistos.add(_normal(a.titulo))
        out.append(Historia(id=f"es-{a.id}"[:80], articulos=[a], medios=[a.medio], n_medios=1, ultima_publicacion=a.publicado_en,
                            titular_es=a.titulo.strip(), resumen_es=(a.entradilla or "").strip()[:400] or None, carril="radar"))
        if len(out) >= c.en_espanol:
            break
    return out


def con_extra(cfg: Config, fecha: str, historias: list[Historia], ampliar_ahora: bool = False) -> list[Historia]:
    """Las historias del día más las añadidas a la lista (`ampliar_ahora`: las busca y las guarda)."""
    ruta = _ruta_extra(cfg, fecha)
    if ampliar_ahora:
        extra = ampliar(cfg, fecha, historias)
        guardar_json(ruta, [h.model_dump(mode="json") for h in extra])
    else:
        try:
            extra = [Historia.model_validate(x) for x in json.loads(ruta.read_text(encoding="utf-8"))]
        except (OSError, ValueError):
            extra = []
    ya = {h.id for h in historias}
    return historias + [h for h in extra if h.id not in ya]
