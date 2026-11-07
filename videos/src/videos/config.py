"""Configuración de la beta: rutas, claves y modelos, todo por variables de entorno (`videos/.env` en local).

Es una herramienta aparte de Folio: no importa nada de `folio` ni toca su configuración.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]          # videos/
load_dotenv(RAIZ / ".env")

# Precios por millón de tokens: entrada, salida, lectura de caché. La escritura de caché de 1 h cuesta 2× la entrada.
PRECIOS = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


def _bool(nombre: str, defecto: bool = False) -> bool:
    v = os.environ.get(nombre)
    return defecto if v is None else v.strip().lower() in ("1", "true", "si", "sí", "yes")


@dataclass
class Config:
    datos: Path = field(default_factory=lambda: Path(os.environ.get("VIDEOS_DATOS", RAIZ / "data")))
    prompts: Path = RAIZ / "prompts"
    anthropic_api_key: str = field(default_factory=lambda: (os.environ.get("ANTHROPIC_API_KEY")
                                                            or os.environ.get("FOLIO_ANTHROPIC_API_KEY") or "").strip())
    magnific_api_key: str = field(default_factory=lambda: os.environ.get("MAGNIFIC_API_KEY", "").strip())
    elevenlabs_api_key: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", "").strip())
    # Modelos (claves de config, nunca a fuego en el resto del código)
    modelo_conceptos: str = field(default_factory=lambda: os.environ.get("VIDEOS_MODELO_CONCEPTOS", "claude-opus-5-5"))
    modelo_critico: str = field(default_factory=lambda: os.environ.get("VIDEOS_MODELO_CRITICO", "claude-opus-5-5"))
    modelo_gancho: str = field(default_factory=lambda: os.environ.get("VIDEOS_MODELO_GANCHO", "claude-opus-5-5"))
    modelo_guion: str = field(default_factory=lambda: os.environ.get("VIDEOS_MODELO_GUION", "claude-opus-5-5"))
    # Simulación: sin clave de un servicio, ese servicio va simulado; VIDEOS_SIMULADO=1 lo fuerza para los dos
    forzar_simulado: bool = field(default_factory=lambda: _bool("VIDEOS_SIMULADO"))

    @property
    def magnific_simulado(self) -> bool:
        return self.forzar_simulado or not self.magnific_api_key

    @property
    def elevenlabs_simulado(self) -> bool:
        return self.forzar_simulado or not self.elevenlabs_api_key

    @property
    def proyectos(self) -> Path:
        return self.datos / "proyectos"

    @property
    def cache(self) -> Path:
        return self.datos / "cache"

    @property
    def trabajos(self) -> Path:
        return self.datos / "trabajos"
