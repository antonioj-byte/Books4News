"""Prueba de estilos de ilustración para el Instagram de Folio (Magnific, Flux 2 Pro, texto a imagen).

Documentación consultada el 4/11/2026: https://docs.magnific.com/api-reference/text-to-image/post-flux-2-pro.md
POST /v1/ai/text-to-image/flux-2-pro (cabecera x-magnific-api-key; prompt, width/height 256–1440, seed 0–4294967295)
y GET /v1/ai/text-to-image/flux-2-pro/{task_id} hasta COMPLETED, con las URLs en `generated`.

Uso:  python generar.py risografia:anthropic      (una combinación)
      python generar.py --todas                   (las 15; no repite las que ya existen)
Clave: MAGNIFIC_API_KEY o FREEPIK_API_KEY. Ante cualquier error, informa y sigue con la siguiente; no reintenta.
"""
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

AQUI = Path(__file__).parent
BASE = "https://api.magnific.com/v1/ai/text-to-image/flux-2-pro"
ANCHO, ALTO = 1080, 1350          # 4:5
MAX_GENERACIONES = 20

ESTILOS = {
    "risografia": "risograph print, two-color magenta and yellow on off-white paper, slight misregistration, visible halftone, paper grain",
    "grabado": "19th century engraving, fine crosshatching, black ink on cream paper, one flat accent block of magenta or yellow",
    "fotomontaje": "dada constructivist photomontage, black and white cut-out photos, impossible scale, torn paper edges, flat geometric shapes in magenta and yellow",
    "objeto": "single symbolic object isolated on flat background, hard studio light, editorial still life, limited palette magenta yellow black cream",
    "gouache": "muted gouache illustration, vintage children's book style, visible brush texture, limited palette",
}
COMUN = "editorial magazine cover image, negative space in lower third, no text, no letters"
# La paleta cerrada de la marca y lo prohibido, iguales en todos
PALETA = ("strict colour palette: magenta #D6246E, yellow #F2E14C, black and cream #F3EFE6, no other colours; "
          "no 3D render, no glossy CGI, no cartoon characters, no recognizable real people")
# Opción A (4/11): los mismos temas sin superficies que inviten a escribir (cheque, monedas, páginas, letrero),
# porque en la prueba el cheque y las monedas salieron con letras y números inventados
TEMAS = {
    "anthropic": "stack of books with plain unmarked gold coins spilling out and a blank torn cheque with no writing",
    "biblia1631": "antique open Bible with blank pages on a wooden printing press, one empty gap where a word is missing",
    "goncourt": "Parisian restaurant facade at night with blank awning and no sign, two laurel wreaths facing each other",
}


def prompt_de(estilo: str, tema: str) -> str:
    return f"{TEMAS[tema]}, {ESTILOS[estilo]}, {COMUN}, {PALETA}"


def generar(estilo: str, tema: str, clave: str, registro: dict) -> None:
    nombre = f"{estilo}_{tema}"
    if (AQUI / f"{nombre}.png").exists():
        print(f"{nombre}: ya existe, no se repite")
        return
    if len(registro) >= MAX_GENERACIONES:
        raise SystemExit(f"Tope de {MAX_GENERACIONES} generaciones: pregunta antes de seguir")
    seed = random.randint(0, 4_294_967_295)
    cuerpo = {"prompt": prompt_de(estilo, tema), "width": ANCHO, "height": ALTO, "seed": seed}
    t0 = time.monotonic()
    with httpx.Client(timeout=60, headers={"x-magnific-api-key": clave}) as c:
        r = c.post(BASE, json=cuerpo)
        if r.status_code >= 400:
            print(f"{nombre}: ERROR {r.status_code} al crear la tarea: {r.text[:300]}")
            return
        tarea = r.json()["data"]
        while tarea.get("status") not in ("COMPLETED", "FAILED"):
            if time.monotonic() - t0 > 240:
                print(f"{nombre}: la tarea {tarea['task_id']} no terminó en 4 minutos")
                return
            time.sleep(4)
            g = c.get(f"{BASE}/{tarea['task_id']}")
            if g.status_code >= 400:
                print(f"{nombre}: ERROR {g.status_code} al consultar: {g.text[:300]}")
                return
            tarea = g.json()["data"]
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            print(f"{nombre}: la tarea falló ({json.dumps(tarea)[:300]})")
            return
        img = c.get(tarea["generated"][0])
        img.raise_for_status()
    from PIL import Image
    from io import BytesIO
    Image.open(BytesIO(img.content)).convert("RGB").save(AQUI / f"{nombre}.png")
    registro[nombre] = {"estilo": estilo, "tema": tema, "modelo": "flux-2-pro", "endpoint": BASE, **cuerpo,
                        "task_id": tarea["task_id"], "segundos": round(time.monotonic() - t0, 1)}
    print(f"{nombre}: OK en {registro[nombre]['segundos']} s (seed {seed})")


def main() -> None:
    clave = os.getenv("MAGNIFIC_API_KEY") or os.getenv("FREEPIK_API_KEY")
    if not clave:
        raise SystemExit("Falta MAGNIFIC_API_KEY o FREEPIK_API_KEY")
    ruta = AQUI / "prompts.json"
    registro = json.loads(ruta.read_text()) if ruta.exists() else {}
    if sys.argv[1:] == ["--todas"]:
        pares = [(e, t) for e in ESTILOS for t in TEMAS]
    else:
        pares = [tuple(a.split(":")) for a in sys.argv[1:]]
    # De tres en tres, para no tardar un cuarto de hora (sin reintentos: un fallo se informa y se sigue)
    import threading
    from concurrent.futures import ThreadPoolExecutor
    cerrojo = threading.Lock()

    def una(par):
        generar(par[0], par[1], clave, registro)
        with cerrojo:
            ruta.write_text(json.dumps(registro, ensure_ascii=False, indent=1))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(una, pares))


if __name__ == "__main__":
    main()
