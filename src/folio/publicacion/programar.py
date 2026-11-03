"""Programar una pieza aprobada en Buffer (lo comparten `folio buffer programar` y el botón de la web, 2/11).

Prepara el carrusel de la versión actual (JPEG y, donde la haya, la diapositiva en vídeo), hace una copia estable
en informes/<fecha>/publicar/<pieza>-buffer/ (Buffer descarga los archivos al publicar, horas o días después) y
crea la publicación con enlaces firmados que valen hasta tres días después de la hora (treinta, en la cola).
`programada.json` deja constancia: una pieza programada no se vuelve a programar sin `reemplazar` (después de
borrar la publicación en Buffer).
"""

from __future__ import annotations

import json
import os
import threading
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from folio.modelos import Pieza
from folio.publicacion import enlaces
from folio.publicacion.buffer import MAX_IMAGENES_LINKEDIN, NOMBRE_RED, REDES, Buffer
from folio.publicacion.preparar import preparar


class NoSePuede(Exception):
    """La pieza no se puede programar (no está aprobada, falta configuración, hora pasada, ya programada)."""


@dataclass
class Programacion:
    pie: str
    diapositivas: int
    videos: list[int]
    hora: datetime | None
    borrador: bool
    canal: str = ""
    post: dict | None = None             # None: solo preparada (prueba)
    posts: dict = field(default_factory=dict)   # por red («instagram», «linkedin»): el post de Buffer
    redes: list[str] = field(default_factory=lambda: ["instagram"])
    avisos: list[str] = field(default_factory=list)
    carpeta: Path | None = None


def hora_de_publicacion(texto: str, zona: str, ahora: datetime | None = None) -> datetime:
    """«2026-11-02 09:30» o «09:30» (la próxima vez que sea esa hora) en la zona de Folio. ValueError si no vale."""
    tz = ZoneInfo(zona)
    ahora = (ahora or datetime.now(tz)).astimezone(tz)
    try:
        if len(texto.strip()) <= 5:
            h, m = (int(x) for x in texto.strip().split(":"))
            cuando = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
            return cuando if cuando > ahora else cuando + timedelta(days=1)
        return datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError:
        raise ValueError(f"Hora no válida: «{texto}» (usa «AAAA-MM-DD HH:MM» o «HH:MM»)") from None


def texto_de_pieza(p: Pieza) -> str:
    """Lo que la memoria de lo publicado compara con las noticias de mañana: titular, de qué se habla y los titulares
    de sus fuentes (como los artículos: «titular. entradilla»)."""
    portada = p.guion.diapositivas[0].texto if p.guion and p.guion.diapositivas else p.eleccion.titular
    partes = [portada, p.eleccion.titular, p.eleccion.de_que_se_habla] + [f.titulo for f in p.fuentes[:4]]
    return ". ".join(x.strip() for x in dict.fromkeys(partes) if x and x.strip())[:700]


def recordar_publicada(cfg, p: Pieza, redes: list[str]) -> None:
    """Apunta la pieza en la memoria de lo publicado (3/11). Nunca hace fallar la programación."""
    try:
        from folio.historial import Historial
        hoy = datetime.now(ZoneInfo(os.getenv("FOLIO_ZONA") or "Europe/Madrid")).date().isoformat()
        Historial(cfg.ruta_db).anadir_publicada(hoy, p.id, p.eleccion.titular, texto_de_pieza(p), ",".join(redes))
    except Exception:
        pass


def recordar_programadas(cfg, almacen, dias: int = 7) -> int:
    """Pasa a la memoria de lo publicado lo programado en Buffer (no los borradores) en los últimos días, también lo de
    antes de que existiera (al arrancar la API). Devuelve cuántas piezas apuntó."""
    from datetime import date
    from folio.historial import Historial
    h, n = Historial(cfg.ruta_db), 0
    hoy = date.today()
    for d in range(dias + 1):
        fecha = (hoy - timedelta(days=d)).isoformat()
        carpeta = cfg.dir_informes / fecha / "publicar"
        if not carpeta.exists():
            continue
        for estable in carpeta.glob("*-buffer"):
            pid = estable.name.removesuffix("-buffer")
            redes = [r for r in REDES if (e := estado(cfg, fecha, pid, r)) and not e.get("borrador")]
            eid = almacen.ultima_ejecucion(fecha) if redes else None
            hallada = almacen.pieza(eid, pid) if eid else None
            if hallada:
                cuando = (estado(cfg, fecha, pid, redes[0]) or {}).get("en", fecha)[:10]
                h.anadir_publicada(cuando, pid, hallada[0].eleccion.titular, texto_de_pieza(hallada[0]), ",".join(redes))
                n += 1
    return n


