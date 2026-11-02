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
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from folio.config import Config
from folio.llm import LLM, ErrorLLM, cache_al_final, cargar_prompt
from folio.modelos import Arte, Diapositiva, FuenteNoticia, GuionLLM, Historia, HistoriaElegida, Pieza

FORMATO = "cinco"
PREFIJO = "cinco-"
SUFIJO_IMAGEN = "-cinco"          # <pieza>-cinco-1.jpg … <pieza>-cinco-5.jpg
N = 5
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
    noticias: list[NoticiaCinco] = Field(description="Las cinco noticias, de más a menos importante")
    pie_instagram: str = Field(description="De 80 a 150 palabras")


def _palabras(t: str) -> int:
    return len(t.split())


def _remate_valido(titular: str, remate: str) -> bool:
    t, r = titular.strip().rstrip(".").strip(), remate.strip().rstrip(".").strip()
    return bool(r) and 2 <= _palabras(r) <= 5 and t.endswith(r)


def validar(g: GuionCinco, ids: set[str]) -> list[str]:
    """Los errores del guion de «Cinco del libro» (lista vacía si vale)."""
    from folio.imagenes.editorial import validar_escena
    errores = []
    if _palabras(g.titular) > 12 or g.titular.strip().endswith("?"):
        errores.append("El titular de portada tiene que tener 12 palabras como máximo y no ser una pregunta.")
    if not 10 <= _palabras(g.subtitulo) <= 22:
        errores.append(f"El subtítulo de portada tiene que tener de 10 a 22 palabras (tiene {_palabras(g.subtitulo)}).")
    if not _remate_valido(g.titular, g.remate):
        errores.append("El remate de portada tiene que ser el final literal del titular, de 2 a 5 palabras.")
    if len(g.noticias) != N:
        errores.append(f"Tienen que ser exactamente {N} noticias (hay {len(g.noticias)}).")
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
    return [h for h in historias if h.carril in CARRILES and h.titular_es]


def _bloque(historias: list[Historia]) -> str:
    def linea(h: Historia) -> str:
        desde = min((a.publicado_en for a in h.articulos if a.publicado_en), default=None)
        return (f"- [{h.id}] {h.n_medios} medio{'s' if h.n_medios != 1 else ''} ({', '.join(h.medios[:4])})"
                + (f", desde el {desde.date().isoformat()}" if desde else "") + f": {h.titular_es}. {h.resumen_es or ''}")
    return "<noticias>\n" + "\n".join(linea(h) for h in historias) + "\n</noticias>"


def escribir(llm: LLM, cfg: Config, fecha: str, historias: list[Historia]) -> tuple[GuionCinco, list[str]]:
    """El guion de «Cinco del libro». ErrorLLM si no hay noticias bastantes o si no valida tras un reintento."""
    from folio.guion import linea_hoy
    lista = candidatas(historias)
    if len(lista) < N:
        raise ErrorLLM(f"Cinco del libro: solo hay {len(lista)} noticias del mundo del libro hoy")
    usadas = escenas_recientes(cfg, fecha)
    prompt = cargar_prompt(cfg, "cinco", {"[pegar hoy]": linea_hoy(fecha), "[pegar noticias]": _bloque(lista),
                                          "[pegar objetos]": "\n".join(f"- {e}" for e in usadas) or "(ninguna)"})
    mensajes = [{"role": "user", "content": prompt}]
    ids = {h.id for h in lista}
    avisos = []
    errores: list[str] = []
    for intento in range(2):
        g, _ = llm.estructurado(f"cinco:{fecha}:{intento + 1}", cache_al_final(mensajes, hasta=0), GuionCinco,
                                etapa_modelo="cinco", max_tokens=16000)
        errores = validar(g, ids)
        if not errores:
            return g, avisos
        avisos.append(f"Cinco del libro: rechazado en el intento {intento + 1}: " + " | ".join(errores))
        mensajes += [{"role": "assistant", "content": json.dumps(g.model_dump(), ensure_ascii=False)},
                     {"role": "user", "content": "No cumple estas condiciones:\n" + "\n".join(f"- {e}" for e in errores)
                      + "\nCorrígelo y devuelve el JSON completo."}]
    raise ErrorLLM("Cinco del libro: el guion no cumple las reglas tras un reintento (" + " | ".join(errores) + ")")


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
    import time

    import httpx

    from folio import gastos
    from folio.imagenes import retrato_generado as rg
    if rg.bloqueado():
        raise rg.ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise rg.ErrorMagnific("Falta MAGNIFIC_API_KEY")
    ie = cfg.pipeline.arte.ilustracion_editorial
    cache = cfg.dir_cache("x").parent / "ilustraciones" / f"cinco-{hashlib.sha256(texto.encode()).hexdigest()[:20]}.jpg"
    if cache.exists():
        return cache
    ruta = "/v1/ai/text-to-image/flux-2-pro"
    try:
        with httpx.Client(timeout=60) as c:
            tarea = rg._api(c, cfg.magnific_api_key, "POST", ruta, json={"prompt": texto, "width": ANCHO, "height": ALTO})
            gastos.imagen_magnific(cfg, "cinco", pieza_id, ie.creditos_imagen, "Flux 2 Pro")
            t0 = time.monotonic()
            while tarea.get("status") not in ("COMPLETED", "FAILED"):
                if time.monotonic() - t0 > ie.espera_max_s:
                    raise rg.ErrorMagnific(f"La tarea {tarea.get('task_id')} no terminó a tiempo")
                time.sleep(rg.ESPERA_S)
                tarea = rg._api(c, cfg.magnific_api_key, "GET", f"{ruta}/{tarea['task_id']}")
            if tarea["status"] == "FAILED" or not tarea.get("generated"):
                raise rg.ErrorMagnific("La tarea de Magnific falló")
            r = c.get(tarea["generated"][0])
            r.raise_for_status()
    except rg.ErrorMagnific as e:
        if e.bloqueo:
            rg._bloqueo = str(e)
        raise
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(r.content)
    return cache


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

def preparar(tuberia, historias: list[Historia], pieza_id: str, dibujar: bool = True) -> Pieza:
    """Escribe, ilustra y comprueba la pieza de «Cinco del libro». Si falla el guion, la pieza sale «fallida» con el
    motivo; las ilustraciones y la comprobación nunca la paran."""
    from folio import hechos
    cfg, llm, fecha = tuberia.cfg, tuberia.llm, tuberia.fecha
    try:
        g, avisos = escribir(llm, cfg, fecha, historias)
    except ErrorLLM as exc:
        e = HistoriaElegida(formato=FORMATO, historia_id=PREFIJO + fecha, titular="Cinco del libro", de_que_se_habla="",
                            cuestion_de_fondo="", libros_candidatos=[], por_que="")
        return Pieza(id=pieza_id, fecha=fecha, estado="fallida", historia_id=PREFIJO + fecha, eleccion=e, n_medios=0,
                     error=str(exc)[:400])
    pieza = a_pieza(g, pieza_id, fecha, historias)
    pieza.avisos += avisos
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
