"""Configuración: YAML de config/ + variables de entorno (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]


@dataclass
class Fuente:
    medio: str
    url: str
    idioma: str
    acceso: str  # abierto | parcial | muro


@dataclass
class Config:
    pipeline: dict
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
    def dir_datos(self) -> Path:
        return self.raiz / "data"

    @property
    def dir_informes(self) -> Path:
        return self.raiz / "informes"

    @property
    def ruta_db(self) -> Path:
        return self.dir_datos / "folio.db"

    def dir_cache(self, fecha: str) -> Path:
        return self.dir_datos / "cache" / fecha

    def modelo(self, paso: str) -> str:
        return self.pipeline["modelos"][paso]

    def esfuerzo(self, paso: str) -> str:
        return self.pipeline["esfuerzo"][paso]

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
    barato = dev.pipeline.get("dev", {}).get("modelo", "claude-haiku-5-5")
    dev.pipeline["modelos"] = {etapa: barato for etapa in dev.pipeline["modelos"]}
    dev.pipeline["esfuerzo"] = {etapa: "low" for etapa in dev.pipeline["esfuerzo"]}
    return dev


def ultima_fecha_con_seleccion(cfg: Config) -> str | None:
    """La fecha más reciente con una selección guardada en data/cache/."""
    fechas = sorted(p.parent.name for p in (cfg.dir_datos / "cache").glob("*/seleccion.json"))
    return fechas[-1] if fechas else None


def _clave_anthropic() -> str | None:
    """ANTHROPIC_API_KEY si existe; si no, FOLIO_ANTHROPIC_API_KEY (entornos que filtran la primera)."""
    return os.getenv("ANTHROPIC_API_KEY") or os.getenv("FOLIO_ANTHROPIC_API_KEY") or None


def cargar(raiz: Path = RAIZ) -> Config:
    load_dotenv(raiz / ".env")
    pipeline = yaml.safe_load((raiz / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    fuentes_raw = yaml.safe_load((raiz / "config" / "fuentes.yaml").read_text(encoding="utf-8"))
    fuentes = [Fuente(**f) for f in fuentes_raw["fuentes"]]
    return Config(
        pipeline=pipeline,
        fuentes=fuentes,
        raiz=raiz,
        anthropic_api_key=_clave_anthropic(),
        google_books_api_key=os.getenv("GOOGLE_BOOKS_API_KEY") or None,
        openlibrary_contact=os.getenv("OPENLIBRARY_CONTACT") or None,
    )
