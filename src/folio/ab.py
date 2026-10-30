"""Prueba A/B del guionista: mismas historias, mismos libros, mismos textos; cambia el modelo.

`folio ab` toma las piezas propuestas del día (data/cache/<fecha>/piezas.json), reescribe el
guion con cada variante de config `ab.variantes` y deja en informes/<fecha>/ab/:

- ab.md: las versiones de cada pieza en orden aleatorio, con letras (A, B, C) y una plantilla
  de evaluación. Es ciego: no dice qué modelo escribió cada una.
- ab_clave.json: qué variante es cada letra y sus métricas (coste, intentos, hechos no
  verificados). No se abre hasta haber evaluado.

`folio ab-resultados` lee las evaluaciones de todos los días, destapa la clave y compara cada
variante con el control. Los libros son los que eligió el control: la prueba mide cómo se
escribe, no qué libro se elige.
"""

from __future__ import annotations

import copy
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from folio import evaluacion_md
from folio import guion as guionista
from folio import hechos
from folio.config import Config, VarianteAB
from folio.llm import LLM
from folio.modelos import FuenteNoticia, GuionLLM, Historia, Pieza
from pydantic import TypeAdapter

LETRAS = "ABCDEFG"


@dataclass
class Version:
    variante: str
    guion: GuionLLM | None
    coste_usd: float = 0.0
    intentos: int = 0
    hechos_no_verificados: int = 0
    hechos_total: int = 0
    error: str | None = None
    avisos: list[str] = field(default_factory=list)


def _cfg_variante(cfg: Config, v: VarianteAB) -> Config:
    c = copy.deepcopy(cfg)
    c.pipeline.modelos["guion"] = v.modelo
    c.pipeline.esfuerzo["guion"] = v.esfuerzo
    return c


def _escribir(cfg: Config, nombre: str, v: VarianteAB, pieza: Pieza, textos: list[tuple[FuenteNoticia, str]],
              reutilizar: bool) -> Version:
    llm = LLM(_cfg_variante(cfg, v), reutilizar=reutilizar)
    try:
        g, avisos = guionista.escribir(llm, f"ab:{pieza.id}:{nombre}", pieza.eleccion, textos, pieza.libros)
    except Exception as exc:
        return Version(nombre, None, sum(t.coste_usd for t in llm.trazas), len(llm.trazas), error=str(exc))
    guionista.ajustar_libros(g, pieza.libros)
    return Version(nombre, g, sum(t.coste_usd for t in llm.trazas), len(llm.trazas), avisos=avisos)


def _comprobar(cfg: Config, ver: Version, pieza: Pieza, textos, reutilizar: bool) -> None:
    if not ver.guion:
        return
    llm = LLM(cfg, reutilizar=reutilizar)
    try:
        hs = hechos.comprobar(llm, f"{pieza.id}-{ver.variante}", ver.guion, textos)
        ver.hechos_total, ver.hechos_no_verificados = len(hs), sum(not h.verificado for h in hs)
    except Exception as exc:
        ver.avisos.append(f"No se pudo comprobar los hechos: {exc}")


def _md_version(pieza_id: str, letra: str, g: GuionLLM | None) -> list[str]:
    l = [f"#### Versión {letra}", ""]
    if g is None:
        l += ["_Esta versión no pasó la validación._", ""]
    else:
        l += [f"{d.n}. _{d.tipo}_ — {d.texto}" for d in g.diapositivas]
        l += ["", "> " + g.pie_instagram.replace("\n", "\n> "), ""]
    l += evaluacion_md.bloque(f"ab:{pieza_id}:{letra}", evaluacion_md.CAMPOS_AB)
    return l


