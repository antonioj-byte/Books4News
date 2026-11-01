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
    ventana_horas_editorial: int = 72   # los medios del libro publican menos
    timeout_s: float
    concurrencia_llm: int
    embeddings_de_dia: bool = True     # 2/11: la lectura periódica calcula los embeddings de los artículos nuevos


class Agrupacion(_Seccion):
    modelo_embeddings: str
    umbral_similitud: float
    umbral_fusion: float | None = None
    min_medios: int
    # Carril editorial: titulares cortos en muchos idiomas; sin fusión, un umbral más estricto
    umbral_similitud_editorial: float = 0.88


class Seleccion(_Seccion):
    historias_al_jefe: int
    historias_editoriales: int = 12     # contexto del mundo del libro para el jefe de cultura
    elegidas: int
    reserva: int
    buscar_balda: bool = True   # 2/11: libros reales de la misma balda para las propuestas de actualidad (folio.balda)
    puente_minimo: int = Field(default=3, ge=1, le=5)   # 2/11: propuestas con un puente peor se quedan fuera (evaluador de puentes)
    puente_para_escribir: int = Field(default=4, ge=1, le=5)  # la que se escribe sola tiene que llegar a esto
    # Mesa del día (31/10, a petición del usuario): propuestas por formato y cuántas se escriben solas
    # (las primeras por preferencia); el resto espera a que se pulse «Proceder» en la web
    reparto: dict[Literal["lateral", "dialogo", "edicion", "curiosidad", "recomendado"], int] = Field(
        default_factory=lambda: {"lateral": 2, "dialogo": 2, "edicion": 2})
    desarrollar_al_inicio: int = Field(default=1, ge=0)
    # Novedad (31/10, a petición del usuario): solo libros publicados en los últimos N años (primera edición
    # o edición española); los anteriores se descartan al verificar
    antiguedad_libros: int = Field(default=2, ge=0)
    solo_con_edicion_es: bool = True   # 2/11 (a petición del usuario): todos los libros, con edición en castellano verificada
    # Cajón de curiosidades (1/11, a petición del usuario): una historia del mundo del libro sin percha
    # (config/cajon_curiosidades.yaml) no vuelve a ofrecerse al jefe hasta pasados estos días
    dias_curiosidades: int = Field(default=90, ge=0)
    # La nevera (2/11, a petición del usuario: «busca 3 nuevas al día para hacer nevera»)
    nevera_por_dia: int = Field(default=3, ge=0)


class Catalogo(_Seccion):
    """Formato «recomendado» (1/11): novedades de las editoriales independientes (config/editoriales_independientes.yaml),
    leídas en todostuslibros.com con cortesía (una petición cada `pausa_s` s)."""
    meses: int = 6                      # novedades de los últimos 6 meses
    candidatos: int = 20                # libros que pasan al jefe de cultura
    max_por_editorial: int = 1          # por turnos: cada día empieza por editoriales distintas
    editoriales_por_dia: int = 25       # páginas de novedades que se refrescan al día como mucho
    refresco_dias: int = 7              # las novedades de cada editorial se leen una vez por semana
    de_fondo_por_vuelta: int = 6        # 2/11: editoriales caducadas que refresca cada vuelta de la lectura periódica (folio leer)
    pausa_s: float = Field(default=1.2, ge=1.0)


class Radar(_Seccion):
    """Radar del libro (1/11): temas del mundo del libro sin desarrollar, que se escriben con un clic."""
    activo: bool = True
    max_temas: int = 8
    historias: int = 32                 # historias del carril editorial que se resumen y ve el radar


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
    palabras_max_subtitulo: int = 22
    max_citas: int = 1                  # citas literales del libro, solo si se verifican en su texto
    palabras_cita: tuple[int, int] = (4, 30)
    max_diapositivas_actualidad: int
    posicion_max_primer_libro: int
    pie_min_palabras: int
    pie_max_palabras: int
    # 2/11 (a petición del usuario: «no entiendo este copy si no conoces la obra»): un modelo barato lee el guion
    # como alguien sin contexto y, si algo no se entiende, el guionista lo reescribe una vez
    lector_sin_contexto: bool = True
    prensa_del_libro: int = Field(default=3, ge=0)   # 2/11: en mundo del libro y recomendado, hasta N artículos de prensa sobre el libro (0 = no se busca)


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


