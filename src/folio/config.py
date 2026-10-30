"""Configuración: YAML de config/ + variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

RAIZ = Path(__file__).resolve().parents[2]


Esfuerzo = Literal["low", "medium", "high", "xhigh", "max"]


class _Seccion(BaseModel):
    """Sección de config/pipeline.yaml. Una clave desconocida es un error al cargar (antes de gastar
    nada), no un KeyError a mitad de la ejecución. Se puede leer también por clave (seccion["x"])."""
    model_config = ConfigDict(extra="forbid")

    def __getitem__(self, clave: str):
        return getattr(self, clave)

    def get(self, clave: str, defecto=None):
        return getattr(self, clave, defecto)


class Ingesta(_Seccion):
    ventana_horas: int
    timeout_s: float
    concurrencia_llm: int


class Agrupacion(_Seccion):
    modelo_embeddings: str
    umbral_similitud: float
    umbral_fusion: float | None = None
    min_medios: int


class Seleccion(_Seccion):
    historias_al_jefe: int
    elegidas: int
    reserva: int


class Exclusion(_Seccion):
    dias_historias: int
    dias_libros: int
    umbral_historia_repetida: float


class SeleccionTextos(_Seccion):
    min_textos: int = 3
    margen: float = 0.06
    bonus_acceso: dict[str, float] = Field(default_factory=lambda: {"abierto": 0.02, "parcial": 0.01, "muro": 0.0})


class Guion(_Seccion):
    max_textos: int
    max_caracteres_texto: int
    reintentos: int
    diapositivas_por_defecto: int
    palabras_max_diapositiva: int
    palabras_max_portada: int
    max_diapositivas_actualidad: int
    posicion_max_primer_libro: int
    pie_min_palabras: int
    pie_max_palabras: int


class Dev(_Seccion):
    modelo: str = "claude-haiku-5-5"


class VarianteAB(_Seccion):
    modelo: str
    esfuerzo: Esfuerzo


class AB(_Seccion):
    control: str
    reutilizar_control: bool = True
    variantes: dict[str, VarianteAB]

    @model_validator(mode="after")
    def _control_existe(self):
        if self.control not in self.variantes:
            raise ValueError(f"ab.control «{self.control}» no está entre ab.variantes")
        return self


class ConfigPipeline(_Seccion):
    """config/pipeline.yaml, tipado."""
    modelos: dict[str, str]
    dev: Dev = Field(default_factory=Dev)
    esfuerzo: dict[str, Esfuerzo]
    precios: dict[str, list[float]] = Field(default_factory=dict)  # entrada, salida[, lectura de caché]
    ingesta: Ingesta
    agrupacion: Agrupacion
    seleccion: Seleccion
    exclusion: Exclusion
    seleccion_textos: SeleccionTextos = Field(default_factory=SeleccionTextos)
    guion: Guion
    ab: AB | None = None

    @model_validator(mode="after")
    def _coherente(self):
        sin_esfuerzo = set(self.modelos) - set(self.esfuerzo)
        if sin_esfuerzo:
            raise ValueError(f"etapas sin esfuerzo en «esfuerzo»: {', '.join(sorted(sin_esfuerzo))}")
        for modelo, precios in self.precios.items():
            if len(precios) not in (2, 3):
                raise ValueError(f"precios de {modelo}: se esperan 2 o 3 valores (entrada, salida[, lectura de caché])")
        return self


@dataclass
class Fuente:
    medio: str
    url: str
    idioma: str
    acceso: str  # abierto | parcial | muro


@dataclass
class Config:
    pipeline: ConfigPipeline
    fuentes: list[Fuente]
    raiz: Path = RAIZ
    anthropic_api_key: str | None = None
    google_books_api_key: str | None = None
    openlibrary_contact: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def dir_prompts(self) -> Path:
        return self.raiz / "prompts"

    @property
    def dir_persistente(self) -> Path:
        """Dónde viven los datos que cambian (base de datos, cachés, informes). En local, la raíz
        del repositorio; en un despliegue, el volumen que indique FOLIO_DATOS (p. ej. /datos)."""
        return Path(os.environ["FOLIO_DATOS"]) if os.getenv("FOLIO_DATOS") else self.raiz

    @property
    def dir_datos(self) -> Path:
        return self.dir_persistente / "data"

    @property
    def dir_informes(self) -> Path:
        return self.dir_persistente / "informes"

    @property
    def ruta_db(self) -> Path:
        return self.dir_datos / "folio.db"

    def dir_cache(self, fecha: str) -> Path:
        return self.dir_datos / "cache" / fecha

    def modelo(self, paso: str) -> str:
        return self.pipeline.modelos[paso]

    def esfuerzo(self, paso: str) -> str:
        return self.pipeline.esfuerzo[paso]

    @property
    def user_agent(self) -> str:
        contacto = f" ({self.openlibrary_contact})" if self.openlibrary_contact else ""
        return f"FolioLateral/0.1{contacto}"


def perfil_dev(cfg: Config) -> Config:
    """Copia de la configuración con el modelo barato y esfuerzo bajo en todas las etapas.

    Sirve para depurar la tubería (validación, verificación, informe) sin gastar Opus; la
    calidad del texto que sale no dice nada de la de producción."""
    import copy
    dev = copy.deepcopy(cfg)
    dev.pipeline.modelos = {etapa: dev.pipeline.dev.modelo for etapa in dev.pipeline.modelos}
    dev.pipeline.esfuerzo = {etapa: "low" for etapa in dev.pipeline.esfuerzo}
    return dev


def ultima_fecha_con_seleccion(cfg: Config) -> str | None:
    """La fecha más reciente con una selección guardada en data/cache/."""
    fechas = sorted(p.parent.name for p in (cfg.dir_datos / "cache").glob("*/seleccion.json"))
    return fechas[-1] if fechas else None


def _clave_anthropic() -> str | None:
    """ANTHROPIC_API_KEY si existe; si no, FOLIO_ANTHROPIC_API_KEY (entornos que filtran la primera)."""
    return _limpia("ANTHROPIC_API_KEY") or _limpia("FOLIO_ANTHROPIC_API_KEY")


def _limpia(nombre: str) -> str | None:
    """Valor de una variable sin espacios ni saltos de línea alrededor (habituales al pegar una clave en
    un panel: un salto de línea final hace que el cliente HTTP falle con un «Connection error» engañoso)."""
    return (os.getenv(nombre) or "").strip() or None


def cargar(raiz: Path = RAIZ) -> Config:
    load_dotenv(raiz / ".env")
    pipeline = ConfigPipeline.model_validate(
        yaml.safe_load((raiz / "config" / "pipeline.yaml").read_text(encoding="utf-8")))
    fuentes_raw = yaml.safe_load((raiz / "config" / "fuentes.yaml").read_text(encoding="utf-8"))
    fuentes = [Fuente(**f) for f in fuentes_raw["fuentes"]]
    return Config(
        pipeline=pipeline,
        fuentes=fuentes,
        raiz=raiz,
        anthropic_api_key=_clave_anthropic(),
        google_books_api_key=_limpia("GOOGLE_BOOKS_API_KEY"),
        openlibrary_contact=_limpia("OPENLIBRARY_CONTACT"),
    )
