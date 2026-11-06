"""El registro de formatos (4/11, refactorización pedida por el usuario: «igual conviene una acción de
refactorización»; la newsletter había heredado las reglas de las piezas con libro y la firma «Folio.» porque cada
formato era un caso especial repartido por el código).

Cada formato se declara aquí una vez: cómo se llama, cuántos libros lleva, si exige novedad, si caduca, de qué carril
sale, quién lo propone y si es «propio» (tiene su módulo, que lo escribe, lo ilustra y lo comprueba, con sus plantillas
y sus reglas, y no pasa por el director de arte ni por la comprobación general). El resto del código pregunta aquí en
vez de comparar nombres de formato. Un formato nuevo empieza por una entrada en `FORMATOS`.

Este módulo no importa nada de Folio: lo usan los modelos, el pipeline, el render, la API y la web (por la API).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Formato:
    id: str
    nombre: str                       # visible en la web: «Lectura lateral»
    en_frase: str                     # en una frase: «propuso una lectura lateral»
    en_prompt: str                    # en los prompts y el informe: «lectura lateral»
    libros: int = 1                   # los que lleva la pieza: 3 en «Tres libros»; 1 en los demás
    libro_obligatorio: bool = True    # sin libro verificado, ¿la pieza no sale?
    candidatos: tuple[int, int] = (3, 4)   # libros candidatos que tiene que proponer el jefe (mínimo, máximo)
    exige_novedad: bool = True        # solo libros de los últimos años (un perfil necesita la obra)
    atemporal: bool = False           # en el Archivo no caduca: no depende de una noticia
    carril: str | None = None         # el carril del que tiene que salir (y solo él), si no es de actualidad
    propone: str = "jefe_cultura"     # el rol que lo propone en la mesa
    friso: bool = False               # sus fichas de libro pueden llevar el friso ilustrado
    propio: str | None = None         # módulo que lo escribe entero (folio.<propio>): plantillas, reglas e ilustraciones
    firma_folio: bool = True          # el cierre acaba con la firma de Folio (la corrección mecánica la añade)
    noticia: bool = True              # tiene una noticia detrás (si no, la diapositiva de actualidad no lleva «Lo cuentan»)
    infografia: bool = True           # la idea puede llevar infografía («Tres libros», no: no cuenta nada que no cuenten ellos)


FORMATOS: dict[str, Formato] = {f.id: f for f in (
    Formato("lateral", "Lectura lateral", "una lectura lateral", "lectura lateral"),
    Formato("dialogo", "Diálogo con la actualidad", "un diálogo", "diálogo con la actualidad"),
    Formato("balda", "Tres libros", "tres libros", "tres libros", libros=3, candidatos=(3, 6), exige_novedad=False, friso=True,
            infografia=False),
    # 6/11 («en el caso de Asturias, no hay por qué hablar del libro: sirve con la propia noticia»): el libro, si lo hay
    Formato("edicion", "Mundo del libro", "una del mundo del libro", "mundo del libro", libro_obligatorio=False,
            candidatos=(0, 4), propone="editor_libro"),
    Formato("curiosidad", "Historia editorial", "una historia editorial", "historia editorial", libro_obligatorio=False,
            candidatos=(0, 4), atemporal=True, carril="cajon", propone="editor_libro"),
    Formato("recomendado", "Libro recomendado", "un libro recomendado", "libro recomendado", candidatos=(1, 4),
            atemporal=True, carril="catalogo", propone="editor_libro", noticia=False),
    Formato("radar", "Breve del mundo del libro", "un breve", "radar del libro", libro_obligatorio=False,
            propone="editor_libro"),
    Formato("noticia", "Noticia", "una noticia", "noticia", libro_obligatorio=False),
    Formato("ensayo", "Ensayo", "un ensayo", "ensayo", libro_obligatorio=False, atemporal=True),
    Formato("cinco", "Cinco del libro", "cinco del libro", "cinco del libro", libros=0, libro_obligatorio=False,
            propio="cinco", firma_folio=False),
    Formato("newsletter", "La newsletter del jueves", "la newsletter del jueves", "la newsletter del jueves", libros=0,
            libro_obligatorio=False, atemporal=True, propio="newsletter", firma_folio=False, propone="redaccion"),
)}

_DESCONOCIDO = FORMATOS["lateral"]


def de(formato: str | None) -> Formato:
    """La ficha del formato; uno desconocido (piezas viejas) se trata como una lectura lateral."""
    return FORMATOS.get(formato or "", _DESCONOCIDO)


def nombre(formato: str | None) -> str:
    return FORMATOS[formato].nombre if formato in FORMATOS else (formato or "")


# Los que no necesitan libro: la pieza sale aunque ninguno se verifique
SIN_LIBRO_OBLIGATORIO = tuple(f.id for f in FORMATOS.values() if not f.libro_obligatorio)
# Los que tienen su propio módulo (no pasan por el arte ni por la comprobación general del pipeline)
PROPIOS = tuple(f.id for f in FORMATOS.values() if f.propio)
# El carril del que tiene que salir cada formato que no es de actualidad
CARRIL_DEL_FORMATO = {f.id: f.carril for f in FORMATOS.values() if f.carril}
