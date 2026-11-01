"""Etapas guardadas de una ejecución, en data/cache/<fecha>/.

Cada etapa del pipeline deja aquí su resultado para poder relanzar desde ella (`--desde
seleccion`, `--desde guion`, `--desde hechos`, `--desde arte`) sin repetir la ingesta ni pagar otra vez las
llamadas ya hechas. Los textos de cada historia se congelan aquí la primera vez que se descargan.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from folio.modelos import Articulo, FuenteNoticia, Historia, HistoriaElegida, HistoriaResumida, Pieza, SeleccionJefe

Etapa = Literal["ingesta", "seleccion", "guion", "hechos", "arte"]
ORDEN: dict[str, int] = {"ingesta": 0, "seleccion": 1, "guion": 2, "hechos": 3, "arte": 4}
VERSION_TEXTOS = 2  # 2: artículos elegidos por cercanía al hecho principal


def guardar_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: un tema de la redacción puede escribir mientras «Proceder» lee en otro proceso (2/11)
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, ruta)


def cargar_json(ruta: Path):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}: ejecuta antes las etapas anteriores")
    return json.loads(ruta.read_text(encoding="utf-8"))


class EtapasGuardadas:
    def __init__(self, directorio: Path):
        self.directorio = directorio

    def hay_articulos(self) -> bool:
        return (self.directorio / "articulos.json").exists()

    def articulos(self) -> list[Articulo]:
        return TypeAdapter(list[Articulo]).validate_python(cargar_json(self.directorio / "articulos.json"))

    def guardar_articulos(self, articulos: list[Articulo]) -> None:
        guardar_json(self.directorio / "articulos.json", [a.model_dump(mode="json") for a in articulos])

    def historias(self) -> tuple[list[Historia], list[HistoriaResumida], dict]:
        datos = cargar_json(self.directorio / "historias.json")
        return (TypeAdapter(list[Historia]).validate_python(datos["al_jefe"]),
                TypeAdapter(list[HistoriaResumida]).validate_python(datos["resumidas"]), datos["stats"])

    def guardar_historias(self, al_jefe: list[Historia], resumidas: list[HistoriaResumida], stats: dict) -> None:
        guardar_json(self.directorio / "historias.json", {
            "al_jefe": [h.model_dump(mode="json") for h in al_jefe],
            "resumidas": [r.model_dump(mode="json") for r in resumidas],
            "stats": stats,
        })

    def seleccion(self) -> SeleccionJefe:
        return SeleccionJefe.model_validate(cargar_json(self.directorio / "seleccion.json"))

    def guardar_seleccion(self, sel: SeleccionJefe) -> None:
        guardar_json(self.directorio / "seleccion.json", sel.model_dump(mode="json"))

    def radar(self) -> list[HistoriaElegida]:
        """Los temas del radar del libro (vacío si la ejecución es anterior al radar)."""
        ruta = self.directorio / "radar.json"
        return TypeAdapter(list[HistoriaElegida]).validate_python(cargar_json(ruta)) if ruta.exists() else []

    def guardar_radar(self, temas: list[HistoriaElegida]) -> None:
        guardar_json(self.directorio / "radar.json", [t.model_dump(mode="json") for t in temas])

    def piezas(self) -> list[Pieza]:
        return TypeAdapter(list[Pieza]).validate_python(cargar_json(self.directorio / "piezas.json"))

    def guardar_piezas(self, piezas: list[Pieza]) -> None:
        guardar_json(self.directorio / "piezas.json", [p.model_dump(mode="json") for p in piezas])

    def textos(self, historia_id: str) -> list[tuple[FuenteNoticia, str]] | None:
        """Textos congelados de la historia, o None si no los hay (o son de una versión anterior,
        que eligía los artículos sin mirar su relevancia: se vuelven a elegir y descargar)."""
        ruta = self.directorio / "textos" / f"{historia_id}.json"
        if not ruta.exists():
            return None
        guardado = cargar_json(ruta)
        if not (isinstance(guardado, dict) and guardado.get("version") == VERSION_TEXTOS):
            return None
        return [(FuenteNoticia.model_validate(x["fuente"]), x["texto"]) for x in guardado["textos"]]

    def guardar_textos(self, historia_id: str, textos: list[tuple[FuenteNoticia, str]]) -> None:
        guardar_json(self.directorio / "textos" / f"{historia_id}.json", {
            "version": VERSION_TEXTOS,
            "textos": [{"fuente": f.model_dump(mode="json"), "texto": t} for f, t in textos],
        })
