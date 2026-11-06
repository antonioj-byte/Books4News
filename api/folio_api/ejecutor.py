"""Lanzar `folio run` desde la web: un proceso aparte (el pipeline carga 2 GB de embeddings y no
debe vivir en el servidor), una sola ejecución a la vez y su registro en el volumen de datos.

Una ejecución puede tener varios pasos seguidos (la diaria: el pipeline y después el render de PNG y
vídeo); si un paso falla, los siguientes no se lanzan."""

from __future__ import annotations

import json
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
    tipico_s: int | None = None        # lo que suele tardar este trabajo (mediana de los anteriores que acabaron bien)


class Trabajo(BaseModel):
    """Un trabajo en segundo plano, para los avisos del navegador (2/11, a petición del usuario: «un sistema de
    notificaciones que permita ver en el navegador cuando una tarea se ha acabado»)."""
    clave: str                         # «diaria», «fondo-del-mes», «memoria-analisis» o el id de la pieza
    nombre: str                        # cómo se enseña: «Tanda del fondo», «Pieza 2026-11-02-3»…
    en_marcha: bool
    codigo: int | None = None
    inicio: str | None = None
    fin: str | None = None
    ultima_linea: str = ""
    etapa: str | None = None           # el paso en curso, para la bandeja de trabajos (4/11)
    tipico_s: int | None = None


NOMBRES_TRABAJO = {"diaria": "Ejecución del día", "fondo-del-mes": "Tanda del fondo del mes",
                   "memoria-analisis": "Análisis de la memoria", "cinco-del-libro": "Cinco del libro",
                   "cinco-lista": "Cinco del libro: la lista", "newsletter": "La newsletter del jueves"}

MAX_DESARROLLOS = 3                    # «Proceder» a la vez (2/11): cada uno es un proceso aparte
YA_EN_MARCHA = "Esta pieza ya se está escribiendo"
# Cada registro acaba con esta línea al terminar. Uno sin ella es de un trabajo que se cortó (un despliegue reinicia la
# API y mata sus procesos): así el estado sobrevive al reinicio (revisión general, 2/11: la web lo daba por terminado)
FIN = "FIN: código "
# Y, justo antes, lo que tardó: de ahí sale «suele tardar» (4/11, usabilidad: la barra de la tarjeta de trabajo)
DURACION = "DURACION: "
# Lo que suele tardar cada tipo de trabajo si aún no hay ninguno terminado con su duración (segundos)
TIPICO_POR_DEFECTO = {"diaria": 300, "pieza": 150, "cinco-del-libro": 300, "cinco-lista": 30, "newsletter": 180, "fondo-del-mes": 900,
                      "memoria-analisis": 90, "tema": 90}
CANCELADO = "Cancelado por la redacción."
CODIGO_CANCELADO = -2
INTERRUMPIDO = "Interrumpido: la API se reinició (un despliegue) antes de que terminara. Vuelve a lanzarlo."


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
        fin = datetime.now(timezone.utc)
        cancelado = getattr(self, "cancelado", False)
        codigo = CODIGO_CANCELADO if cancelado else self.proceso.returncode
        salida.write(("\n" + CANCELADO if cancelado else "")
                     + f"\n{DURACION}{round((fin - datetime.fromisoformat(self.inicio)).total_seconds())}\n{FIN}{codigo}\n")
        salida.close()
        self.codigo_final = codigo
        self.fin = fin.isoformat(timespec="seconds")

    def cancelar(self) -> None:
        """6/11 («esto es ridículo, quizá debería haber opción de cancelar»): para el proceso y no lanza los pasos que
        quedaban."""
        self.cancelado = True
        self.pendientes = []
        if self.proceso.poll() is None:
            self.proceso.terminate()

    def vivo(self) -> bool:
        return self.proceso.poll() is None or self.fin is None

    def estado(self) -> EstadoEjecucion:
        return _estado(self.registro, self.vivo(), self.inicio, self.fin,
                       None if self.vivo() else getattr(self, "codigo_final", self.proceso.returncode))


