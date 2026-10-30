"""Verificación de citas literales del libro.

Una cita solo entra en una pieza si aparece letra por letra (salvo mayúsculas, tildes y signos) en
el texto de un libro del mismo autor, según la búsqueda de texto completo de Google Books. Google
Books solo indexa el texto de una parte de los libros (sobre todo los de dominio público): de los
demás devuelve la sinopsis, así que sus citas no se pueden verificar y se rechazan.
"""

from __future__ import annotations

from typing import Callable

from folio.modelos import CitaVerificada, LibroVerificado
from folio.verificacion_texto import apellido, autor_coincide, normalizar

Verificador = Callable[[str, list[LibroVerificado]], CitaVerificada | None]


def verificador_google_books(gb) -> Verificador:
    """Verificador de citas sobre el cliente de Google Books (folio.libros.fuentes.GoogleBooks)."""
    def verificar(frase: str, libros: list[LibroVerificado]) -> CitaVerificada | None:
        objetivo = normalizar(frase)
        for libro in libros:
            for autor in libro.autores[:1]:
                for v in gb.buscar_frase_en_texto(frase, apellido(autor) or autor):
                    if autor_coincide(autor, v["autores"]) and objetivo and objetivo in normalizar(v["fragmento"]):
                        return CitaVerificada(texto=frase, libro=libro.titulo_propuesto, autor=autor,
                                              volumen_google=v["id"], fragmento=v["fragmento"])
        return None
    return verificar
