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
    # 3: gasto en servicios de pago (1/11): un apunte por llamada a Anthropic y por imagen nueva de Magnific
    """
    CREATE TABLE gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,                  -- UTC, ISO
        fecha TEXT NOT NULL,               -- día local (FOLIO_ZONA) del gasto
        servicio TEXT NOT NULL,            -- anthropic | magnific
        concepto TEXT NOT NULL,            -- etapa (seleccion, guion, arte…) o tipo de imagen
        modelo TEXT,
        unidades REAL NOT NULL DEFAULT 0,  -- tokens (Anthropic) o créditos (Magnific)
        coste REAL NOT NULL DEFAULT 0,
        moneda TEXT NOT NULL,              -- USD | EUR
        detalle TEXT,
        ejecucion_id INTEGER               -- solo en los apuntes cargados de ejecuciones anteriores al registro
    );
    CREATE INDEX gastos_fecha ON gastos (fecha);
    CREATE TABLE gastos_inicio (ts TEXT NOT NULL);
    INSERT INTO gastos_inicio (ts) VALUES (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));
    """,
    # 4: memoria del feedback (1/11): patrones que salen de las evaluaciones y ediciones, con su propuesta de regla
    """
    CREATE TABLE memoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creado_en TEXT NOT NULL,
        actualizado_en TEXT NOT NULL,
        patron TEXT NOT NULL,              -- lo que se repite, en una frase
        evidencia TEXT NOT NULL,           -- JSON: [«pieza: qué pasó»]
        veces INTEGER NOT NULL DEFAULT 1,  -- en cuántos análisis ha salido
        propuesta TEXT NOT NULL,           -- la regla que se propone
        destino TEXT NOT NULL,             -- dónde iría: jefe_cultura, guionista, director_arte, formatos, codigo
        estado TEXT NOT NULL DEFAULT 'propuesta',  -- propuesta | aceptada | rechazada | aplicada
        nota TEXT NOT NULL DEFAULT ''
    );
    """,
    # 5: la memoria guarda también lo decidido en las conversaciones de trabajo (origen «conversacion», con su
    # clave estable en config/memoria_conversacion.yaml) y cada análisis del feedback, para el análisis semanal (2/11)
    """
    ALTER TABLE memoria ADD COLUMN origen TEXT NOT NULL DEFAULT 'feedback';
    ALTER TABLE memoria ADD COLUMN clave TEXT;
    CREATE UNIQUE INDEX memoria_clave ON memoria (clave) WHERE clave IS NOT NULL;
    CREATE TABLE memoria_analisis (
        ts TEXT NOT NULL,
        origen TEXT NOT NULL,              -- manual (botón o comando) | semanal
        piezas INTEGER NOT NULL,
        patrones INTEGER NOT NULL,
        coste_usd REAL NOT NULL,
        aviso TEXT NOT NULL DEFAULT ''
    );
    """,
]


class Patron(BaseModel):
    id: int
    creado_en: str
    actualizado_en: str
    patron: str
    evidencia: list[str]
    veces: int
    propuesta: str
    destino: str
    estado: str
    nota: str = ""
    origen: str = "feedback"           # feedback (análisis de la web) | conversacion (decidido en una sesión)
    clave: str | None = None


