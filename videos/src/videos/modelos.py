"""Esquemas: lo que devuelve Claude (…LLM) y el proyecto de un vídeo, un JSON por vídeo con estado por etapa y plano."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Rol = Literal["gancho", "tension", "desarrollo", "giro", "cierre"]
EstadoEtapa = Literal["pendiente", "en_curso", "propuesta", "aprobada", "bloqueado", "hecha", "desfasada", "fallida"]


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Salidas de Claude ─────────────────────────────────────────────────────────────────────────────────────────────

class NotasLLM(BaseModel):
    sorpresa: int = Field(description="De 1 a 10: cuánto contradice lo que el espectador da por hecho")
    utilidad: int = Field(description="De 1 a 10: cuánto puede aplicarlo a su vida esta semana")
    polemica: int = Field(description="De 1 a 10: cuánta gente sensata discreparía y querría decirlo")
    visualidad: int = Field(description="De 1 a 10: cuántas imágenes concretas y potentes sugiere")


class ConceptoLLM(BaseModel):
    titulo: str = Field(description="Título del concepto, de 3 a 8 palabras")
    idea: str = Field(description="La idea en una frase, tal como se la contarías a un amigo")
    gancho: str = Field(description="La frase de los primeros 2 segundos del vídeo: como mucho 7 palabras")
    por_que: str = Field(description="Por qué genera conversación: qué creencia toca, qué discusión abre, a quién se lo mandarías")
    pasaje: str = Field(description="Pasaje del libro que lo sostiene, copiado letra por letra, de 15 a 60 palabras, sin cortes ni puntos suspensivos")
    capitulo: int = Field(description="Número `n` del capítulo donde está el pasaje")
    notas: NotasLLM


class CandidatosLLM(BaseModel):
    conceptos: list[ConceptoLLM]


class ValoracionLLM(BaseModel):
    indice: int = Field(description="Índice del candidato (empieza en 0)")
    veredicto: Literal["elegido", "descartado"]
    motivo: str = Field(description="Una frase: por qué entra o por qué no")
    notas: NotasLLM = Field(description="Tus notas, no las del autor del candidato")


class CriticaLLM(BaseModel):
    valoraciones: list[ValoracionLLM] = Field(description="Una por candidato; los elegidos, en orden de preferencia")


class JuezGanchoLLM(BaseModel):
    nota: int = Field(description="De 1 a 10")
    curiosidad: int = Field(description="De 1 a 10: ¿abre una pregunta que obliga a quedarse?")
    concrecion: int = Field(description="De 1 a 10: ¿es concreto y específico, no genérico?")
    sin_contexto: int = Field(description="De 1 a 10: ¿se entiende sin saber nada del libro?")
    motivo: str = Field(description="Qué le falta o qué lo hace funcionar, en una frase")
    reescritura: str = Field(description="Una versión mejor, como mucho 7 palabras (igual que la original si ya es de 9 o 10)")


class PlanoLLM(BaseModel):
    rol: Rol
    locucion: str = Field(description="Lo que dice la voz en este plano")
    pantalla: str = Field(description="Texto en pantalla, como mucho 8 palabras; vacío si no lleva")
    visual: str = Field(description="Qué se ve: una imagen concreta, sin texto ni rótulos dentro de la imagen")
    movimiento: str = Field(description="Movimiento de cámara o animación (p. ej. «zoom lento hacia la mano», «travelling lateral»)")
    duracion_estimada: float = Field(description="Segundos estimados de voz")
    cita: str = Field(description="Si este plano cita el libro: el texto literal citado; si no, vacío")


class GuionLLM(BaseModel):
    titulo: str
    planos: list[PlanoLLM]


class RespuestaChatLLM(BaseModel):
    respuesta: str = Field(description="Lo que has hecho o lo que contestas, en una o dos frases")
    guion: GuionLLM | None = Field(description="El guion entero revisado, o null si no cambia")


class SalidaLibroLLM(BaseModel):
    """Un solo esquema para todas las llamadas que llevan el libro: el esquema de salida forma parte del prefijo que
    se cachea, así que con un esquema por paso cada paso volvía a escribir la caché del libro entero (7/11, medido:
    el guion pagó 22.822 tokens de escritura en vez de leerlos). Cada prompt dice qué campo rellenar."""
    conceptos: list[ConceptoLLM] | None = Field(description="Los candidatos, si te los piden; si no, null")
    guion: GuionLLM | None = Field(description="El guion entero, si te lo piden o si lo has cambiado; si no, null")
    respuesta: str | None = Field(description="Lo que contestas a quien edita, si te escribe; si no, null")


class RespuestaChatConceptosLLM(BaseModel):
    respuesta: str = Field(description="Lo que contestas, en una o dos frases")
    otra_ronda: bool = Field(description="true si hay que proponer conceptos nuevos")
    indicaciones: str = Field(description="Si hay otra ronda: qué tienen que tener los nuevos, en una frase")


class EstiloLLM(BaseModel):
    nombre: str
    tecnica: str
    paleta: list[str]
    luz: str
    encuadres: str
    prohibido: list[str]
    prefijo: str
    sufijo: str
    musica: str


class EscenaLLM(BaseModel):
    id: str
    escena: str = Field(description="En inglés, de 15 a 45 palabras")
    animacion: str = Field(description="En inglés, si el plano es un clip animado; si no, vacío")


class EscenasLLM(BaseModel):
    escenas: list[EscenaLLM]


class RevisionLLM(BaseModel):
    tiene_texto: bool
    donde: str = Field(description="Dónde está el texto; vacío si no hay")


# ── El proyecto ───────────────────────────────────────────────────────────────────────────────────────────────────

class Etapa(BaseModel):
    estado: EstadoEtapa = "pendiente"
    actualizado: str = Field(default_factory=ahora)
    trabajo: str | None = None
    error: str | None = None


class Pasaje(BaseModel):
    texto: str
    capitulo: int
    titulo_capitulo: str = ""
    pagina: str | None = None
    verificado: bool = False


class Notas(BaseModel):
    sorpresa: int
    utilidad: int
    polemica: int
    visualidad: int

    @property
    def media(self) -> float:
        return round((self.sorpresa + self.utilidad + self.polemica + self.visualidad) / 4, 1)


class JuicioGancho(BaseModel):
    original: str
    nota: int
    motivo: str
    intentos: int = 1
    historial: list[dict] = Field(default_factory=list)


class Concepto(BaseModel):
    id: str
    ronda: int
    titulo: str
    idea: str
    gancho: str
    por_que: str
    pasaje: Pasaje
    notas: Notas
    notas_critico: Notas | None = None
    motivo_critico: str = ""
    juicio_gancho: JuicioGancho | None = None
    prompt: str = ""


class Cita(BaseModel):
    texto: str
    capitulo: int
    pagina: str | None = None


class Plano(BaseModel):
    id: str
    rol: Rol
    locucion: str
    pantalla: str = ""
    visual: str
    movimiento: str
    duracion_estimada: float
    cita: Cita | None = None


class VersionGuion(BaseModel):
    n: int
    concepto: str
    origen: Literal["guionista", "chat", "manual"]
    creado: str = Field(default_factory=ahora)
    titulo: str
    planos: list[Plano]
    avisos: list[str] = Field(default_factory=list)
    prompt: str = ""


class MensajeChat(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str
    etapa: Literal["conceptos", "guion"]
    creado: str = Field(default_factory=ahora)


class Estilo(BaseModel):
    id: str                      # collage, grabado, cine o propio
    nombre: str
    tecnica: str
    paleta: list[str]
    luz: str
    encuadres: str
    prohibido: list[str]
    prefijo: str
    sufijo: str
    musica: str
    descripcion: str = ""
    peticion: str = ""


class Palabra(BaseModel):
    t: str
    i: float
    f: float
    plano: str


class TiempoPlano(BaseModel):
    inicio: float
    fin: float


class Voz(BaseModel):
    modelo: str
    voz_id: str
    voz_nombre: str
    simulada: bool
    audio: str                  # relativo a la carpeta del proyecto (WAV, la fuente de verdad)
    audio_mp3: str
    duracion: float
    palabras: list[Palabra]
    planos: dict[str, TiempoPlano]
    huella: str                 # de las locuciones: si cambian, la voz queda desfasada
    version: int = 1
    creado: str = Field(default_factory=ahora)


class Variante(BaseModel):
    archivo: str
    semilla: int
    simulada: bool = False
    aviso: str = ""


class ImagenPlano(BaseModel):
    escena: str
    animacion: str = ""
    prompt: str
    variantes: list[Variante] = Field(default_factory=list)
    elegida: int | None = None
    clip: str | None = None
    clip_simulado: bool = False
    estado: Literal["pendiente", "generando", "lista", "elegida", "fallida"] = "pendiente"
    error: str | None = None


class Montaje(BaseModel):
    version: int
    archivo: str
    srt: str
    duracion: float
    con_musica: bool
    creado: str = Field(default_factory=ahora)


class Gasto(BaseModel):
    etapa: str
    servicio: str
    modelo: str = ""
    usd: float = 0.0
    detalle: str = ""
    creado: str = Field(default_factory=ahora)


class LibroInfo(BaseModel):
    tipo: str = "libro"          # libro, articulo, ensayo, texto o nota_de_voz (ver `fuente.TIPOS`)
    titulo: str
    autor: str
    formato: str
    archivo: str
    huella: str
    capitulos: list[dict]
    caracteres: int


class Proyecto(BaseModel):
    esquema: int = 1
    id: str
    creado: str = Field(default_factory=ahora)
    libro: LibroInfo
    etapas: dict[str, Etapa] = Field(default_factory=lambda: {k: Etapa() for k in
                                     ("ingesta", "conceptos", "guion", "estilo", "voz", "imagenes", "montaje")})
    conceptos: list[Concepto] = Field(default_factory=list)
    concepto_elegido: str | None = None
    guion: list[VersionGuion] = Field(default_factory=list)
    chat: list[MensajeChat] = Field(default_factory=list)
    gasto: list[Gasto] = Field(default_factory=list)
    libro_en_cache: str | None = None      # última vez que se mandó el libro con caché de 1 h (ISO)
    estilo: Estilo | None = None
    voz: Voz | None = None
    imagenes: dict[str, ImagenPlano] = Field(default_factory=dict)
    musica: str | None = None              # archivo de la cama musical, si la hay
    musica_activa: bool = False
    montajes: list[Montaje] = Field(default_factory=list)

    def concepto(self, cid: str) -> Concepto | None:
        return next((c for c in self.conceptos if c.id == cid), None)

    @property
    def guion_actual(self) -> VersionGuion | None:
        """La última versión del guion del concepto elegido."""
        return next((v for v in reversed(self.guion) if v.concepto == self.concepto_elegido), None)