def carpeta_estable(cfg, fecha: str, pid: str) -> Path:
    return cfg.dir_informes / fecha / "publicar" / f"{pid}-buffer"


def _archivo_estado(red: str) -> str:
    return "programada.json" if red == "instagram" else f"programada-{red}.json"


def estado(cfg, fecha: str, pid: str, red: str = "instagram") -> dict | None:
    """Lo que se programó en Buffer para la pieza en esa red (programada.json, programada-linkedin.json), o None."""
    f = carpeta_estable(cfg, fecha, pid) / _archivo_estado(red)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def programar(cfg, p: Pieza, version: int, fecha: str, cuando: datetime | None, *, borrador: bool = False,
              reemplazar: bool = False, confirmar: bool = True, con_video: bool = True, videos_de: Path | None = None,
              buffer: Buffer | None = None, redes: tuple[str, ...] | list[str] = ("instagram",)) -> Programacion:
    """Programa la pieza en las redes pedidas (Instagram y, desde el 3/11, LinkedIn), o, sin `confirmar`, solo la
    prepara. NoSePuede o ErrorBuffer si no se puede."""
    redes = [r for r in dict.fromkeys(redes) if r in REDES]
    if not redes:
        raise NoSePuede("Elige al menos una red: Instagram o LinkedIn")
    if p.estado != "aprobada":
        raise NoSePuede(f"La pieza está «{p.estado}»: solo se programan las aprobadas")
    if not (cfg.url_publica and cfg.clave_enlaces):
        raise NoSePuede("Faltan FOLIO_URL_PUBLICA o FOLIO_CLAVE_ENLACES: Buffer descarga las imágenes de la web")
    if cuando and cuando <= datetime.now(cuando.tzinfo) + timedelta(minutes=5):
        raise NoSePuede("La hora tiene que ser al menos dentro de cinco minutos")
    estable = carpeta_estable(cfg, fecha, p.id)
    previas = {r: estado(cfg, fecha, p.id, r) for r in redes}
    ya_borrada = reemplazar                       # lo marcó quien programa («Ya la he borrado»)
    # Desde un borrador se puede programar sin borrarlo antes (2/11, a petición del usuario: el botón «no funcionaba»):
    # un borrador no se publica solo; queda en Buffer y se avisa para que se borre allí
    for red, previa in previas.items():
        if confirmar and previa and not previa.get("borrador") and not reemplazar:
            raise NoSePuede(f"La pieza ya está programada en {NOMBRE_RED[red]}: sus archivos se descargan al publicar y no "
                            "se pueden cambiar. Borra antes esa publicación en Buffer y vuelve a programarla marcando "
                            "«reemplazar», o elige solo la otra red.")
    # Revisión general (2/11): si la preparación pasaba de 5 minutos, la web daba error, se volvía a pulsar y Buffer
    # recibía dos publicaciones. Se marca «en curso» antes de empezar; el segundo intento se rechaza.
    en_curso = estable.parent / f"{p.id}-buffer.en-curso"
    if confirmar and en_curso.exists() and not ya_borrada:
        raise NoSePuede("Ya se está programando esta pieza, o un intento anterior se cortó sin que conste si llegó a "
                        "Buffer. Espera a que acabe o, si no sigue en marcha, mira en Buffer: si está, no hagas nada; si "
                        "no, vuelve a programarla marcando «Ya la he borrado».")
    if confirmar:
        en_curso.parent.mkdir(parents=True, exist_ok=True)
        en_curso.write_text(datetime.now().astimezone().isoformat(timespec="seconds"), encoding="utf-8")
    try:
        return _programar(cfg, fecha, p, version, cuando, borrador, confirmar, con_video, videos_de, buffer, estable,
                          previas, en_curso, redes)
    except BaseException:
        if confirmar and not (estable / "programada.json").exists() and not getattr(_enviado, "si", False):
            en_curso.unlink(missing_ok=True)      # no llegó a Buffer: se puede reintentar sin más
        raise
    finally:
        _enviado.si = False


