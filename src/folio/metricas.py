"""Las métricas de Instagram de lo publicado (6/11, punto 6 del libro de estilo vivo: «la segunda señal: el público»).

Una vez al día (`folio leer`, o `folio metricas`), para las piezas publicadas en los últimos `DIAS` días: se buscan sus
publicaciones en la cuenta de Folio (`/me/media`, emparejadas por el principio del pie) y se guardan sus métricas
(alcance, guardados, compartidos, me gusta, comentarios e interacciones; tabla `metricas`, una medida por pieza y día).
La Memoria las recibe con el feedback de cada pieza y la web las enseña en el Archivo.

Necesita INSTAGRAM_TOKEN con el permiso `instagram_business_manage_insights` (además de los de publicar). Sin token, no
hace nada; ante 403, 429, límite o token caducado, para sin reintentar (regla del usuario).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

from folio.almacen import Almacen, Metrica
from folio.config import Config
from folio.publicacion.instagram import ErrorInstagram, Instagram
from folio.verificacion_texto import normalizar

DIAS = 30                  # se siguen midiendo las piezas publicadas en este tiempo
METRICAS = ("reach", "saved", "shares", "likes", "comments", "total_interactions")
CAMPO = {"reach": "alcance", "saved": "guardados", "shares": "compartidos", "likes": "me_gusta", "comments": "comentarios",
         "total_interactions": "interacciones"}
PALABRAS_PARA_CASAR = 14   # el principio del pie que tiene que estar en el de la publicación


def _principio(texto: str) -> str:
    return " ".join(normalizar(texto).split()[:PALABRAS_PARA_CASAR])


def casar(publicaciones: list[dict], piezas: dict[str, str]) -> dict[str, dict]:
    """{pieza: publicación} emparejando por el principio del pie (`piezas`: {pieza: pie}). Cada publicación, una vez."""
    out, usadas = {}, set()
    for pid, pie in piezas.items():
        clave = _principio(pie)
        if len(clave.split()) < 6:
            continue
        for m in publicaciones:
            if m["id"] in usadas:
                continue
            if normalizar(m.get("caption") or "").startswith(clave):
                out[pid] = m
                usadas.add(m["id"])
                break
    return out


def publicaciones(ig: Instagram, limite: int = 50) -> list[dict]:
    datos = ig._llamar("GET", f"{ig.usuario}/media", fields="id,caption,timestamp,permalink,media_type", limit=str(limite))
    return datos.get("data") or []


def medidas(ig: Instagram, media_id: str) -> dict[str, int]:
    datos = ig._llamar("GET", f"{media_id}/insights", metric=",".join(METRICAS))
    out = {}
    for fila in datos.get("data") or []:
        valores = fila.get("values") or [{}]
        valor = fila.get("total_value", {}).get("value") if fila.get("total_value") else valores[0].get("value")
        if fila.get("name") in CAMPO and isinstance(valor, (int, float)):
            out[CAMPO[fila["name"]]] = int(valor)
    return out


def medir(cfg: Config, almacen: Almacen, hoy: date | None = None, ig: Instagram | None = None) -> tuple[int, list[str]]:
    """Mide las piezas publicadas en los últimos DIAS días. Devuelve (medidas guardadas, avisos). Nunca lanza."""
    from folio.historial import Historial
    hoy = hoy or date.today()
    if ig is None:
        token = os.getenv("INSTAGRAM_TOKEN")
        if not token:
            return 0, ["Métricas: sin INSTAGRAM_TOKEN, no se miden"]
        ig = Instagram(token, os.getenv("INSTAGRAM_USER_ID") or None)
    publicadas = Historial(cfg.ruta_db).publicadas_recientes(hoy.isoformat(), DIAS)
    if not publicadas:
        return 0, ["Métricas: nada publicado en los últimos 30 días"]
    ultimas = {p.id: p for _f, _e, p, _v, _t in almacen.archivo()}
    pies = {pid: ultimas[pid].guion.pie_instagram for pid, *_ in publicadas if pid in ultimas and ultimas[pid].guion}
    try:
        casadas = casar(publicaciones(ig), pies)
    except ErrorInstagram as exc:
        return 0, [f"Métricas: {exc}" + (" (se para sin reintentar)" if exc.bloqueo else "")]
    n, avisos = 0, []
    if len(casadas) < len(pies):
        avisos.append(f"Métricas: {len(pies) - len(casadas)} piezas publicadas sin encontrar en Instagram (¿solo en LinkedIn, "
                      "o el pie se cambió en Instagram?)")
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for pid, m in casadas.items():
        try:
            valores = medidas(ig, m["id"])
        except ErrorInstagram as exc:
            avisos.append(f"Métricas de {pid}: {exc}")
            if exc.bloqueo or "permission" in str(exc).lower() or "(código 10)" in str(exc):
                avisos.append("Métricas: se para (sin permiso instagram_business_manage_insights, límite o bloqueo)")
                break
            continue
        almacen.guardar_metrica(Metrica(pieza_id=pid, dia=hoy.isoformat(), medido_en=ahora, media_id=m["id"],
                                        permalink=m.get("permalink") or "", publicado_en=(m.get("timestamp") or "")[:19],
                                        **valores))
        n += 1
    return n, avisos


def intento_hoy(cfg: Config, hoy: date | None = None) -> bool:
    """¿Se midió ya hoy? (la lectura periódica pasa cada dos horas: una vez al día basta). Marca el intento."""
    hoy = (hoy or date.today()).isoformat()
    ruta = cfg.dir_datos / "metricas_intento.txt"
    if ruta.exists() and ruta.read_text(encoding="utf-8").strip() == hoy:
        return True
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(hoy, encoding="utf-8")
    return False


def bloque_memoria(almacen: Almacen, piezas: list[str]) -> dict[str, str]:
    """{pieza: «alcance 1.234 · guardados 56 · compartidos 12»} para el feedback de la Memoria."""
    m = almacen.metricas()
    out = {}
    for pid in piezas:
        x = m.get(pid)
        if x:
            out[pid] = " · ".join(f"{k} {getattr(x, k)}" for k in ("alcance", "guardados", "compartidos", "me_gusta", "comentarios")
                                  if getattr(x, k) is not None)
    return out