class _Cancelado(Exception):
    pass


class _Hilo:
    """Un trabajo que corre en un hilo de la API (4/11, usabilidad: proponer un tema, replicar al jefe o escribir una
    propuesta del fondo ya no dependen de que la página siga abierta). Escribe su registro como los procesos (ETAPA,
    DURACION, FIN), así que se sigue igual, y deja su resultado en `<clave>.json`."""
    cuenta = False                     # no ocupa sitio de «Proceder»

    def __init__(self, registro: Path, nombre: str, fn):
        self.registro, self.nombre = registro, nombre
        self.registro.parent.mkdir(parents=True, exist_ok=True)
        self.registro.write_text("", encoding="utf-8")
        self.resultado_ruta = registro.with_suffix(".json")
        self.resultado_ruta.unlink(missing_ok=True)
        self.inicio, self.fin, self.codigo = datetime.now(timezone.utc).isoformat(timespec="seconds"), None, None
        threading.Thread(target=self._correr, args=(fn,), daemon=True).start()

    def _linea(self, texto: str) -> None:
        with self.registro.open("a", encoding="utf-8") as f:
            f.write(texto.rstrip("\n") + "\n")

    cancelado = False

    def _anunciar(self, etapa: str) -> None:
        if self.cancelado:                 # entre paso y paso: lo cancelado no sigue ni deja nada en la mesa
            raise _Cancelado()
        self._linea(f"ETAPA: {etapa}")

    def cancelar(self) -> None:
        """6/11: un hilo no se puede matar; se da por terminado ya (cancelado) y, cuando el paso en curso acabe, se para
        en el siguiente anuncio y no guarda su resultado."""
        if self.fin is not None:
            return
        self.cancelado = True
        fin = datetime.now(timezone.utc)
        self._linea(CANCELADO)
        self._linea(f"{DURACION}{round((fin - datetime.fromisoformat(self.inicio)).total_seconds())}")
        self._linea(f"{FIN}{CODIGO_CANCELADO}")
        self.codigo, self.fin = CODIGO_CANCELADO, fin.isoformat(timespec="seconds")

    def _correr(self, fn) -> None:
        codigo = 0
        try:
            resultado = fn(self._anunciar)
            if self.cancelado:
                return
            if resultado is not None:
                self.resultado_ruta.write_text(resultado.model_dump_json() if hasattr(resultado, "model_dump_json")
                                               else json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
        except _Cancelado:
            return
        except Exception as exc:       # el motivo, en una línea, como la última de un proceso que falla
            if self.cancelado:
                return
            codigo = 1
            self._linea(str(getattr(exc, "detail", None) or f"{type(exc).__name__}: {exc}"))
        fin = datetime.now(timezone.utc)
        self._linea(f"{DURACION}{round((fin - datetime.fromisoformat(self.inicio)).total_seconds())}")
        self._linea(f"{FIN}{codigo}")
        self.codigo, self.fin = codigo, fin.isoformat(timespec="seconds")

    def vivo(self) -> bool:
        return self.fin is None

    def estado(self) -> EstadoEjecucion:
        return _estado(self.registro, self.vivo(), self.inicio, self.fin, None if self.vivo() else self.codigo)


def _estado(registro: Path, en_marcha: bool, inicio, fin, codigo) -> EstadoEjecucion:
    lineas: list[str] = []
    etapa = None
    if registro.exists():
        todas = [l for l in registro.read_text(encoding="utf-8", errors="replace").splitlines()
                 if l.strip() and "Fetching" not in l]
        etapa = next((l.removeprefix("ETAPA: ") for l in reversed(todas) if l.startswith("ETAPA: ")), None)
        lineas = [l for l in todas if not l.startswith(("ETAPA: ", "TIEMPO: ", FIN, DURACION))][-12:]
        if not en_marcha and codigo is None:
            # Sin el trabajo en memoria (la API se reinició): el registro dice cómo acabó, o que se cortó
            final = next((l for l in reversed(todas) if l.startswith(FIN)), None)
            if final:
                codigo = int(final.removeprefix(FIN) or 1)
            else:
                codigo = -1
                lineas = [*lineas, INTERRUMPIDO][-12:]
            fin = fin or datetime.fromtimestamp(registro.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
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
        # El fondo del mes (2/11): el primer día del mes (o el primero en que esté vacío), después de la mesa, las seis
        # tandas; nunca hace fallar la diaria
        self.fondo_mensual = [sys.executable, "-m", "folio.cli", "fondo", "preparar", "--si-toca", "--tandas", "6"]
        self.diaria.append(self.fondo_mensual)
        self._trabajo: _Trabajo | None = None
        self._desarrollos: dict[str, _Trabajo] = {}
        self._cerrojo = threading.Lock()
        # La lectura periódica (folio leer, programador.Lector) reescribe data/lecturas.json y la caché de embeddings
        # que el pipeline lee: mientras lee, no se lanza el pipeline (ronda 3 de mejora, fiabilidad)
        self._leyendo = False

    def empezar_lectura(self) -> bool:
        """La lectura periódica pide turno: False si hay una ejecución del día en marcha (se salta la vuelta)."""
        with self._cerrojo:
            if self.ocupado():
                return False
            self._leyendo = True
            return True

    def acabar_lectura(self) -> None:
        with self._cerrojo:
            self._leyendo = False

    def motivo_ocupado(self) -> str | None:
        """Por qué no se puede lanzar ahora la ejecución del día (None si se puede)."""
        if self.ocupado():
            return "Ya hay una ejecución en marcha"
        if self.desarrollando():
            return "Se están escribiendo piezas con «Proceder»; prueba cuando acaben"
        if self._leyendo:
            return "Se están leyendo las noticias (lectura periódica); prueba en unos minutos"
        return None

    def lanzar(self, pasos: list[list[str]] | None = None) -> bool:
        """Lanza la ejecución del día (por defecto, solo el pipeline). False si ya hay una en marcha, si se están
        escribiendo piezas con «Proceder» (el pipeline reescribe las historias del día que ellas leen) o si la lectura
        periódica está a medias (reescribe las lecturas que el pipeline lee)."""
        pasos = pasos or [self.comando]
        with self._cerrojo:
            if self.motivo_ocupado():
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
                return YA_EN_MARCHA
            if pid not in NOMBRES_TRABAJO and self.desarrollando() >= MAX_DESARROLLOS:
                return f"Ya se están escribiendo {MAX_DESARROLLOS} piezas; prueba cuando acabe alguna"
            self._desarrollos[pid] = _Trabajo(self._registro_de(pid), pasos)
            return None

    def desarrollando(self) -> int:
        """Piezas escribiéndose con «Proceder». La tanda del fondo y la Memoria no cuentan: ni ocupan sitio de las
        piezas ni bloquean la ejecución del día con un mensaje que no es (revisión general, 2/11)."""
        return sum(1 for k, t in self._desarrollos.items() if t.vivo() and k not in NOMBRES_TRABAJO and getattr(t, "cuenta", True))

    def en_hilo(self, clave: str, nombre: str, fn) -> str | None:
        """Un trabajo corto de la API en segundo plano (`fn(progreso)` devuelve el resultado). None si lo lanza; si ya
        hay uno con esa clave en marcha, YA_EN_MARCHA."""
        with self._cerrojo:
            previo = self._desarrollos.get(clave)
            if previo and previo.vivo():
                return YA_EN_MARCHA
            self._desarrollos[clave] = _Hilo(self._registro_de(clave), nombre, fn)
            return None

    def resultado(self, clave: str) -> str | None:
        """El resultado (JSON) de un trabajo en hilo que acabó bien, si lo hay."""
        r = self._registro_de(clave).with_suffix(".json")
        return r.read_text(encoding="utf-8") if r.exists() else None

    def tipico(self, clave: str) -> int | None:
        """Lo que suele tardar este tipo de trabajo: la mediana de los anteriores que acabaron bien (sus registros
        guardan la duración); si aún no hay, un valor por defecto."""
        tipo = "diaria" if clave == "diaria" else clave if clave in NOMBRES_TRABAJO else "tema" if clave.startswith(("tema-", "fondo-")) else "pieza"
        if tipo == "diaria":
            registros = [self.registro]
        elif tipo == "pieza":
            raros = {self._registro_de(k).name for k in NOMBRES_TRABAJO}
            registros = [r for r in self.dir_desarrollos.glob("*.log") if r.name not in raros and not r.name.startswith(("tema-", "fondo-"))]
        elif tipo == "tema":
            registros = [*self.dir_desarrollos.glob("tema-*.log"), *self.dir_desarrollos.glob("fondo-*.log")]
        else:
            registros = [self._registro_de(clave)]
        duraciones = []
        for r in sorted(registros, key=lambda x: x.stat().st_mtime if x.exists() else 0)[-30:]:
            try:
                cola = r.read_text(encoding="utf-8", errors="replace").splitlines()[-4:]
            except OSError:
                continue
            d = next((l.removeprefix(DURACION) for l in cola if l.startswith(DURACION)), None)
            if d and f"{FIN}0" in cola and d.strip().isdigit():
                duraciones.append(int(d))
        if not duraciones:
            return TIPICO_POR_DEFECTO.get(tipo)
        duraciones.sort()
        return duraciones[len(duraciones) // 2]

    def en_marcha(self, pid: str) -> bool:
        t = self._desarrollos.get(pid)
        return bool(t and t.vivo())

    def _registro_de(self, pid: str) -> Path:
        return self.dir_desarrollos / ("".join(c if c.isalnum() or c in "-_" else "_" for c in pid) + ".log")

    def cancelar(self, clave: str) -> bool:
        """Cancela un trabajo en marcha de esta sesión de la API (la diaria, «Proceder», un tema…). False si no lo hay."""
        t = self._trabajo if clave == "diaria" else self._desarrollos.get(clave)
        if not t or not t.vivo():
            return False
        t.cancelar()
        return True

    def estado_desarrollo(self, pid: str) -> EstadoEjecucion | None:
        """El estado de un trabajo aparte; si no es de esta sesión de la API, lo que diga su registro (también
        «interrumpido» si se cortó en un despliegue). None si nunca se lanzó."""
        t = self._desarrollos.get(pid)
        if t:
            e = t.estado()
        else:
            r = self._registro_de(pid)
            if not r.exists():
                return None
            e = _estado(r, False, None, None, None)
        e.tipico_s = self.tipico(pid)
        return e

    def trabajos(self) -> list[Trabajo]:
        """La ejecución del día y los trabajos aparte («Proceder», fondo, memoria) de esta sesión de la API."""
        def de(clave: str, t: _Trabajo) -> Trabajo:
            e = t.estado()
            nombre = getattr(t, "nombre", None) or NOMBRES_TRABAJO.get(clave) or f"Pieza {clave} escrita («Proceder»)"
            return Trabajo(clave=clave, nombre=nombre, en_marcha=e.en_marcha, codigo=e.codigo, inicio=e.inicio, fin=e.fin,
                           ultima_linea=(e.ultimas_lineas or [""])[-1][:200], etapa=e.etapa, tipico_s=self.tipico(clave))
        out = [de("diaria", self._trabajo)] if self._trabajo else []
        return out + [de(k, t) for k, t in self._desarrollos.items()]

    def con_pipeline(self) -> bool:
        """Si lo que corre ahora es el pipeline del día (`folio run`), que reescribe las historias del día. Proceder,
        el render, la nevera y la Memoria no chocan con un tema de la redacción (2/11)."""
        return self.ocupado() and "run" in list(getattr(self._trabajo.proceso, "args", []) or [])

    def ocupado(self) -> bool:
        return bool(self._trabajo and self._trabajo.vivo())

    def estado(self) -> EstadoEjecucion:
        t = self._trabajo
        e = t.estado() if t else _estado(self.registro, False, None, None, None)
        e.tipico_s = self.tipico("diaria")
        return e
