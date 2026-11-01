"""El juez a ciegas de las rondas de la voz (2/11, a petición del usuario: mejorar por rondas cómo escribe el guionista).

`folio ab-juez <carpeta>` lee el ab.md de una ronda (versiones con letras, sin decir qué variante es cada una), pide a
un modelo distinto del que escribe (`modelos.juez`, prompts/juez_voz.md) que puntúe cada versión de 1 a 5 en idea
nueva y voz, diga si la publicaría y copie su mejor y su peor frase, y rellena con eso los bloques de evaluación de
ab.md. Solo después abre ab_clave.json para decidir con la regla de las rondas:

    la variante gana si no empeora los hechos no verificados ni las piezas publicables y sube la media de idea y voz
    al menos 0,25 puntos respecto al control.

Las frases que el juez dice copiar se comprueban contra el texto: si no están, se marca (el juez no puede inventar).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from folio.config import Config
from folio.llm import LLM, cargar_prompt
from folio.verificacion_texto import normalizar

MEJORA_MINIMA = 0.25


class NotaVersion(BaseModel):
    letra: str = Field(description="La letra de la versión (A, B…)")
    idea: int = Field(description="Idea nueva, de 1 a 5")
    voz: int = Field(description="Voz de Folio, de 1 a 5")
    publicaria: bool = Field(description="¿La publicarías tal cual?")
    mejor_frase: str = Field(description="La mejor frase de la versión, copiada letra por letra")
    peor_frase: str = Field(description="La peor frase de la versión, copiada letra por letra")
    por_que_idea: str = Field(description="Una línea que explica la nota de idea, apoyada en una frase concreta del texto")
    por_que_voz: str = Field(description="Una línea que explica la nota de voz, apoyada en una frase concreta del texto")


class Juicio(BaseModel):
    versiones: list[NotaVersion]


_PIEZA = re.compile(r"^## (\S+) · .*?$(.*?)(?=^## |\Z)", re.M | re.S)
_VERSION = re.compile(r"^#### Versión ([A-G])\n(.*?)(?=^<!-- ab:)", re.M | re.S)


def versiones(md: str) -> dict[str, dict[str, str]]:
    """{pieza: {letra: texto de la versión}} de un ab.md (sin los bloques de evaluación)."""
    out: dict[str, dict[str, str]] = {}
    for pid, cuerpo in _PIEZA.findall(md):
        out[pid] = {letra: texto.strip() for letra, texto in _VERSION.findall(cuerpo)}
    return out


def _esta(frase: str, texto: str) -> bool:
    f = normalizar(frase.strip(" .«»\"“”"))
    return bool(f) and f in normalizar(texto)


def _rellenar(md: str, pid: str, n: NotaVersion, literal: bool) -> str:
    clave = f"ab:{pid}:{n.letra}"
    comentario = (f"Juez a ciegas. Idea: {n.por_que_idea} Voz: {n.por_que_voz} Mejor: «{n.mejor_frase}». "
                  f"Peor: «{n.peor_frase}».{'' if literal else ' (Alguna frase citada no está letra por letra en el texto.)'}")
    valores = {"Idea nueva (1–5)": str(n.idea), "Voz (1–5)": str(n.voz),
               "¿La publicarías? (sí/no)": "sí" if n.publicaria else "no", "Comentario": " ".join(comentario.split())}

    def sustituir(m: re.Match) -> str:
        cuerpo = m.group(2)
        for campo, valor in valores.items():
            cuerpo = re.sub(rf"^- {re.escape(campo)}:.*$", lambda _: f"- {campo}: {valor}", cuerpo, flags=re.M)
        return f"<!-- {clave} -->{cuerpo}<!-- /{clave} -->"
    return re.sub(rf"<!-- ({re.escape(clave)}) -->(.*?)<!-- /\1 -->", sustituir, md, flags=re.S)


def juzgar(cfg: Config, directorio: Path, llm: LLM | None = None) -> dict:
    """Juzga a ciegas la ronda de `directorio` (ab.md), rellena ab.md y guarda juez.json. No abre la clave."""
    llm = llm or LLM(cfg)
    ruta_md = directorio / "ab.md"
    md = ruta_md.read_text(encoding="utf-8")
    voz = (cfg.dir_prompts / "voz_folio.md").read_text(encoding="utf-8").strip()
    salida: dict = {"piezas": {}, "coste_usd": 0.0}
    for pid, vers in versiones(md).items():
        bloque = "\n\n".join(f"<version letra=\"{l}\">\n{t}\n</version>" for l, t in sorted(vers.items()))
        prompt = cargar_prompt(cfg, "juez_voz", {"[pegar voz]": voz, "[pegar versiones]": bloque})
        juicio, _ = llm.estructurado(f"juez:{pid}", [{"role": "user", "content": prompt}], Juicio, etapa_modelo="juez",
                                     max_tokens=8000)
        notas = {}
        for n in juicio.versiones:
            n.letra = n.letra.strip().upper()[:1]
            if n.letra not in vers:
                continue
            n.idea, n.voz = max(1, min(5, n.idea)), max(1, min(5, n.voz))
            literal = _esta(n.mejor_frase, vers[n.letra]) and _esta(n.peor_frase, vers[n.letra])
            md = _rellenar(md, pid, n, literal)
            notas[n.letra] = {**n.model_dump(), "frases_literales": literal}
        faltan = set(vers) - set(notas)
        if faltan:
            raise ValueError(f"El juez no puntuó {sorted(faltan)} de {pid}")
        salida["piezas"][pid] = notas
    salida["coste_usd"] = round(sum(t.coste_usd for t in llm.trazas), 4)
    salida["modelo"] = cfg.modelo("juez")
    ruta_md.write_text(md, encoding="utf-8")
    (directorio / "juez.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida


def decidir(directorio: Path) -> tuple[str, dict]:
    """Destapa la clave y compara cada variante con el control con la regla de las rondas. (markdown, datos)."""
    clave = json.loads((directorio / "ab_clave.json").read_text(encoding="utf-8"))
    juez = json.loads((directorio / "juez.json").read_text(encoding="utf-8"))
    control = clave["control"]
    filas: dict[str, dict] = {}
    for pid, letras in clave["piezas"].items():
        for letra, d in letras.items():
            n = juez["piezas"].get(pid, {}).get(letra)
            f = filas.setdefault(d["variante"], {"idea": [], "voz": [], "publica": 0, "hechos_nv": 0, "intentos": 0,
                                                 "coste": 0.0, "fallidas": 0, "piezas": 0})
            f["piezas"] += 1
            f["hechos_nv"] += d["hechos_no_verificados"]
            f["intentos"] += d["intentos"]
            f["coste"] += d["coste_usd"]
            f["fallidas"] += d["error"] is not None
            if n:
                f["idea"].append(n["idea"])
                f["voz"].append(n["voz"])
                f["publica"] += bool(n["publicaria"])
    media = lambda xs: sum(xs) / len(xs) if xs else 0.0
    l = ["| Variante | Idea | Voz | Media idea+voz | Publicables | Hechos no verif. | Intentos | Coste $ | Fallidas |",
         "|---|---|---|---|---|---|---|---|---|"]
    for nombre, f in sorted(filas.items(), key=lambda kv: kv[0] != control):
        f["media"] = (media(f["idea"]) + media(f["voz"])) / 2
        l.append(f"| {nombre}{' (control)' if nombre == control else ''} | {media(f['idea']):.2f} | {media(f['voz']):.2f} | "
                 f"{f['media']:.2f} | {f['publica']}/{f['piezas']} | {f['hechos_nv']} | {f['intentos']} | {f['coste']:.3f} | {f['fallidas']} |")
    c = filas.get(control)
    veredictos = {}
    if c:
        for nombre, f in filas.items():
            if nombre == control:
                continue
            dif = f["media"] - c["media"]
            gana = (f["hechos_nv"] <= c["hechos_nv"] and f["publica"] >= c["publica"] and not f["fallidas"]
                    and dif >= MEJORA_MINIMA)
            veredictos[nombre] = {"gana": gana, "dif": round(dif, 2)}
            l.append(f"- {nombre}: {'GANA' if gana else 'no gana'} (idea+voz {dif:+.2f}; hechos no verif. "
                     f"{f['hechos_nv']} vs {c['hechos_nv']}; publicables {f['publica']} vs {c['publica']})")
    return "\n".join(l), {"filas": filas, "veredictos": veredictos, "coste_juez": juez["coste_usd"]}
