"""Lectura periódica de las noticias (2/11, a petición del usuario: «¿un agente que siempre esté buscando
noticias solucionaría algo?»).

No es un agente ni gasta: cada `FOLIO_LECTURA_CADA` minutos (la API lo lanza, folio_api.programador) se descargan
los RSS y se guarda cada artículo con la hora en que Folio lo vio por primera vez (data/lecturas.json). Sirve para
dos cosas:
- la ejecución de madrugada junta esos artículos con los del momento: no se pierden los que ya han salido del RSS;
- el jefe de cultura sabe desde cuándo circula de verdad una historia (`Articulo.visto_en`), que es lo que necesita
  la regla de no tratar en caliente un suceso doloroso.
Sin embeddings: no carga el modelo (4 GB) a deshoras ni compite con «Proceder».
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from folio.ingesta import rss
from folio.modelos import Articulo


def ruta(cfg):
    return cfg.dir_datos / "lecturas.json"


def _cargar(cfg) -> dict[str, dict]:
    try:
        return json.loads(ruta(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ventana(cfg) -> timedelta:
    i = cfg.pipeline.ingesta
    return timedelta(hours=max(i.ventana_horas, i.ventana_horas_editorial))


def leer(cfg, ahora: datetime | None = None) -> tuple[int, int, list[str]]:
    """Descarga los RSS y guarda lo nuevo. Devuelve (nuevos, guardados en total, feeds fallidos)."""
    ahora = ahora or datetime.now(timezone.utc)
    articulos, errores = rss.ingerir(cfg, ahora)
    guardados = _cargar(cfg)
    nuevos = 0
    for a in articulos:
        if a.id not in guardados:
            guardados[a.id] = a.model_copy(update={"visto_en": ahora}).model_dump(mode="json")
            nuevos += 1
    limite = ahora - _ventana(cfg)
    guardados = {k: v for k, v in guardados.items() if datetime.fromisoformat(v["visto_en"]) >= limite}
    ruta(cfg).parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: la madrugada lo lee (juntar) y, a medio escribir, lo daba por vacío sin avisar (ronda 3)
    tmp = ruta(cfg).with_name(f".lecturas.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(guardados, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta(cfg))
    return nuevos, len(guardados), errores


def juntar(cfg, articulos: list[Articulo], ahora: datetime | None = None) -> list[Articulo]:
    """Los artículos del RSS de ahora con su hora de primera lectura, y los leídos antes que ya no salen en el RSS
    (dentro de la ventana de su carril)."""
    ahora = ahora or datetime.now(timezone.utc)
    guardados = _cargar(cfg)
    if not guardados:
        return articulos
    i = cfg.pipeline.ingesta
    limites = {"actualidad": ahora - timedelta(hours=i.ventana_horas), "editorial": ahora - timedelta(hours=i.ventana_horas_editorial)}
    salida, vistos_url = [], set()
    for a in articulos:
        g = guardados.get(a.id)
        salida.append(a.model_copy(update={"visto_en": datetime.fromisoformat(g["visto_en"])}) if g else a)
        vistos_url.add(a.url)
    for g in guardados.values():
        a = Articulo.model_validate(g)
        cuando = a.publicado_en or a.visto_en
        if a.url in vistos_url or a.carril not in limites or (cuando and cuando < limites[a.carril]):
            continue
        salida.append(a)
        vistos_url.add(a.url)
    return salida


def embeber(cfg) -> tuple[int, int]:
    """Los embeddings de los artículos guardados que aún no los tienen, en la caché común (2/11, a petición del
    usuario: agilizar la madrugada). Gratis (CPU), pero carga el modelo (~2 GB): solo si hay artículos nuevos. Quita
    de la caché los que ya salieron de la ventana. Devuelve (calculados, en la caché)."""
    from folio.ingesta import agrupacion
    guardados = _cargar(cfg)
    emb = agrupacion.Embedder(cfg.pipeline.agrupacion.modelo_embeddings, agrupacion.dir_comun(cfg))
    ya = set(emb._leer())
    textos = {k: agrupacion.texto_articulo(Articulo.model_validate(v)) for k, v in guardados.items() if k not in ya}
    if textos:
        emb.vectores(textos)
    return len(textos), emb.podar(set(guardados))
