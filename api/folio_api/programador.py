"""Ejecución diaria programada: cada mañana, el pipeline del día y el render (PNG y vídeos),
para que a primera hora haya piezas listas para revisar y programar.

Se activa con FOLIO_EJECUCION_DIARIA=HH:MM, hora local de FOLIO_ZONA (por defecto Europe/Madrid, con
el cambio de hora resuelto). Sin la variable no hace nada: en local, nada cambia. Vive en el proceso de
la API (un hilo que mira el reloj cada 30 s), así que no hace falta otro servicio en Railway.

Reglas: una vez al día; si a esa hora hay una ejecución en marcha (lanzada a mano), espera a que acabe
mientras siga dentro de la ventana; si la API arranca tarde (un despliegue, un reinicio), recupera la del
día solo dentro de la ventana, para no lanzar a mediodía una ejecución de ~1 $ que nadie pidió. El día
de la última lanzada se guarda en el volumen (ejecucion_diaria.json).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from folio.modelos import BaseModel
from folio_api.ejecutor import Ejecutor

VENTANA = timedelta(hours=2)          # después de la hora, hasta cuándo se lanza (o se recupera)
log = logging.getLogger("folio_api.programador")


class EstadoProgramada(BaseModel):
    activa: bool
    hora: str | None = None           # HH:MM, hora local
    zona: str | None = None
    ultima: str | None = None         # fecha local de la última lanzada
    proxima: str | None = None        # fecha y hora local de la próxima


def hora_de_entorno() -> tuple[time | None, ZoneInfo]:
    zona = ZoneInfo(os.getenv("FOLIO_ZONA") or "Europe/Madrid")
    valor = (os.getenv("FOLIO_EJECUCION_DIARIA") or "").strip()
    if not valor:
        return None, zona
    h, m = valor.split(":")
    return time(int(h), int(m)), zona


class Programador:
    def __init__(self, ejecutor: Ejecutor, hora: time | None, zona: ZoneInfo, dir_datos: Path,
                 ahora: Callable[[], datetime] | None = None):
        self.ejecutor, self.hora, self.zona = ejecutor, hora, zona
        self.archivo = dir_datos / "ejecucion_diaria.json"
        self._ahora = ahora or (lambda: datetime.now(self.zona))
        self._parar = threading.Event()

    def ultima(self) -> str | None:
        try:
            return json.loads(self.archivo.read_text(encoding="utf-8")).get("ultima")
        except (OSError, ValueError):
            return None

    def comprobar(self) -> bool:
        """Lanza la del día si toca. True si la ha lanzado."""
        if not self.hora:
            return False
        ahora = self._ahora().astimezone(self.zona)
        programada = datetime.combine(ahora.date(), self.hora, self.zona)
        hoy = ahora.date().isoformat()
        if self.ultima() == hoy or not programada <= ahora < programada + VENTANA:
            return False
        if not self.ejecutor.lanzar(self.ejecutor.diaria):
            return False                   # hay otra en marcha: se reintenta en la próxima vuelta
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.archivo.write_text(json.dumps({"ultima": hoy, "lanzada": ahora.isoformat(timespec="seconds")}),
                                encoding="utf-8")
        log.info("Ejecución diaria lanzada (%s)", ahora.isoformat(timespec="minutes"))
        return True

    def estado(self) -> EstadoProgramada:
        if not self.hora:
            return EstadoProgramada(activa=False)
        ahora = self._ahora().astimezone(self.zona)
        proxima = datetime.combine(ahora.date(), self.hora, self.zona)
        if self.ultima() == ahora.date().isoformat() or ahora >= proxima + VENTANA:
            proxima = datetime.combine(ahora.date() + timedelta(days=1), self.hora, self.zona)
        return EstadoProgramada(activa=True, hora=self.hora.strftime("%H:%M"), zona=str(self.zona),
                                ultima=self.ultima(), proxima=proxima.isoformat(timespec="minutes"))

    def arrancar(self) -> None:
        if not self.hora:
            return

        def bucle():
            while not self._parar.wait(30):
                try:
                    self.comprobar()
                except Exception:
                    log.exception("Error en la ejecución diaria programada")
        threading.Thread(target=bucle, daemon=True, name="ejecucion-diaria").start()
        log.info("Ejecución diaria a las %s (%s)", self.hora.strftime("%H:%M"), self.zona)

    def parar(self) -> None:
        self._parar.set()


def lectura_de_entorno() -> int | None:
    """FOLIO_LECTURA_CADA: minutos entre lecturas periódicas de los RSS (sin la variable, no se lee)."""
    valor = (os.getenv("FOLIO_LECTURA_CADA") or "").strip()
    return max(30, int(valor)) if valor else None


class Lector:
    """Lectura periódica de las noticias (folio leer) en un proceso aparte, cada `cada` minutos. No usa el ejecutor
    (no bloquea «Proceder» ni la diaria) y se salta la vuelta si hay una ejecución en marcha."""

    def __init__(self, ejecutor: Ejecutor, cada: int | None, lanzar: Callable[[], int] | None = None):
        self.ejecutor, self.cada = ejecutor, cada
        self._lanzar = lanzar or (lambda: subprocess.run([sys.executable, "-m", "folio.cli", "leer", "--quiet"],
                                                         timeout=600, capture_output=True).returncode)
        self._parar = threading.Event()
        self.ultima: str | None = None

    def una_vuelta(self) -> bool:
        if self.ejecutor.ocupado():
            return False
        codigo = self._lanzar()
        self.ultima = datetime.now().astimezone().isoformat(timespec="minutes")
        if codigo:
            log.warning("Lectura periódica: salió con código %s", codigo)
        return codigo == 0

    def arrancar(self) -> None:
        if not self.cada:
            return

        def bucle():
            while not self._parar.wait(self.cada * 60):
                try:
                    self.una_vuelta()
                except Exception:
                    log.exception("Error en la lectura periódica")
        threading.Thread(target=bucle, daemon=True, name="lectura-periodica").start()
        log.info("Lectura periódica de los RSS cada %s minutos", self.cada)

    def parar(self) -> None:
        self._parar.set()