class Gasto(BaseModel):
    ts: str
    fecha: str
    servicio: str
    concepto: str
    modelo: str | None = None
    unidades: float
    coste: float
    moneda: str
    detalle: str | None = None


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

    # --- Memoria del feedback ------------------------------------------------------------

    def patrones(self) -> list[Patron]:
        filas = self.db.execute("SELECT * FROM memoria ORDER BY estado = 'propuesta' DESC, veces DESC, creado_en DESC, id DESC").fetchall()
        return [Patron(**{**dict(f), "evidencia": json.loads(f["evidencia"])}) for f in filas]

    def guardar_patron(self, patron: str, evidencia: list[str], propuesta: str, destino: str, existente: int | None = None) -> int:
        """Un patrón nuevo, o uno que ya estaba y vuelve a salir (se suma la evidencia y una vez más)."""
        ahora = _ahora()
        with self._transaccion() as db:
            if existente:
                f = db.execute("SELECT evidencia, veces FROM memoria WHERE id = ?", (existente,)).fetchone()
                if f:
                    todas = list(dict.fromkeys(json.loads(f["evidencia"]) + evidencia))
                    db.execute("UPDATE memoria SET evidencia = ?, veces = ?, actualizado_en = ?, propuesta = ? WHERE id = ?",
                               (json.dumps(todas, ensure_ascii=False), f["veces"] + 1, ahora, propuesta, existente))
                    return existente
            c = db.execute("INSERT INTO memoria (creado_en, actualizado_en, patron, evidencia, propuesta, destino) VALUES (?, ?, ?, ?, ?, ?)",
                           (ahora, ahora, patron, json.dumps(evidencia, ensure_ascii=False), propuesta, destino))
            return c.lastrowid

    def decidir_patron(self, pid: int, estado: str, nota: str = "") -> None:
        with self._transaccion() as db:
            db.execute("UPDATE memoria SET estado = ?, nota = ?, actualizado_en = ? WHERE id = ?", (estado, nota, _ahora(), pid))

    def importar_conversacion(self, entradas: list[dict]) -> int:
        """Lo decidido en las conversaciones de trabajo, como patrones «aplicada» (idempotente por clave: si el
        texto cambia en el archivo se actualiza, el estado no se toca). Las de conversación que ya no están en el
        archivo se quitan: una regla sustituida no puede seguir en la memoria junto a la nueva (2/11, «ilustración
        apagada» seguía al lado de «mejorarla»). Devuelve cuántas son nuevas."""
        nuevas = 0
        with self._transaccion() as db:
            claves = [e["clave"] for e in entradas]
            db.execute(f"DELETE FROM memoria WHERE origen = 'conversacion' AND clave NOT IN ({','.join('?' * len(claves))})"
                       if claves else "DELETE FROM memoria WHERE origen = 'conversacion'", claves)
            for e in entradas:
                evidencia = json.dumps(e["evidencia"], ensure_ascii=False)
                f = db.execute("SELECT id FROM memoria WHERE clave = ?", (e["clave"],)).fetchone()
                if f:
                    db.execute("UPDATE memoria SET patron = ?, propuesta = ?, destino = ?, evidencia = ? WHERE id = ?",
                               (e["patron"], e["propuesta"], e["destino"], evidencia, f["id"]))
                    continue
                ts = f"{e['fecha']}T12:00:00+00:00"
                db.execute("INSERT INTO memoria (creado_en, actualizado_en, patron, evidencia, propuesta, destino, estado, "
                           "origen, clave) VALUES (?, ?, ?, ?, ?, ?, 'aplicada', 'conversacion', ?)",
                           (ts, ts, e["patron"], evidencia, e["propuesta"], e["destino"], e["clave"]))
                nuevas += 1
        return nuevas

    def registrar_analisis(self, origen: str, piezas: int, patrones: int, coste_usd: float, aviso: str = "") -> None:
        with self._transaccion() as db:
            db.execute("INSERT INTO memoria_analisis VALUES (?, ?, ?, ?, ?, ?)",
                       (_ahora(), origen, piezas, patrones, round(coste_usd, 4), aviso))

    def ultimo_analisis(self) -> dict | None:
        f = self.db.execute("SELECT * FROM memoria_analisis ORDER BY ts DESC LIMIT 1").fetchone()
        return dict(f) if f else None

    def feedback(self, desde: str) -> list[dict]:
        """Lo que ha dicho y hecho quien edita desde `desde` (AAAA-MM-DD), por pieza: evaluación, ediciones a mano
        (antes y después), peticiones del chat y si se descartó."""
        out = []
        piezas = self.db.execute(
            "SELECT p.ejecucion_id, p.pieza_id, p.estado, e.fecha FROM piezas p JOIN ejecuciones e ON e.id = p.ejecucion_id "
            "WHERE e.fecha >= ? ORDER BY e.fecha, p.pieza_id", (desde,)).fetchall()
        for f in piezas:
            eid, pid = f["ejecucion_id"], f["pieza_id"]
            versiones = self.db.execute("SELECT n, origen, descripcion, datos FROM versiones WHERE ejecucion_id = ? AND pieza_id = ? ORDER BY n",
                                        (eid, pid)).fetchall()
            ev = self.evaluacion(eid, pid)
            pedidos = [m.texto for m in self.chat(eid, pid) if m.rol == "usuario"]
            ediciones = []
            for anterior, v in zip(versiones, versiones[1:]):
                if v["origen"] != "manual":
                    continue
                a, b = Pieza.model_validate_json(anterior["datos"]), Pieza.model_validate_json(v["datos"])
                for da, db_ in zip(a.guion.diapositivas if a.guion else [], b.guion.diapositivas if b.guion else []):
                    if (da.texto, da.subtitulo) != (db_.texto, db_.subtitulo):
                        ediciones.append({"diapositiva": f"{db_.n} ({db_.tipo})", "antes": da.texto, "despues": db_.texto})
            if not (ev or pedidos or ediciones or f["estado"] == "descartada"):
                continue
            ultima = Pieza.model_validate_json(versiones[-1]["datos"]) if versiones else None
            out.append({"pieza": pid, "fecha": f["fecha"], "estado": f["estado"],
                        "formato": ultima.eleccion.formato if ultima else None,
                        "titular": ultima.guion.diapositivas[0].texto if ultima and ultima.guion else (ultima.eleccion.titular if ultima else ""),
                        "evaluacion": ev[0].model_dump() if ev else None, "pedidos_chat": pedidos, "ediciones": ediciones})
        return out

    # --- Gasto -----------------------------------------------------------------------

    def apuntar_gasto(self, g: Gasto) -> None:
        with self._transaccion() as db:
            db.execute("INSERT INTO gastos (ts, fecha, servicio, concepto, modelo, unidades, coste, moneda, detalle) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (g.ts, g.fecha, g.servicio, g.concepto, g.modelo, g.unidades, g.coste, g.moneda, g.detalle))

    def gastos(self, desde: str) -> list[Gasto]:
        """Los apuntes desde la fecha `desde` (AAAA-MM-DD), del más antiguo al más reciente."""
        filas = self.db.execute("SELECT ts, fecha, servicio, concepto, modelo, unidades, coste, moneda, detalle "
                                "FROM gastos WHERE fecha >= ? ORDER BY ts", (desde,)).fetchall()
        return [Gasto(**dict(f)) for f in filas]

    def inicio_gastos(self) -> str:
        return self.db.execute("SELECT ts FROM gastos_inicio").fetchone()["ts"]

    def importar_gastos_historicos(self) -> int:
        """Carga el gasto en Anthropic de las ejecuciones anteriores al registro (de las trazas que
        guardaba cada informe), una vez. Las posteriores ya dejan sus apuntes al gastar."""
        inicio = self.inicio_gastos()
        hechas = {f[0] for f in self.db.execute("SELECT DISTINCT ejecucion_id FROM gastos WHERE ejecucion_id IS NOT NULL")}
        n = 0
        for f in self.db.execute("SELECT id, fecha, generado_en, informe FROM ejecuciones WHERE generado_en < ?", (inicio,)).fetchall():
            if f["id"] in hechas:
                continue
            trazas = json.loads(f["informe"]).get("trazas") or []
            with self._transaccion() as db:
                for t in trazas:
                    if not t.get("coste_usd"):
                        continue
                    db.execute("INSERT INTO gastos (ts, fecha, servicio, concepto, modelo, unidades, coste, moneda, detalle, ejecucion_id) "
                               "VALUES (?, ?, 'anthropic', ?, ?, ?, ?, 'USD', ?, ?)",
                               (f["generado_en"], f["fecha"], t["paso"].split(":")[0], t.get("modelo"),
                                sum(t.get(k) or 0 for k in ("tokens_entrada", "tokens_salida", "tokens_cache_escritura", "tokens_cache_lectura")),
                                t["coste_usd"], t["paso"], f["id"]))
                    n += 1
        return n

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
