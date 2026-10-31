"""Base de datos de la web (Fase 3): ejecuciones, piezas, versiones y evaluaciones.

Vive en el mismo SQLite que el historial (data/folio.db). La usan el pipeline (guarda cada
ejecución al terminar) y la API de /api. Sin ORM: sqlite3 y los esquemas Pydantic de siempre.

- Cada `folio run` es una ejecución. Relanzar un día crea otra; la anterior y sus
  evaluaciones siguen ahí.
- Las versiones de una pieza solo se añaden: deshacer es una versión nueva que copia una anterior.
- La evaluación se guarda aquí y se copia en el bloque de evaluación de informe.md, con los
  mismos marcadores, para que el formato de la Fase 1 siga valiendo.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from folio import evaluacion_md
from folio.modelos import BaseModel, InformeDiario, Pieza

_MIGRACIONES = [
    # 1: ejecuciones, piezas, versiones y evaluaciones
    """
    CREATE TABLE ejecuciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        generado_en TEXT NOT NULL UNIQUE,
        coste_usd REAL NOT NULL DEFAULT 0,
        informe TEXT NOT NULL              -- InformeDiario sin las piezas (selección, avisos, trazas…)
    );
    CREATE TABLE piezas (
        ejecucion_id INTEGER NOT NULL REFERENCES ejecuciones(id),
        pieza_id TEXT NOT NULL,
        estado TEXT NOT NULL,
        version_actual INTEGER NOT NULL,
        PRIMARY KEY (ejecucion_id, pieza_id)
    );
    CREATE TABLE versiones (
        ejecucion_id INTEGER NOT NULL,
        pieza_id TEXT NOT NULL,
        n INTEGER NOT NULL,
        creada_en TEXT NOT NULL,
        origen TEXT NOT NULL,              -- pipeline | manual | chat | reserva | deshacer
        descripcion TEXT NOT NULL DEFAULT '',
        datos TEXT NOT NULL,               -- Pieza completa en JSON
        PRIMARY KEY (ejecucion_id, pieza_id, n)
    );
    CREATE TABLE evaluaciones (
        ejecucion_id INTEGER NOT NULL,
        pieza_id TEXT NOT NULL,
        version_n INTEGER NOT NULL,
        seleccion INTEGER, libro INTEGER, idea INTEGER, voz INTEGER,
        publicaria INTEGER,                -- 1 sí, 0 no, NULL sin responder
        comentario TEXT NOT NULL DEFAULT '',
        actualizada TEXT NOT NULL,
        PRIMARY KEY (ejecucion_id, pieza_id)
    );
    """,
    # 2: conversación del chat de edición, por pieza (paso 5 del plan de la Fase 3)
    """
    CREATE TABLE chat_mensajes (
        ejecucion_id INTEGER NOT NULL,
        pieza_id TEXT NOT NULL,
        n INTEGER NOT NULL,
        rol TEXT NOT NULL,                 -- usuario | editor
        texto TEXT NOT NULL,
        version_n INTEGER,                 -- versión que creó el mensaje, si cambió la pieza
        creado_en TEXT NOT NULL,
        PRIMARY KEY (ejecucion_id, pieza_id, n)
    );
    """,
]


class Evaluacion(BaseModel):
    seleccion: int | None = Field(default=None, ge=1, le=5)
    libro: int | None = Field(default=None, ge=1, le=5)
    idea: int | None = Field(default=None, ge=1, le=5)
    voz: int | None = Field(default=None, ge=1, le=5)
    publicaria: bool | None = None
    comentario: str = ""


class MensajeChat(BaseModel):
    n: int
    rol: str
    texto: str
    version_n: int | None = None
    creado_en: str


class Version(BaseModel):
    n: int
    creada_en: str
    origen: str
    descripcion: str


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Almacen:
    """Acceso a la base de datos de la web.

    La API atiende peticiones en varios hilos y el pipeline escribe desde otro proceso, así que:
    una conexión por hilo, WAL (lectores y escritor no se bloquean), espera si la base está
    ocupada y escrituras en transacciones BEGIN IMMEDIATE (leer y escribir sin que otro se cuele).
    """

    def __init__(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta = ruta
        self._local = threading.local()
        self._activar_wal()
        self._migrar()

    def _activar_wal(self) -> None:
        """WAL es persistente: basta con activarlo una vez. Con la base recién creada y varias
        conexiones arrancando a la vez, el cambio puede dar «database is locked» sin esperar."""
        for intento in range(50):
            try:
                if self.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
                    return
                self.db.execute("PRAGMA journal_mode = WAL")
                return
            except sqlite3.OperationalError:
                if intento == 49:
                    raise
                time.sleep(0.1)

    @property
    def db(self) -> sqlite3.Connection:
        """Conexión de este hilo (sqlite3 no permite compartir una conexión entre hilos con seguridad)."""
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(self.ruta, timeout=10, isolation_level=None)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("PRAGMA busy_timeout = 10000")
            self._local.con = con
        return con

    @contextmanager
    def _transaccion(self) -> Iterator[sqlite3.Connection]:
        """Transacción de escritura: reserva la base desde el principio (BEGIN IMMEDIATE)."""
        db = self.db
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
        except BaseException:
            db.execute("ROLLBACK")
            raise
        db.execute("COMMIT")

    def _migrar(self) -> None:
        self.db.execute("CREATE TABLE IF NOT EXISTS migraciones (n INTEGER PRIMARY KEY)")
        for n, sql in enumerate(_MIGRACIONES, 1):
            with self._transaccion() as db:
                # Se comprueba dentro de la transacción: la API y el pipeline pueden arrancar a la vez
                if db.execute("SELECT 1 FROM migraciones WHERE n = ?", (n,)).fetchone():
                    continue
                for sentencia in (x.strip() for x in sql.split(";")):
                    if sentencia:
                        db.execute(sentencia)
                db.execute("INSERT INTO migraciones VALUES (?)", (n,))

    # --- Ejecuciones --------------------------------------------------------

    def registrar(self, inf: InformeDiario) -> int:
        """Guarda una ejecución con sus piezas (versión 1, origen pipeline). Idempotente por
        hora de generación: importar dos veces el mismo informe no lo duplica."""
        generado = inf.generado_en.isoformat()
        sin_piezas = inf.model_dump(mode="json", exclude={"piezas"})
        with self._transaccion() as db:
            # Dentro de la transacción: la API (al arrancar) y el pipeline pueden registrar el mismo informe
            fila = db.execute("SELECT id FROM ejecuciones WHERE generado_en = ?", (generado,)).fetchone()
            if fila:
                return fila["id"]
            cur = db.execute(
                "INSERT INTO ejecuciones (fecha, generado_en, coste_usd, informe) VALUES (?, ?, ?, ?)",
                (inf.fecha, generado, inf.coste_total_usd, json.dumps(sin_piezas, ensure_ascii=False)),
            )
            eid = cur.lastrowid
            for p in inf.piezas:
                db.execute("INSERT INTO piezas VALUES (?, ?, ?, 1)", (eid, p.id, p.estado))
                db.execute("INSERT INTO versiones VALUES (?, ?, 1, ?, 'pipeline', 'Generada por el pipeline', ?)",
                                (eid, p.id, generado, p.model_dump_json()))
        return eid

    def importar_informes(self, dir_informes: Path) -> list[int]:
        """Importa informes/<fecha>/informe.json (no los de prueba: -dev, solo-pieza)."""
        ids = []
        for ruta in sorted(dir_informes.glob("*/informe.json")):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ruta.parent.name):
                continue
            ids.append(self.registrar(InformeDiario.model_validate_json(ruta.read_text(encoding="utf-8"))))
        return ids

    def dias(self) -> list[dict]:
        filas = self.db.execute(
            "SELECT e.fecha, e.id, e.generado_en, e.coste_usd, COUNT(p.pieza_id) AS n "
            "FROM ejecuciones e LEFT JOIN piezas p ON p.ejecucion_id = e.id "
            "GROUP BY e.id ORDER BY e.fecha DESC, e.generado_en DESC").fetchall()
        dias: dict[str, list] = {}
        for f in filas:
            dias.setdefault(f["fecha"], []).append(
                {"id": f["id"], "generado_en": f["generado_en"], "coste_usd": f["coste_usd"], "piezas": f["n"]})
        return [{"fecha": k, "ejecuciones": v} for k, v in dias.items()]

    def ejecucion(self, eid: int) -> tuple[str, InformeDiario] | None:
        f = self.db.execute("SELECT fecha, informe FROM ejecuciones WHERE id = ?", (eid,)).fetchone()
        if not f:
            return None
        return f["fecha"], InformeDiario.model_validate({**json.loads(f["informe"]), "piezas": []})

    def ultima_ejecucion(self, fecha: str) -> int | None:
        f = self.db.execute("SELECT id FROM ejecuciones WHERE fecha = ? ORDER BY generado_en DESC LIMIT 1",
                            (fecha,)).fetchone()
        return f["id"] if f else None

    # --- Piezas y versiones -------------------------------------------------

    def piezas(self, eid: int) -> list[tuple[Pieza, int]]:
        """(pieza en su versión actual con el estado actual, nº de versión), en orden."""
        filas = self.db.execute(
            "SELECT p.estado, p.version_actual, v.datos FROM piezas p JOIN versiones v "
            "ON v.ejecucion_id = p.ejecucion_id AND v.pieza_id = p.pieza_id AND v.n = p.version_actual "
            "WHERE p.ejecucion_id = ? ORDER BY p.pieza_id", (eid,)).fetchall()
        return [(Pieza.model_validate_json(f["datos"]).model_copy(update={"estado": f["estado"]}), f["version_actual"])
                for f in filas]

    def pieza(self, eid: int, pid: str) -> tuple[Pieza, int] | None:
        return next(((p, v) for p, v in self.piezas(eid) if p.id == pid), None)

    def cambiar_estado(self, eid: int, pid: str, estado: str) -> None:
        with self._transaccion() as db:
            db.execute("UPDATE piezas SET estado = ? WHERE ejecucion_id = ? AND pieza_id = ?", (estado, eid, pid))

    def guardar_version(self, eid: int, pid: str, pieza: Pieza, origen: str, descripcion: str) -> int:
        with self._transaccion() as db:
            n = db.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM versiones WHERE ejecucion_id = ? AND pieza_id = ?",
                                (eid, pid)).fetchone()[0]
            db.execute("INSERT INTO versiones VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (eid, pid, n, _ahora(), origen, descripcion, pieza.model_dump_json()))
            db.execute("UPDATE piezas SET version_actual = ? WHERE ejecucion_id = ? AND pieza_id = ?", (n, eid, pid))
        return n

    def versiones(self, eid: int, pid: str) -> list[Version]:
        return [Version(**dict(f)) for f in self.db.execute(
            "SELECT n, creada_en, origen, descripcion FROM versiones WHERE ejecucion_id = ? AND pieza_id = ? ORDER BY n",
            (eid, pid))]

    def version(self, eid: int, pid: str, n: int) -> Pieza | None:
        f = self.db.execute("SELECT datos FROM versiones WHERE ejecucion_id = ? AND pieza_id = ? AND n = ?",
                            (eid, pid, n)).fetchone()
        return Pieza.model_validate_json(f["datos"]) if f else None

    # --- Chat de edición ----------------------------------------------------

    def chat(self, eid: int, pid: str) -> list[MensajeChat]:
        return [MensajeChat(**dict(f)) for f in self.db.execute(
            "SELECT n, rol, texto, version_n, creado_en FROM chat_mensajes WHERE ejecucion_id = ? AND pieza_id = ? ORDER BY n",
            (eid, pid))]

    def anadir_mensaje(self, eid: int, pid: str, rol: str, texto: str, version_n: int | None = None) -> None:
        with self._transaccion() as db:
            n = db.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM chat_mensajes WHERE ejecucion_id = ? AND pieza_id = ?",
                           (eid, pid)).fetchone()[0]
            db.execute("INSERT INTO chat_mensajes VALUES (?, ?, ?, ?, ?, ?, ?)", (eid, pid, n, rol, texto, version_n, _ahora()))

    # --- Evaluaciones -------------------------------------------------------

    def evaluacion(self, eid: int, pid: str) -> tuple[Evaluacion, int] | None:
        f = self.db.execute("SELECT * FROM evaluaciones WHERE ejecucion_id = ? AND pieza_id = ?", (eid, pid)).fetchone()
        if not f:
            return None
        pub = None if f["publicaria"] is None else bool(f["publicaria"])
        return Evaluacion(seleccion=f["seleccion"], libro=f["libro"], idea=f["idea"], voz=f["voz"],
                          publicaria=pub, comentario=f["comentario"]), f["version_n"]

    def guardar_evaluacion(self, eid: int, pid: str, ev: Evaluacion, version_n: int) -> None:
        pub = None if ev.publicaria is None else int(ev.publicaria)
        with self._transaccion() as db:
            db.execute(
                "INSERT INTO evaluaciones VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (ejecucion_id, pieza_id) DO UPDATE SET version_n = excluded.version_n, "
                "seleccion = excluded.seleccion, libro = excluded.libro, idea = excluded.idea, voz = excluded.voz, "
                "publicaria = excluded.publicaria, comentario = excluded.comentario, actualizada = excluded.actualizada",
                (eid, pid, version_n, ev.seleccion, ev.libro, ev.idea, ev.voz, pub, ev.comentario, _ahora()))

    def resumen_evaluaciones(self) -> list[dict]:
        """Medias por criterio y día, y porcentaje de piezas que se publicarían."""
        filas = self.db.execute(
            "SELECT e.fecha, COUNT(*) AS n, AVG(v.seleccion) AS seleccion, AVG(v.libro) AS libro, "
            "AVG(v.idea) AS idea, AVG(v.voz) AS voz, AVG(v.publicaria) AS publicaria "
            "FROM evaluaciones v JOIN ejecuciones e ON e.id = v.ejecucion_id GROUP BY e.fecha ORDER BY e.fecha").fetchall()
        return [dict(f) for f in filas]


# --- Copia de la evaluación en informe.md ----------------------------------------

def escribir_evaluacion_md(ruta_md: Path, pid: str, ev: Evaluacion) -> bool:
    """Rellena el bloque <!-- evaluacion:pid --> de informe.md. Devuelve False si no existe."""
    if not ruta_md.exists():
        return False
    pub = "" if ev.publicaria is None else ("sí" if ev.publicaria else "no")
    valores = [ev.seleccion, ev.libro, ev.idea, ev.voz, pub, ev.comentario.replace("\n", " ")]
    md = evaluacion_md.rellenar(ruta_md.read_text(encoding="utf-8"), f"evaluacion:{pid}",
                                dict(zip(evaluacion_md.CAMPOS_PIEZA, valores)))
    if md is None:
        return False
    ruta_md.write_text(md, encoding="utf-8")
    return True
