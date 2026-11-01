"""Lanzar `folio run` desde la web: un proceso aparte (el pipeline carga 2 GB de embeddings y no
debe vivir en el servidor), una sola ejecución a la vez y su registro en el volumen de datos.

Una ejecución puede tener varios pasos seguidos (la diaria: el pipeline y después el render de PNG y
vídeo); si un paso falla, los siguientes no se lanzan."""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from folio.modelos import BaseModel


class EstadoEjecucion(BaseModel):
    en_marcha: bool
    inicio: str | None = None
    fin: str | None = None
    codigo: int | None = None          # código de salida del último `folio run` (0 = bien)
    etapa: str | None = None           # última línea «ETAPA: …» del registro
    ultimas_lineas: list[str] = []


MAX_DESARROLLOS = 3                    # «Proceder» a la vez (2/11): cada uno es un proceso aparte


class _Trabajo:
    """Un proceso (o varios pasos seguidos) con su registro."""

    def __init__(self, registro: Path, pasos: list[list[str]]):
        self.registro = registro
        self.registro.parent.mkdir(parents=True, exist_ok=True)
        salida = self.registro.open("w", encoding="utf-8")
        self.proceso = subprocess.Popen(pasos[0], stdout=salida, stderr=subprocess.STDOUT)
        self.pendientes = pasos[1:]
        self.inicio, self.fin = datetime.now(timezone.utc).isoformat(timespec="seconds"), None
        threading.Thread(target=self._esperar, args=(salida,), daemon=True).start()

    def _esperar(self, salida) -> None:
        while True:
            self.proceso.wait()
            if self.proceso.returncode != 0 or not self.pendientes:
                break
            salida.flush()
            self.proceso = subprocess.Popen(self.pendientes.pop(0), stdout=salida, stderr=subprocess.STDOUT)
        salida.close()
        self.fin = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def vivo(self) -> bool:
        return self.proceso.poll() is None or self.fin is None

    def estado(self) -> EstadoEjecucion:
        return _estado(self.registro, self.vivo(), self.inicio, self.fin,
                       None if self.vivo() else self.proceso.returncode)


def _estado(registro: Path, en_marcha: bool, inicio, fin, codigo) -> EstadoEjecucion:
    lineas: list[str] = []
    etapa = None
    if registro.exists():
        todas = [l for l in registro.read_text(encoding="utf-8", errors="replace").splitlines()
                 if l.strip() and "Fetching" not in l]
        etapa = next((l.removeprefix("ETAPA: ") for l in reversed(todas) if l.startswith("ETAPA: ")), None)
        lineas = [l for l in todas if not l.startswith(("ETAPA: ", "TIEMPO: "))][-12:]
    return EstadoEjecucion(en_marcha=en_marcha, inicio=inicio, fin=fin, codigo=codigo, etapa=etapa, ultimas_lineas=lineas)


class Ejecutor:
    def __init__(self, dir_datos: Path, comando: list[str] | None = None):
        self.registro = dir_datos / "ejecucion.log"
        self.dir_desarrollos = dir_datos / "desarrollos"
        self.comando = comando or [sys.executable, "-m", "folio.cli", "run", "--quiet"]
        # La ejecución diaria programada: el pipeline y, si sale bien, PNG y vídeos
        # y, al final, la nevera del cajón: historias editoriales nuevas (2/11; nunca hace fallar la diaria)
        # y, los lunes, el análisis semanal del feedback para la Memoria (2/11; tampoco falla nunca)
        self.diaria = [self.comando, [sys.executable, "-m", "folio.cli", "render", "--video"],
                       [sys.executable, "-m", "folio.cli", "cajon", "buscar"],
                       [sys.executable, "-m", "folio.cli", "memoria", "analizar", "--si-toca"]]
        self._trabajo: _Trabajo | None = None
        self._desarrollos: dict[str, _Trabajo] = {}
        self._cerrojo = threading.Lock()

    def lanzar(self, pasos: list[list[str]] | None = None) -> bool:
        """Lanza la ejecución del día (por defecto, solo el pipeline). False si ya hay una en marcha o si se están
        escribiendo piezas con «Proceder» (el pipeline reescribe las historias del día que ellas leen)."""
        pasos = pasos or [self.comando]
        with self._cerrojo:
            if self.ocupado() or self.desarrollando():
                return False
            self._trabajo = _Trabajo(self.registro, pasos)
            return True

    def desarrollar(self, pid: str, pasos: list[list[str]]) -> str | None:
        """«Proceder» de una pieza, en paralelo con otras piezas, el render, la nevera o la Memoria (2/11, a petición
        del usuario: «¿no puede hacer dos cosas a la vez?»). Devuelve None si la lanza o el motivo si no."""
        with self._cerrojo:
            if self.con_pipeline():
                return "Se está preparando la mesa del día; prueba cuando termine"
            previo = self._desarrollos.get(pid)
            if previo and previo.vivo():
                return "Esta pieza ya se está escribiendo"
            if self.desarrollando() >= MAX_DESARROLLOS:
                return f"Ya se están escribiendo {MAX_DESARROLLOS} piezas; prueba cuando acabe alguna"
            nombre = "".join(c if c.isalnum() or c in "-_" else "_" for c in pid)
            self._desarrollos[pid] = _Trabajo(self.dir_desarrollos / f"{nombre}.log", pasos)
            return None

    def desarrollando(self) -> int:
        return sum(1 for t in self._desarrollos.values() if t.vivo())

    def estado_desarrollo(self, pid: str) -> EstadoEjecucion | None:
        t = self._desarrollos.get(pid)
        return t.estado() if t else None

    def con_pipeline(self) -> bool:
        """Si lo que corre ahora es el pipeline del día (`folio run`), que reescribe las historias del día. Proceder,
        el render, la nevera y la Memoria no chocan con un tema de la redacción (2/11)."""
        return self.ocupado() and "run" in list(getattr(self._trabajo.proceso, "args", []) or [])

    def ocupado(self) -> bool:
        return bool(self._trabajo and self._trabajo.vivo())

    def estado(self) -> EstadoEjecucion:
        t = self._trabajo
        if not t:
            return _estado(self.registro, False, None, None, None)
        return t.estado()