class RetratoGenerado(_Seccion):
    """Retrato del autor generado con IA a partir de su foto libre (folio.imagenes.retrato_generado)."""
    activo: bool = False
    # Estilos de la casa (prompts/retrato_generado.md), alternados en el día en este orden
    estilos: list[Literal["low_poly", "voxel", "dithering", "render_2000"]] = Field(
        default_factory=lambda: ["low_poly", "voxel", "dithering", "render_2000"], min_length=1)
    aspecto: Literal["traditional_3_4", "portrait_2_3", "square_1_1"] = "traditional_3_4"
    espera_max_s: int = Field(default=180, gt=0)
    max_por_dia: int = Field(default=5, ge=0)
    # Estilos según el tono de la pieza (31/10): rota solo entre los de su tono que estén en `estilos`;
    # una lista vacía es «sin retrato generado» (la foto). Un tono que no esté aquí rota entre todos.
    por_tono: dict[Literal["grave", "sereno", "reflexivo", "ironico", "luminoso"],
                   list[Literal["low_poly", "voxel", "dithering", "render_2000"]]] = Field(default_factory=dict)


class Esquema(_Seccion):
    activo: bool = True
    max_por_dia: int = Field(default=3, ge=0)     # ilustraciones de Magnific por día (unos 25 créditos cada una)
    aspecto: Literal["traditional_3_4", "portrait_2_3", "square_1_1", "widescreen_16_9", "classic_4_3"] = "classic_4_3"
    espera_max_s: int = Field(default=240, gt=0)


class IlustracionEditorial(_Seccion):
    activo: bool = True
    max_por_dia: int = Field(default=3, ge=0)     # piezas ilustradas por día (cada variante, unos 25 créditos)
    variantes: int = Field(default=2, ge=1, le=4) # escenas que se dibujan por pieza; el director elige una
    espera_max_s: int = Field(default=240, gt=0)
    # Modelo de Magnific (2/11, elegido por el usuario tras comparar: «usamos Flux 2 Pro»); Seedream 4.5, de reserva
    modelo: Literal["flux_2_pro", "seedream_4_5"] = "flux_2_pro"
    creditos_imagen: int = Field(default=25, ge=0)   # para el panel de gasto: la API no da el coste


class Friso(_Seccion):
    """La banda superior de las tres fichas de «Tres libros» (2/11, opción B elegida por el usuario): una ilustración
    que cruza las tres diapositivas de libro."""
    activo: bool = True
    max_por_dia: int = Field(default=3, ge=0)


class Arte(_Seccion):
    # Composiciones de portada que puede elegir el director de arte. La ilustración vectorial
    # dibujada por el modelo se desactivó el 31/10: el resultado parece clip-art.
    portadas: list[Literal["sangre", "banda", "caja", "neon", "ilustracion", "circulo", "collage"]] = Field(
        default_factory=lambda: ["sangre", "banda", "caja", "neon"])
    # Retrato del autor (Wikidata + Commons) en la portada y junto a la cubierta
    retratos: bool = True
    # Casi todos los retratos de Commons son CC BY-SA: la imagen derivada se publica con la misma licencia
    retratos_cc_by_sa: bool = False
    # Si Commons no tiene retrato, la foto de la ficha del autor en la web de su editorial (folio.imagenes.prensa)
    fotos_editoriales: bool = True
    retrato_generado: RetratoGenerado = Field(default_factory=RetratoGenerado)
    # Recursos de la diapositiva de actualidad sin foto ni cifra (elegidos el 31/10). Si el que propone
    # el director de arte no está aquí o le faltan datos, se usa el primero de la lista que los tenga.
    sin_foto: list[Literal["golpe", "gigante", "teletipo", "collage"]] = Field(
        default_factory=lambda: ["golpe", "gigante", "teletipo", "collage"])
    # Infografías de la diapositiva de la idea (31/10) y la ilustración técnica de Magnific del «esquema»
    infografias: list[Literal["linea", "mapa", "esquema"]] = Field(default_factory=lambda: ["linea", "mapa", "esquema"])
    esquema: Esquema = Field(default_factory=lambda: Esquema())
    # Ilustración editorial de la pieza (B1), que cruza la portada y la noticia (B6); el buscador de la
    # portada (B2) y el mapa de la idea dibujado como tres salas (B4)
    ilustracion_editorial: IlustracionEditorial = Field(default_factory=lambda: IlustracionEditorial())
    friso: Friso = Field(default_factory=lambda: Friso())
    buscador: bool = True
    buscador_max_por_dia: int = Field(default=1, ge=0)   # 2/11 (a petición del usuario): recurso opcional, «queda muy recargado»
    mapa_ilustrado: bool = False
    # Lo que va en el pie, también en las diapositivas (1/11): colofón final con fuentes, ficha y créditos (A),
    # sello de ficha verificada en la del libro (B) y los medios que cuentan la noticia (C)
    colofon: bool = True
    impulsado_por: bool = True        # «Impulsado por» con el logo de Alighieria bajo la ficha del colofón (2/11)
    sello_verificacion: bool = False
    medios_en_noticia: bool = True   # hasta que haya una ilustración de las salas elegida por el usuario
    # Tonos en los que la portada en vídeo lleva la interferencia (M10)
    interferencia: list[Literal["grave", "sereno", "reflexivo", "ironico", "luminoso"]] = Field(default_factory=lambda: ["ironico"])


