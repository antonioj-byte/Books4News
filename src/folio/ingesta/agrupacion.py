"""Embeddings y agrupación de artículos por evento."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from folio.modelos import Articulo, Historia

log = logging.getLogger(__name__)


class Embedder:
    """Envoltorio de fastembed con caché en disco por id de artículo."""

    def __init__(self, modelo: str, dir_cache: Path):
        self.modelo = modelo
        self.dir_cache = dir_cache
        self._motor = None

    def _cargar(self):
        if self._motor is None:
            from fastembed import TextEmbedding
            log.info("Cargando modelo de embeddings %s (la primera vez se descarga)", self.modelo)
            self._motor = TextEmbedding(self.modelo, cache_dir=str(self.dir_cache.parent / "modelos"))
        return self._motor

    def _prefijo(self, texto: str) -> str:
        # Los modelos e5 esperan prefijo; "query: " para comparaciones simétricas.
        return f"query: {texto}" if "e5" in self.modelo.lower() else texto

    def vectores(self, textos: dict[str, str]) -> dict[str, np.ndarray]:
        """textos: id -> texto. Devuelve id -> vector normalizado."""
        self.dir_cache.mkdir(parents=True, exist_ok=True)
        clave_modelo = hashlib.sha1(self.modelo.encode()).hexdigest()[:8]
        ruta = self.dir_cache / f"embeddings_{clave_modelo}.npz"
        cache: dict[str, np.ndarray] = dict(np.load(ruta)) if ruta.exists() else {}
        faltan = [i for i in textos if i not in cache]
        if faltan:
            motor = self._cargar()
            nuevos = list(motor.embed([self._prefijo(textos[i]) for i in faltan], batch_size=32))
            for i, v in zip(faltan, nuevos):
                cache[i] = np.asarray(v, dtype=np.float32)
            np.savez(ruta, **cache)
        out = {}
        for i in textos:
            v = cache[i]
            out[i] = v / (np.linalg.norm(v) or 1.0)
        return out


def texto_articulo(a: Articulo) -> str:
    return f"{a.titulo}. {a.entradilla}"[:700]


def agrupar(
    articulos: list[Articulo],
    vectores: dict[str, np.ndarray],
    umbral_similitud: float,
    umbral_fusion: float | None = None,
) -> list[Historia]:
    """Agrupación aglomerativa (enlace medio, distancia coseno) con umbral fijo.

    Si se da `umbral_fusion`, una segunda pasada fusiona los grupos cuyos centroides superan
    ese coseno: un mismo evento grande (crónica, análisis, víctimas, política) sale partido
    en la primera.

    Devuelve historias ordenadas por relevancia: medios distintos, luego nº de artículos,
    luego la publicación más reciente.
    """
    if not articulos:
        return []
    if len(articulos) == 1:
        etiquetas = np.array([0])
    else:
        X = np.stack([vectores[a.id] for a in articulos])
        modelo = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=1.0 - umbral_similitud,
        )
        etiquetas = modelo.fit_predict(X)

    grupos: dict[int, list[Articulo]] = {}
    for a, e in zip(articulos, etiquetas):
        grupos.setdefault(int(e), []).append(a)

    lista = list(grupos.values())
    if umbral_fusion is not None:
        lista = fusionar(lista, vectores, umbral_fusion)

    historias = []
    for miembros in lista:
        medios = sorted({a.medio for a in miembros})
        fechas = [a.publicado_en for a in miembros if a.publicado_en]
        ids = sorted(a.id for a in miembros)
        historias.append(Historia(
            id="h" + hashlib.sha1("".join(ids).encode()).hexdigest()[:8],
            articulos=sorted(miembros, key=lambda a: a.publicado_en or 0, reverse=True)
            if all(a.publicado_en for a in miembros) else miembros,
            medios=medios,
            n_medios=len(medios),
            ultima_publicacion=max(fechas) if fechas else None,
        ))
    historias.sort(
        key=lambda h: (h.n_medios, len(h.articulos), h.ultima_publicacion.timestamp() if h.ultima_publicacion else 0),
        reverse=True,
    )
    return historias


def _centroide(articulos: list[Articulo], vectores: dict[str, np.ndarray]) -> np.ndarray:
    v = np.mean([vectores[a.id] for a in articulos], axis=0)
    return v / (np.linalg.norm(v) or 1.0)


def fusionar(grupos: list[list[Articulo]], vectores: dict[str, np.ndarray], umbral: float) -> list[list[Articulo]]:
    """Fusiona de dos en dos los grupos con centroides más parecidos mientras superen `umbral`."""
    grupos = [list(g) for g in grupos]
    while len(grupos) > 1:
        C = np.stack([_centroide(g, vectores) for g in grupos])
        S = C @ C.T
        np.fill_diagonal(S, -1.0)
        i, j = np.unravel_index(int(np.argmax(S)), S.shape)
        if S[i, j] < umbral:
            break
        grupos[i] += grupos[j]
        del grupos[j]
    return grupos


def centroide(historia: Historia, vectores: dict[str, np.ndarray]) -> np.ndarray:
    return _centroide(historia.articulos, vectores)
