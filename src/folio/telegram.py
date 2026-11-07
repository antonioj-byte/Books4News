"""El informe del libro por Telegram (7/11, a petición del usuario: «tengo un repositorio que es un bot de Telegram
que uso para las noticias literarias… mira a ver si se puede integrar, porque toda la parte de selección de noticias
y búsqueda ya está montado aquí»).

Fase 1: Folio manda cada mañana, al acabar la ejecución del día, lo que ya ha seleccionado: la lista de «Cinco del
libro» (las noticias del mundo del libro, con titular en español, por qué importa, medio y enlace; primero las que
publicaría el jefe), los breves del radar y la mesa del día con su enlace a la web. Sustituye al informe de las 6:00
de publishing-monitor, que lee los mismos medios.

Se activa con TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (los mismos del bot); sin ellos no hace nada. Una vez al día
(`data/telegram_enviado.txt`). Ante 401, 403 o 429, para sin reintentar (regla del usuario). El token nunca sale en
los mensajes de error.
"""

from __future__ import annotations

import html
import json
import os
from datetime import date

import httpx

from folio.config import Config

LIMITE = 4000                  # Telegram corta a 4.096 caracteres por mensaje
API = "https://api.telegram.org/bot{token}/sendMessage"
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


class ErrorTelegram(RuntimeError):
    """Un fallo al enviar; `bloqueo` si Telegram dijo que no (401/403/429): no se reintenta."""

    def __init__(self, mensaje: str, bloqueo: bool = False):
        super().__init__(mensaje)
        self.bloqueo = bloqueo


def credenciales() -> tuple[str, str] | None:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return (token, chat) if token and chat else None


def _e(texto: str) -> str:
    return html.escape(texto or "", quote=False)


def _fecha_larga(fecha: str) -> str:
    d = date.fromisoformat(fecha)
    return f"{d.day} de {MESES[d.month - 1]}"


def _radar(cfg: Config, fecha: str) -> list[dict]:
    ruta = cfg.dir_cache(fecha) / "radar.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return datos if isinstance(datos, list) else datos.get("temas", []) if isinstance(datos, dict) else []


def informe(cfg: Config, fecha: str) -> str:
    """El informe del día en HTML de Telegram, con lo que Folio ya seleccionó. Vacío si no hay nada."""
    from folio import cinco
    from folio.almacen import Almacen
    partes: list[str] = []
    propuesta = cinco.cargar_propuesta(cfg, fecha)
    if propuesta and propuesta.candidatas:
        def linea(c) -> str:
            medios = f" · {c.n_medios} medios" if c.n_medios > 1 else ""
            enlace = f'<a href="{_e(c.url)}">{_e(c.medio or "Leer")}</a>' if c.url else _e(c.medio)
            return f"<b>{_e(c.titular)}</b>\n{_e(c.por_que)}\n🔗 {enlace}{medios}"
        marcadas = [c for c in propuesta.candidatas if c.marcada]
        resto = [c for c in propuesta.candidatas if not c.marcada]
        if marcadas:
            partes.append("⭐ <b>Lo más importante</b>\n\n" + "\n\n".join(linea(c) for c in marcadas))
        if resto:
            partes.append("📰 <b>También</b>\n\n" + "\n\n".join(linea(c) for c in resto))
    ya = {c.historia for c in propuesta.candidatas} if propuesta else set()
    breves = [b for b in _radar(cfg, fecha) if isinstance(b, dict) and b.get("titular") and b.get("historia_id") not in ya]
    if breves:
        partes.append("📡 <b>Breves del radar</b>\n\n" + "\n".join(f"· {_e(b['titular'])}" for b in breves[:8]))
    almacen = Almacen(cfg.ruta_db)
    eid = almacen.ultima_ejecucion(fecha)
    if eid:
        piezas = [p for p, _v in almacen.piezas(eid) if p.estado not in ("descartada", "fallida") and not p.radar]
        if piezas:
            base = (cfg.url_publica or "").rstrip("/")
            lineas = [(f'· <a href="{_e(base)}/pieza/{eid}/{_e(p.id)}">{_e(p.eleccion.titular)}</a>' if base
                       else f"· {_e(p.eleccion.titular)}") + (" (por escribir)" if p.estado == "pendiente" else "")
                      for p in piezas]
            partes.append("🗂 <b>La mesa de Folio</b>\n\n" + "\n".join(lineas))
    if not partes:
        return ""
    return f"📚 <b>Folio · el libro hoy, {_fecha_larga(fecha)}</b>\n\n" + "\n\n".join(partes)


