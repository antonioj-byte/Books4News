"""Historial en SQLite para no repetir historias (7 días) ni libros (60 días).

Solo cuentan los días anteriores a la fecha de la ejecución: se puede relanzar el mismo día
tantas veces como haga falta sin que una ejecución excluya lo de la anterior.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from folio.verificacion_texto import clave_libro

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS historias_usadas (
    fecha TEXT NOT NULL, historia_id TEXT NOT NULL, titular TEXT, centroide BLOB NOT NULL,
    PRIMARY KEY (fecha, historia_id)
);
CREATE TABLE IF NOT EXISTS libros_usados (
    fecha TEXT NOT NULL, clave TEXT NOT NULL, titulo TEXT, autor TEXT, olid TEXT,
    PRIMARY KEY (fecha, clave)
);
"""


class Historial:
    def __init__(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # Comparte archivo con la base de la web (folio.almacen): espera si está ocupada
        self.db = sqlite3.connect(ruta, timeout=10)
        self.db.executescript(_ESQUEMA)

    def _desde(self, fecha: str, dias: int) -> str:
        return (date.fromisoformat(fecha) - timedelta(days=dias)).isoformat()

    def centroides_recientes(self, fecha: str, dias: int) -> list[tuple[str, str, np.ndarray]]:
        filas = self.db.execute(
            "SELECT fecha, titular, centroide FROM historias_usadas WHERE fecha >= ? AND fecha < ?",
            (self._desde(fecha, dias), fecha),
        ).fetchall()
        return [(f, t, np.frombuffer(c, dtype=np.float32)) for f, t, c in filas]

    def libro_usado(self, fecha: str, dias: int, titulo: str, autor: str, olid: str | None) -> str | None:
        """Devuelve la fecha en que se usó el libro, o None."""
        fila = self.db.execute(
            "SELECT fecha FROM libros_usados WHERE fecha >= ? AND fecha < ? AND (clave = ? OR (olid IS NOT NULL AND olid = ?))",
            (self._desde(fecha, dias), fecha, clave_libro(titulo, autor), olid),
        ).fetchone()
        return fila[0] if fila else None

    def anadir_libros(self, fecha: str, libros: list[tuple[str, str, str | None]]) -> None:
        """Añade libros usados el día `fecha` sin tocar lo ya registrado (una pieza desarrollada más tarde)."""
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO libros_usados VALUES (?, ?, ?, ?, ?)",
                [(fecha, clave_libro(t, a), t, a, olid) for t, a, olid in libros],
            )

    def registrar_dia(self, fecha: str, historias: list[tuple[str, str, np.ndarray]], libros: list[tuple[str, str, str | None]]):
        """Sustituye lo registrado para `fecha` (una nueva ejecución del día reemplaza la anterior)."""
        with self.db:
            self.db.execute("DELETE FROM historias_usadas WHERE fecha = ?", (fecha,))
            self.db.execute("DELETE FROM libros_usados WHERE fecha = ?", (fecha,))
            self.db.executemany(
                "INSERT OR REPLACE INTO historias_usadas VALUES (?, ?, ?, ?)",
                [(fecha, hid, tit, c.astype(np.float32).tobytes()) for hid, tit, c in historias],
            )
            self.db.executemany(
                "INSERT OR REPLACE INTO libros_usados VALUES (?, ?, ?, ?, ?)",
                [(fecha, clave_libro(t, a), t, a, olid) for t, a, olid in libros],
            )