class Gasto(_Seccion):
    # Magnific no devuelve el coste por la API: medido en su panel el 31/10 (16.000 créditos por 16 €)
    magnific_creditos_imagen: float = 25
    magnific_euros_credito: float = 0.001
    busqueda_web_usd: float = 0.01        # cada búsqueda web del servidor de Anthropic (10 $ por 1.000)


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
    catalogo: Catalogo = Field(default_factory=Catalogo)
    radar: Radar = Field(default_factory=Radar)
    guion: Guion
    arte: Arte = Field(default_factory=Arte)
    gasto: Gasto = Field(default_factory=Gasto)
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
    carril: str = "actualidad"   # actualidad | editorial (mundo del libro, config/fuentes_editoriales.yaml)
    tier: int | None = None      # en el carril editorial: 1 = medio de referencia


@dataclass
class Config:
    pipeline: ConfigPipeline
    fuentes: list[Fuente]
    raiz: Path = RAIZ
    anthropic_api_key: str | None = field(default=None, repr=False)   # secreto: fuera del repr (salidas de pytest, registros)
    google_books_api_key: str | None = field(default=None, repr=False)   # secreto: fuera del repr (salidas de pytest, registros)
    openlibrary_contact: str | None = None
    magnific_api_key: str | None = field(default=None, repr=False)   # secreto: fuera del repr (salidas de pytest, registros)
    # Publicación en Instagram (folio.publicacion): token de la cuenta de Folio, su id (opcional: se pide a
    # la API), la URL pública de la web y la clave con que se firman los enlaces de los archivos
    instagram_token: str | None = field(default=None, repr=False)   # secreto: fuera del repr (salidas de pytest, registros)
    instagram_usuario: str | None = None
    url_publica: str | None = None
    clave_enlaces: str | None = field(default=None, repr=False)   # secreto: fuera del repr (salidas de pytest, registros)
    # Programación en Buffer (folio.publicacion.buffer): clave de la API y, si hay más de un canal de
    # Instagram en la cuenta, el id del de Folio
    buffer_clave: str | None = field(default=None, repr=False)   # secreto: fuera del repr (salidas de pytest, registros)
    buffer_canal: str | None = None
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
    dev.pipeline.arte.retrato_generado.activo = False      # tampoco se pagan retratos generados
    dev.pipeline.arte.esquema.activo = False               # ni ilustraciones de esquema (Magnific)
    dev.pipeline.arte.ilustracion_editorial.activo = False # ni ilustraciones editoriales
    dev.pipeline.arte.friso.activo = False                 # ni frisos de «Tres libros»
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
    ruta_editoriales = raiz / "config" / "fuentes_editoriales.yaml"
    if ruta_editoriales.exists():
        editoriales = yaml.safe_load(ruta_editoriales.read_text(encoding="utf-8"))["fuentes"]
        fuentes += [Fuente(**f, carril="editorial") for f in editoriales]
    return Config(
        pipeline=pipeline,
        fuentes=fuentes,
        raiz=raiz,
        anthropic_api_key=_clave_anthropic(),
        google_books_api_key=_limpia("GOOGLE_BOOKS_API_KEY"),
        openlibrary_contact=_limpia("OPENLIBRARY_CONTACT"),
        magnific_api_key=_limpia("MAGNIFIC_API_KEY"),
        instagram_token=_limpia("INSTAGRAM_TOKEN"),
        instagram_usuario=_limpia("INSTAGRAM_USER_ID"),
        url_publica=_limpia("FOLIO_URL_PUBLICA"),
        clave_enlaces=_limpia("FOLIO_CLAVE_ENLACES"),
        buffer_clave=_limpia("BUFFER_API_KEY"),
        buffer_canal=_limpia("BUFFER_CHANNEL_ID"),
    )