def trocear(texto: str, limite: int = LIMITE) -> list[str]:
    """En mensajes de como mucho `limite` caracteres, cortando por párrafos (nunca dentro de una etiqueta)."""
    trozos, actual = [], ""
    for parrafo in texto.split("\n\n"):
        candidato = f"{actual}\n\n{parrafo}" if actual else parrafo
        if len(candidato) <= limite:
            actual = candidato
            continue
        if actual:
            trozos.append(actual)
        while len(parrafo) > limite:                 # un párrafo enorme: por líneas
            corte = parrafo.rfind("\n", 0, limite)
            corte = corte if corte > 0 else limite
            trozos.append(parrafo[:corte])
            parrafo = parrafo[corte:].lstrip("\n")
        actual = parrafo
    if actual:
        trozos.append(actual)
    return trozos


def enviar(texto: str, cliente: httpx.Client | None = None) -> int:
    """Manda el texto (troceado) al chat. Devuelve cuántos mensajes salieron."""
    cred = credenciales()
    if not cred:
        raise ErrorTelegram("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
    token, chat = cred
    propio = cliente is None
    cliente = cliente or httpx.Client(timeout=20)
    n = 0
    try:
        for trozo in trocear(texto):
            try:
                r = cliente.post(API.format(token=token), json={"chat_id": chat, "text": trozo, "parse_mode": "HTML",
                                                                 "disable_web_page_preview": True})
            except httpx.HTTPError as exc:
                raise ErrorTelegram(f"Telegram no respondió ({type(exc).__name__})") from None
            if r.status_code in (401, 403, 429):
                raise ErrorTelegram(f"Telegram respondió {r.status_code}; se para sin reintentar", bloqueo=True)
            if r.status_code >= 400:
                desc = ""
                try:
                    desc = r.json().get("description", "")
                except ValueError:
                    pass
                raise ErrorTelegram(f"Telegram respondió {r.status_code}: {desc}".replace(token, "***"))
            n += 1
    finally:
        if propio:
            cliente.close()
    return n


def _marca(cfg: Config):
    return cfg.dir_datos / "telegram_enviado.txt"


def ya_enviado(cfg: Config, fecha: str) -> bool:
    try:
        return _marca(cfg).read_text(encoding="utf-8").strip() == fecha
    except OSError:
        return False


def enviar_informe(cfg: Config, fecha: str, forzar: bool = False, cliente: httpx.Client | None = None) -> str:
    """El informe del día, una vez. Devuelve lo que pasó, en una frase. Nunca lanza."""
    if not credenciales():
        return "Telegram: sin TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID, no se envía"
    if ya_enviado(cfg, fecha) and not forzar:
        return f"Telegram: el informe del {fecha} ya salió"
    texto = informe(cfg, fecha)
    if not texto:
        return f"Telegram: nada que contar el {fecha}"
    try:
        n = enviar(texto, cliente)
    except ErrorTelegram as exc:
        return f"Telegram: {exc}"
    _marca(cfg).parent.mkdir(parents=True, exist_ok=True)
    _marca(cfg).write_text(fecha, encoding="utf-8")
    return f"Telegram: informe del {fecha} enviado ({n} mensaje{'s' if n > 1 else ''})"
