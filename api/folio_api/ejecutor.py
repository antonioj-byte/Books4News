"""Lanzar `folio run` desde la web: un proceso aparte (el pipeline carga 2 GB de embeddings y no
debe vivir en el servidor), una sola ejecución a la vez y su registro en el volumen de datos."""

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
    ultimas_lineas: list[str] = []


class Ejecutor:
    def __init__(self, dir_datos: Path, comando: list[str] | None = None):
        self.registro = dir_datos / "ejecucion.log"
        self.comando = comando or [sys.executable, "-m", "folio.cli", "run", "--quiet"]
        self._proceso: subprocess.Popen | None = None
        self._inicio: str | None = None
        self._fin: str | None = None
        self._cerrojo = threading.Lock()

    def lanzar(self) -> bool:
        """Lanza la ejecución del día. False si ya hay una en marcha."""
        with self._cerrojo:
            if self._proceso and self._proceso.poll() is None:
                return False
            self.registro.parent.mkdir(parents=True, exist_ok=True)
            salida = self.registro.open("w", encoding="utf-8")
            self._proceso = subprocess.Popen(self.comando, stdout=salida, stderr=subprocess.STDOUT)
            self._inicio, self._fin = datetime.now(timezone.utc).isoformat(timespec="seconds"), None
            threading.Thread(target=self._esperar, args=(self._proceso, salida), daemon=True).start()
            return True

    def _esperar(self, proceso: subprocess.Popen, salida) -> None:
        proceso.wait()
        salida.close()
        self._fin = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def estado(self) -> EstadoEjecucion:
        en_marcha = bool(self._proceso and self._proceso.poll() is None)
        lineas = []
        if self.registro.exists():
            lineas = [l for l in self.registro.read_text(encoding="utf-8", errors="replace").splitlines()
                      if l.strip() and "Fetching" not in l][-12:]
        codigo = None if en_marcha or not self._proceso else self._proceso.returncode
        return EstadoEjecucion(en_marcha=en_marcha, inicio=self._inicio, fin=self._fin, codigo=codigo,
                               ultimas_lineas=lineas)
