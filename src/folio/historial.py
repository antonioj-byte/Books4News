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
CREATE TABLE IF NOT EXISTS curiosidades_usadas (
    fecha TEXT NOT NULL, curiosidad TEXT NOT NULL, PRIMARY KEY (fecha, curiosidad)
);
CREATE TABLE IF NOT EXISTS publicadas (
    pieza_id TEXT PRIMARY KEY, fecha TEXT NOT NULL, titular TEXT, texto TEXT NOT NULL, redes TEXT, vector BLOB
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

    # --- Memoria de lo publicado (3/11, a petición del usuario: «como hemos publicado ahora sobre el Goncourt, que lo
    # recuerde para que mañana por la mañana no mande la misma historia») ---------------------------------------

    def anadir_publicada(self, fecha: str, pieza_id: str, titular: str, texto: str, redes: str = "") -> None:
        """Una pieza que sale (programada en Buffer o marcada «publicada»). El vector lo calcula la madrugada."""
        with self.db:
            self.db.execute("INSERT INTO publicadas (pieza_id, fecha, titular, texto, redes) VALUES (?, ?, ?, ?, ?) "
                            "ON CONFLICT(pieza_id) DO UPDATE SET fecha=excluded.fecha, titular=excluded.titular, "
                            "texto=excluded.texto, redes=excluded.redes, vector=NULL",
                            (pieza_id, fecha, titular, texto, redes))

    def publicadas_recientes(self, fecha: str, dias: int) -> list[tuple[str, str, str, str, np.ndarray | None]]:
        """(pieza, fecha, titular, texto, vector o None) de lo publicado en los `dias` anteriores a `fecha` y en el
        mismo día: lo de hoy cuenta para la ejecución de mañana y para relanzar hoy."""
        filas = self.db.execute("SELECT pieza_id, fecha, titular, texto, vector FROM publicadas WHERE fecha >= ? AND fecha <= ? "
                                "ORDER BY fecha DESC", (self._desde(fecha, dias), fecha)).fetchall()
        return [(p, f, t or "", x, np.frombuffer(v, dtype=np.float32) if v else None) for p, f, t, x, v in filas]

    def poner_vector(self, pieza_id: str, vector: np.ndarray) -> None:
        with self.db:
            self.db.execute("UPDATE publicadas SET vector = ? WHERE pieza_id = ?", (vector.astype(np.float32).tobytes(), pieza_id))

    def libro_usado(self, fecha: str, dias: int, titulo: str, autor: str, olid: str | None) -> str | None:
        """Devuelve la fecha en que se usó el libro, o None."""
        fila = self.db.execute(
            "SELECT fecha FROM libros_usados WHERE fecha >= ? AND fecha < ? AND (clave = ? OR (olid IS NOT NULL AND olid = ?))",
            (self._desde(fecha, dias), fecha, clave_libro(titulo, autor), olid),
        ).fetchone()
        return fila[0] if fila else None

    def libros_recientes(self, fecha: str, dias: int) -> list[tuple[str, str, str]]:
        """(fecha, título, autor) de los libros usados en los `dias` anteriores a `fecha`, del más reciente al más antiguo."""
        filas = self.db.execute("SELECT fecha, titulo, autor FROM libros_usados WHERE fecha >= ? AND fecha < ? "
                                "ORDER BY fecha DESC", (self._desde(fecha, dias), fecha)).fetchall()
        return [(f, t or "", a or "") for f, t, a in filas]

    def curiosidades_recientes(self, fecha: str, dias: int) -> set[str]:
        """Ids del cajón de curiosidades usados en los `dias` anteriores a `fecha`."""
        filas = self.db.execute("SELECT curiosidad FROM curiosidades_usadas WHERE fecha >= ? AND fecha < ?",
                                (self._desde(fecha, dias), fecha)).fetchall()
        return {f[0] for f in filas}

    def anadir_curiosidad(self, fecha: str, curiosidad: str) -> None:
        """Una curiosidad desarrollada más tarde («Proceder»), sin tocar lo ya registrado del día."""
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO curiosidades_usadas VALUES (?, ?)", (fecha, curiosidad))

    def anadir_libros(self, fecha: str, libros: list[tuple[str, str, str | None]]) -> None:
        """Añade libros usados el día `fecha` sin tocar lo ya registrado (una pieza desarrollada más tarde)."""
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO libros_usados VALUES (?, ?, ?, ?, ?)",
                [(fecha, clave_libro(t, a), t, a, olid) for t, a, olid in libros],
            )

    def registrar_dia(self, fecha: str, historias: list[tuple[str, str, np.ndarray]], libros: list[tuple[str, str, str | None]],
                      curiosidades: list[str] = ()):
        """Sustituye lo registrado para `fecha` (una nueva ejecución del día reemplaza la anterior)."""
        with self.db:
            self.db.execute("DELETE FROM historias_usadas WHERE fecha = ?", (fecha,))
            self.db.execute("DELETE FROM curiosidades_usadas WHERE fecha = ?", (fecha,))
            self.db.executemany("INSERT OR REPLACE INTO curiosidades_usadas VALUES (?, ?)", [(fecha, c) for c in curiosidades])
            self.db.execute("DELETE FROM libros_usados WHERE fecha = ?", (fecha,))
            self.db.executemany(
                "INSERT OR REPLACE INTO historias_usadas VALUES (?, ?, ?, ?)",
                [(fecha, hid, tit, c.astype(np.float32).tobytes()) for hid, tit, c in historias],
            )
            self.db.executemany(
                "INSERT OR REPLACE INTO libros_usados VALUES (?, ?, ?, ?, ?)",
                [(fecha, clave_libro(t, a), t, a, olid) for t, a, olid in libros],
            )
