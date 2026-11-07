"""Comandos de la beta: `uv run videos web`, `uv run videos ingesta libro.epub`, `uv run videos conceptos <proyecto>`,
`uv run videos guion <proyecto> <concepto>`."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from videos import almacen, conceptos, guion
from videos.config import Config
from videos.llm import LLM


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for ruidoso in ("pypdf", "httpx", "httpx2"):
        logging.getLogger(ruidoso).setLevel(logging.ERROR)
    ap = argparse.ArgumentParser(prog="videos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("web", help="la API y el asistente en http://127.0.0.1:8100")
    w.add_argument("--puerto", type=int, default=8100)
    i = sub.add_parser("ingesta", help="crea un proyecto a partir de un libro")
    i.add_argument("archivo", type=Path)
    i.add_argument("--titulo", default="")
    i.add_argument("--autor", default="")
    i.add_argument("--tipo", default="libro", choices=["libro", "articulo", "ensayo", "texto", "nota_de_voz"])
    c = sub.add_parser("conceptos", help="propone cinco conceptos")
    c.add_argument("proyecto")
    c.add_argument("--indicaciones", default="")
    g = sub.add_parser("guion", help="elige un concepto y escribe su guion")
    g.add_argument("proyecto")
    g.add_argument("concepto")
    a = ap.parse_args()
    cfg = Config()
    paso = lambda t: print(f"· {t}", flush=True)

    if a.cmd == "web":
        import uvicorn
        from videos.api import crear_app
        uvicorn.run(crear_app(cfg), host="127.0.0.1", port=a.puerto)
    elif a.cmd == "ingesta":
        p = almacen.crear(cfg, a.archivo.name, a.archivo.read_bytes(), a.titulo, a.autor, a.tipo)
        print(json.dumps({"id": p.id, "titulo": p.libro.titulo, "autor": p.libro.autor, "capitulos": len(p.libro.capitulos),
                          "caracteres": p.libro.caracteres}, ensure_ascii=False, indent=1))
    elif a.cmd == "conceptos":
        llm = LLM(cfg, al_gastar=almacen.apuntar_gasto(cfg, a.proyecto, "conceptos"))
        for x in conceptos.proponer(cfg, llm, a.proyecto, a.indicaciones, paso):
            print(f"\n[{x.id}] {x.titulo}\n  gancho: «{x.gancho}» ({x.juicio_gancho.nota}/10)\n  {x.idea}\n  "
                  f"pasaje (cap. {x.pasaje.capitulo}): «{x.pasaje.texto[:120]}…»")
        print(f"\nGasto: {sum(u.usd for u in llm.usos):.3f} $")
    elif a.cmd == "guion":
        conceptos.elegir(cfg, a.proyecto, a.concepto)
        llm = LLM(cfg, al_gastar=almacen.apuntar_gasto(cfg, a.proyecto, "guion"))
        v = guion.escribir(cfg, llm, a.proyecto, paso)
        for x in v.planos:
            print(f"{x.id} [{x.rol}] {x.locucion}" + (f"  ⟦{x.pantalla}⟧" if x.pantalla else ""))
        if v.avisos:
            print("\nAvisos:\n- " + "\n- ".join(v.avisos))
        print(f"\nGasto: {sum(u.usd for u in llm.usos):.3f} $")


if __name__ == "__main__":
    main()
