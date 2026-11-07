"""Proyectos en disco: `data/proyectos/<id>/proyecto.json` y sus archivos (el libro original y troceado, y más
adelante audio, imágenes y salidas). Escritura atómica y un cerrojo por proyecto, porque los trabajos corren en hilos.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from videos import fuente
from videos import libro as lib
from videos.config import Config
from videos.llm import Uso
from videos.modelos import Gasto, LibroInfo, Proyecto, ahora

PEGADO = "__texto_pegado__.txt"
_cerrojos: dict[str, threading.RLock] = {}
_cerrojo_global = threading.Lock()


def _cerrojo(pid: str) -> threading.RLock:
    with _cerrojo_global:
        return _cerrojos.setdefault(pid, threading.RLock())


def _slug(texto: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:48] or "libro"


def carpeta(cfg: Config, pid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", pid):
        raise ValueError("Identificador de proyecto no válido")
    return cfg.proyectos / pid


def crear(cfg: Config, nombre_archivo: str, contenido: bytes, titulo: str = "", autor: str = "",
          tipo: str = "libro") -> Proyecto:
    """Un proyecto a partir de la fuente: un archivo (EPUB, PDF, TXT o una nota de voz) o un texto pegado (se pasa
    como `texto.txt` con su contenido)."""
    from videos import transcripcion
    if tipo not in fuente.TIPOS:
        raise ValueError(f"Tipo de fuente desconocido: {tipo}")
    ext = Path(nombre_archivo).suffix.lower()
    huella = hashlib.sha256(contenido).hexdigest()
    tmp = cfg.datos / "subidas" / f"{huella}{ext}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(contenido)
    if ext in transcripcion.EXTENSIONES:
        tipo = "nota_de_voz"
        libro = transcripcion.a_libro(transcripcion.transcribir(cfg, tmp), titulo.strip() or Path(nombre_archivo).stem,
                                      autor.strip())
    elif nombre_archivo == PEGADO:
        libro = lib.de_texto(contenido.decode("utf-8", errors="replace"), titulo, autor, tipo)
    else:
        libro = lib.leer(tmp, titulo, autor, tipo)
    base = f"{date.today().isoformat()}-{_slug(libro.titulo)}"
    pid, k = base, 2
    while (cfg.proyectos / pid).exists():
        pid, k = f"{base}-{k}", k + 1
    dir_ = carpeta(cfg, pid)
    (dir_ / "libro").mkdir(parents=True)
    (dir_ / "libro" / f"original{ext}").write_bytes(contenido)
    libro.guardar(dir_ / "libro" / "capitulos.json")
    p = Proyecto(id=pid, libro=LibroInfo(
        tipo=libro.tipo, titulo=libro.titulo, autor=libro.autor, formato=libro.formato, archivo=f"libro/original{ext}",
        huella=f"sha256:{huella}", caracteres=libro.caracteres,
        capitulos=[{"n": c.n, "titulo": c.titulo, "paginas": c.rango, "caracteres": len(c.texto)} for c in libro.capitulos]))
    p.etapas["ingesta"].estado = "hecha"
    guardar(cfg, p)
    return p


def cargar(cfg: Config, pid: str) -> Proyecto:
    ruta = carpeta(cfg, pid) / "proyecto.json"
    if not ruta.exists():
        raise FileNotFoundError(pid)
    return Proyecto.model_validate_json(ruta.read_text(encoding="utf-8"))


def guardar(cfg: Config, p: Proyecto) -> None:
    ruta = carpeta(cfg, p.id) / "proyecto.json"
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(p.model_dump_json(indent=1), encoding="utf-8")
    tmp.replace(ruta)


@contextmanager
def editar(cfg: Config, pid: str):
    """Carga, deja modificar y guarda bajo el cerrojo del proyecto."""
    with _cerrojo(pid):
        p = cargar(cfg, pid)
        yield p
        guardar(cfg, p)


def libro(cfg: Config, pid: str) -> lib.Libro:
    return lib.Libro.cargar(carpeta(cfg, pid) / "libro" / "capitulos.json")


def lista(cfg: Config) -> list[dict]:
    salida = []
    for r in sorted(cfg.proyectos.glob("*/proyecto.json"), reverse=True):
        try:
            d = json.loads(r.read_text(encoding="utf-8"))
            salida.append({"id": d["id"], "titulo": d["libro"]["titulo"], "autor": d["libro"]["autor"], "creado": d["creado"],
                           "tipo": d["libro"].get("tipo", "libro"),
                           "etapas": {k: v["estado"] for k, v in d["etapas"].items()}})
        except Exception:
            continue
    return salida


def apuntar_gasto(cfg: Config, pid: str, etapa: str):
    """Devuelve un `al_gastar` para el LLM que apunta cada llamada en el proyecto."""
    def apuntar(uso: Uso) -> None:
        if uso.de_cache_local:
            return
        with editar(cfg, pid) as p:
            p.gasto.append(Gasto(etapa=etapa, servicio="anthropic", modelo=uso.modelo, usd=uso.usd,
                                 detalle=f"{uso.paso} · {uso.entrada}+{uso.cache_escritura}w+{uso.cache_lectura}r → "
                                         f"{uso.salida} tokens · {uso.segundos} s", creado=ahora()))
    return apuntar
