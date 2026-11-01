"""Programar una pieza aprobada en Buffer (lo comparten `folio buffer programar` y el botón de la web, 2/11).

Prepara el carrusel de la versión actual (JPEG y, donde la haya, la diapositiva en vídeo), hace una copia estable
en informes/<fecha>/publicar/<pieza>-buffer/ (Buffer descarga los archivos al publicar, horas o días después) y
crea la publicación con enlaces firmados que valen hasta tres días después de la hora (treinta, en la cola).
`programada.json` deja constancia: una pieza programada no se vuelve a programar sin `reemplazar` (después de
borrar la publicación en Buffer).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from folio.modelos import Pieza
from folio.publicacion import enlaces
from folio.publicacion.buffer import Buffer
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


def carpeta_estable(cfg, fecha: str, pid: str) -> Path:
    return cfg.dir_informes / fecha / "publicar" / f"{pid}-buffer"


def estado(cfg, fecha: str, pid: str) -> dict | None:
    """Lo que se programó en Buffer para la pieza (programada.json), o None."""
    f = carpeta_estable(cfg, fecha, pid) / "programada.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def programar(cfg, p: Pieza, version: int, fecha: str, cuando: datetime | None, *, borrador: bool = False,
              reemplazar: bool = False, confirmar: bool = True, con_video: bool = True, videos_de: Path | None = None,
              buffer: Buffer | None = None) -> Programacion:
    """Programa la pieza (o, sin `confirmar`, solo la prepara). NoSePuede o ErrorBuffer si no se puede."""
    if p.estado != "aprobada":
        raise NoSePuede(f"La pieza está «{p.estado}»: solo se programan las aprobadas")
    if not (cfg.url_publica and cfg.clave_enlaces):
        raise NoSePuede("Faltan FOLIO_URL_PUBLICA o FOLIO_CLAVE_ENLACES: Buffer descarga las imágenes de la web")
    if cuando and cuando <= datetime.now(cuando.tzinfo) + timedelta(minutes=5):
        raise NoSePuede("La hora tiene que ser al menos dentro de cinco minutos")
    estable = carpeta_estable(cfg, fecha, p.id)
    previa = estado(cfg, fecha, p.id)
    # Desde un borrador se puede programar sin borrarlo antes (2/11, a petición del usuario: el botón «no funcionaba»):
    # un borrador no se publica solo; queda en Buffer y se avisa para que se borre allí
    if previa and previa.get("borrador") and not reemplazar:
        reemplazar = True
    if confirmar and previa and not reemplazar:
        raise NoSePuede("La pieza ya está programada en Buffer: sus archivos se descargan al publicar y no se pueden "
                        "cambiar. Borra antes esa publicación en Buffer y vuelve a programarla marcando «reemplazar».")
    b = buffer or Buffer(cfg.buffer_clave)
    lista = preparar(cfg, p, con_video=con_video, videos_de=videos_de)
    resultado = Programacion(pie=lista.pie, diapositivas=len(lista.medios),
                             videos=[i for i, (t, _) in enumerate(lista.medios, 1) if t == "video"],
                             hora=cuando, borrador=borrador, avisos=list(lista.avisos), carpeta=lista.carpeta)
    canal = b.canal_instagram(cfg.buffer_canal)
    resultado.canal = canal["name"]
    if not confirmar:
        return resultado
    # Copia propia y estable: la descarga del .zip e Instagram vuelven a preparar la carpeta de la pieza
    shutil.rmtree(estable, ignore_errors=True)
    shutil.copytree(lista.carpeta, estable)
    segundos = int((cuando - datetime.now(cuando.tzinfo)).total_seconds()) + 3 * 86400 if cuando else 30 * 86400
    medios = [(tipo, enlaces.firmar(cfg.url_publica, cfg.clave_enlaces, f"{fecha}/{p.id}-buffer/{archivo}", segundos))
              for tipo, archivo in lista.medios]
    resultado.post = b.programar(canal["id"], lista.pie, medios, cuando, borrador)
    if previa and previa.get("borrador"):
        resultado.avisos.append("El borrador anterior sigue en Buffer: bórralo allí para no tener dos")
    resultado.carpeta = estable
    (estable / "programada.json").write_text(json.dumps(
        {"buffer": resultado.post, "version": version, "hora": cuando.isoformat() if cuando else None,
         "borrador": borrador, "canal": canal["name"], "en": datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False), encoding="utf-8")
    return resultado