_enviado = threading.local()                     # ¿llegó ya a Buffer la publicación de este hilo?


def _programar(cfg, fecha, p, version, cuando, borrador, confirmar, con_video, videos_de, buffer, estable, previas,
               en_curso, redes) -> Programacion:
    from folio.publicacion.buffer import ErrorBuffer
    b = buffer or Buffer(cfg.buffer_clave)
    lista = preparar(cfg, p, con_video=con_video, videos_de=videos_de)
    resultado = Programacion(pie=lista.pie, diapositivas=len(lista.medios),
                             videos=[i for i, (t, _) in enumerate(lista.medios, 1) if t == "video"],
                             hora=cuando, borrador=borrador, avisos=list(lista.avisos), carpeta=lista.carpeta, redes=redes)
    canales = {r: b.canal_de(r, cfg.buffer_canal if r == "instagram" else cfg.buffer_canal_linkedin) for r in redes}
    resultado.canal = " y ".join(c["name"] for c in canales.values())
    if not confirmar:
        return resultado
    # Copia propia y estable: la descarga del .zip e Instagram vuelven a preparar la carpeta de la pieza
    # (sin borrar la carpeta: guarda lo programado en la otra red, programada*.json)
    estable.mkdir(parents=True, exist_ok=True)
    for f in lista.carpeta.iterdir():
        shutil.copy(f, estable / f.name)
    segundos = int((cuando - datetime.now(cuando.tzinfo)).total_seconds()) + 3 * 86400 if cuando else 30 * 86400

    def firmado(archivo: str) -> str:
        return enlaces.firmar(cfg.url_publica, cfg.clave_enlaces, f"{fecha}/{p.id}-buffer/{archivo}", segundos)

    fallos = []
    for red in redes:
        if red == "linkedin":
            # LinkedIn no mezcla vídeo e imágenes (3/11): todas las diapositivas en JPEG, como mucho nueve
            jpgs = [f"{n:02d}.jpg" for n in range(1, len(lista.medios) + 1)]
            if len(jpgs) > MAX_IMAGENES_LINKEDIN:
                resultado.avisos.append(f"LinkedIn admite {MAX_IMAGENES_LINKEDIN} imágenes: van las {MAX_IMAGENES_LINKEDIN} primeras")
            medios = [("imagen", firmado(a)) for a in jpgs[:MAX_IMAGENES_LINKEDIN]]
        else:
            medios = [(tipo, firmado(archivo)) for tipo, archivo in lista.medios]
        try:
            post = b.programar(canales[red]["id"], lista.pie, medios, cuando, borrador, red) if red != "instagram" \
                else b.programar(canales[red]["id"], lista.pie, medios, cuando, borrador)
        except ErrorBuffer as e:
            if not resultado.posts:
                raise
            fallos.append(f"{NOMBRE_RED[red]}: {e}")
            continue
        _enviado.si = True                        # ya está en Buffer: si algo falla después, el «en curso» se queda
        resultado.posts[red] = post
        if previas.get(red) and previas[red].get("borrador"):
            resultado.avisos.append(f"El borrador anterior de {NOMBRE_RED[red]} sigue en Buffer: bórralo allí para no tener dos")
        (estable / _archivo_estado(red)).write_text(json.dumps(
            {"buffer": post, "version": version, "hora": cuando.isoformat() if cuando else None,
             "borrador": borrador, "canal": canales[red]["name"], "red": red,
             "en": datetime.now().astimezone().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    if resultado.posts and not borrador:
        recordar_publicada(cfg, p, list(resultado.posts))
    for f in fallos:
        resultado.avisos.append(f"No se pudo programar en {f}. Lo demás sí está en Buffer: vuelve a programar solo esa red.")
    resultado.post = next(iter(resultado.posts.values()), None)
    resultado.carpeta = estable
    en_curso.unlink(missing_ok=True)              # lo que llegó a Buffer consta en programada*.json
    return resultado