def generar(cfg: Config, fecha: str, textos_de, reutilizar: bool = False) -> tuple[Path, Path]:
    """`textos_de(historia_id)` devuelve los textos congelados de la historia."""
    ab = cfg.pipeline.ab
    if ab is None:
        raise ValueError("Falta la sección «ab» en config/pipeline.yaml")
    ruta_piezas = cfg.dir_cache(fecha) / "piezas.json"
    if not ruta_piezas.exists():
        raise FileNotFoundError(f"No existe {ruta_piezas}: ejecuta antes el pipeline del día")
    piezas = [p for p in TypeAdapter(list[Pieza]).validate_python(json.loads(ruta_piezas.read_text(encoding="utf-8")))
              if p.estado == "propuesta" and p.guion]
    directorio = cfg.dir_informes / fecha / "ab"
    ruta_md, ruta_clave = directorio / "ab.md", directorio / "ab_clave.json"
    if ruta_md.exists() and evaluaciones(ruta_md.read_text(encoding="utf-8")):
        raise FileExistsError(f"{ruta_md} ya tiene evaluaciones: no se sobrescribe")
    directorio.mkdir(parents=True, exist_ok=True)

    md = [f"# Prueba A/B del guion · {fecha}", "",
          "Cada pieza tiene varias versiones escritas con los mismos libros y las mismas noticias. "
          "No se dice qué modelo escribió cada una: evalúalas antes de abrir `ab_clave.json`.", ""]
    clave: dict = {"fecha": fecha, "control": ab.control,
                   "variantes": {k: v.model_dump() for k, v in ab.variantes.items()}, "piezas": {}}
    for pieza in piezas:
        textos = textos_de(pieza.historia_id)
        versiones = []
        for nombre, v in ab.variantes.items():
            if nombre == ab.control and ab.reutilizar_control:
                # El guion de producción ya es el control: mismas condiciones, sin pagarlo dos veces.
                ver = Version(nombre, pieza.guion, avisos=["guion de producción"])
            else:
                ver = _escribir(cfg, nombre, v, pieza, textos, reutilizar)
            _comprobar(cfg, ver, pieza, textos, reutilizar)
            versiones.append(ver)
        orden = list(range(len(versiones)))
        random.Random(f"{fecha}:{pieza.id}").shuffle(orden)
        md += [f"## {pieza.id} · {pieza.eleccion.titular}", "",
               f"Libros: {'; '.join(f'*{guionista.titulo_para_pieza(l)}*, {l.autores[0] if l.autores else ''}' for l in pieza.libros)}", ""]
        clave["piezas"][pieza.id] = {}
        for letra, i in zip(LETRAS, orden):
            ver = versiones[i]
            md += _md_version(pieza.id, letra, ver.guion)
            clave["piezas"][pieza.id][letra] = {
                "variante": ver.variante, "coste_usd": round(ver.coste_usd, 4), "intentos": ver.intentos,
                "hechos_no_verificados": ver.hechos_no_verificados, "hechos_total": ver.hechos_total,
                "palabras_por_diapositiva": (round(sum(len(d.texto.split()) for d in ver.guion.diapositivas)
                                                   / len(ver.guion.diapositivas), 1) if ver.guion else None),
                "diapositivas": len(ver.guion.diapositivas) if ver.guion else None,
                "error": ver.error, "avisos": ver.avisos,
            }
        md += evaluacion_md.bloque(f"ab:{pieza.id}:preferida", ("Preferida (letra)",))
    ruta_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    ruta_clave.write_text(json.dumps(clave, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta_md, ruta_clave


def evaluaciones(md: str) -> dict[tuple[str, str], dict[str, str]]:
    """{(pieza, letra o «preferida»): {campo: valor}} con los campos rellenados."""
    return {tuple(clave.rsplit(":", 1)): campos for clave, campos in evaluacion_md.leer(md, "ab").items()}


def _nota(v: str | None) -> float | None:
    m = re.match(r"\s*([1-5](?:[.,]\d)?)", v or "")
    return float(m.group(1).replace(",", ".")) if m else None


def resultados(cfg: Config) -> str:
    """Agrega todas las pruebas A/B evaluadas y compara cada variante con el control."""
    filas: dict[str, dict] = {}
    control = cfg.pipeline.ab.control if cfg.pipeline.ab else None
    for ruta_clave in sorted(cfg.dir_informes.glob("*/ab/ab_clave.json")):
        clave = json.loads(ruta_clave.read_text(encoding="utf-8"))
        evals = evaluaciones((ruta_clave.parent / "ab.md").read_text(encoding="utf-8"))
        for pieza, letras in clave["piezas"].items():
            preferida = evals.get((pieza, "preferida"), {}).get("Preferida (letra)", "").strip().upper()[:1]
            for letra, datos in letras.items():
                f = filas.setdefault(datos["variante"], {"n": 0, "evaluadas": 0, "libro": [], "idea": [], "voz": [],
                                                         "publica": [], "preferida": 0, "coste": [], "intentos": [],
                                                         "hechos_nv": [], "fallidas": 0})
                f["n"] += 1
                f["coste"].append(datos["coste_usd"])
                f["intentos"].append(datos["intentos"])
                f["hechos_nv"].append(datos["hechos_no_verificados"])
                f["fallidas"] += datos["error"] is not None
                f["preferida"] += preferida == letra
                e = evals.get((pieza, letra))
                if not e:
                    continue
                f["evaluadas"] += 1
                for campo, k in (("Libro (1–5)", "libro"), ("Idea nueva (1–5)", "idea"), ("Voz (1–5)", "voz")):
                    if (x := _nota(e.get(campo))) is not None:
                        f[k].append(x)
                pub = e.get("¿La publicarías? (sí/no)", "").lower()
                if pub:
                    f["publica"].append(pub.startswith("s"))
    if not filas:
        return "No hay pruebas A/B en informes/*/ab/."
    media = lambda xs: sum(xs) / len(xs) if xs else None
    fmt = lambda x, d=2: "—" if x is None else f"{x:.{d}f}"
    l = ["| Variante | Piezas (evaluadas) | Libro | Idea | Voz | Publicaría | Preferida | Coste medio $ | Intentos | Hechos no verif. | Fallidas |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nombre, f in sorted(filas.items(), key=lambda kv: kv[0] != control):
        pub = media([1.0 if p else 0.0 for p in f["publica"]])
        l.append(f"| {nombre}{' (control)' if nombre == control else ''} | {f['n']} ({f['evaluadas']}) | {fmt(media(f['libro']))} | "
                 f"{fmt(media(f['idea']))} | {fmt(media(f['voz']))} | {fmt(pub * 100 if pub is not None else None, 0)} % | "
                 f"{f['preferida']} | {fmt(media(f['coste']), 3)} | {fmt(media(f['intentos']), 1)} | "
                 f"{fmt(media(f['hechos_nv']), 1)} | {f['fallidas']} |")
    c = filas.get(control)
    l += ["", "Regla de decisión: una variante sustituye al control solo si no se publicarían menos piezas "
          "y la media de idea y voz no baja más de 0,25 puntos."]
    if c:
        for nombre, f in filas.items():
            if nombre == control:
                continue
            if not (f["publica"] and c["publica"] and f["idea"] and c["idea"] and f["voz"] and c["voz"]):
                l.append(f"- {nombre}: faltan evaluaciones para decidir.")
                continue
            ok_pub = media([1.0 if p else 0.0 for p in f["publica"]]) >= media([1.0 if p else 0.0 for p in c["publica"]])
            dif = (media(f["idea"]) + media(f["voz"])) / 2 - (media(c["idea"]) + media(c["voz"])) / 2
            veredicto = "cumple" if ok_pub and dif >= -0.25 else "no cumple"
            l.append(f"- {nombre}: {veredicto} (publicaría {'≥' if ok_pub else '<'} control; idea+voz {dif:+.2f}). "
                     f"Muestra: {f['evaluadas']} versiones evaluadas.")
    return "\n".join(l)
