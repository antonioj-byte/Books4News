"""La fuente de un vídeo: un libro, un artículo, un ensayo, un texto pegado o una nota de voz transcrita. Todo se
trata igual (secciones con su texto y su marca de lugar); cambia cómo se nombra y cómo se cita."""
from __future__ import annotations

TIPOS = {
    "libro": "un libro",
    "articulo": "un artículo",
    "ensayo": "un ensayo",
    "texto": "un texto",
    "nota_de_voz": "una nota de voz transcrita",
}
NOMBRES = {"libro": "Libro", "articulo": "Artículo", "ensayo": "Ensayo", "texto": "Texto", "nota_de_voz": "Nota de voz"}


def descripcion(tipo: str, titulo: str, autor: str) -> str:
    """«un libro: «Título», de Autora»; lo que leen los prompts en {{fuente}}."""
    base = TIPOS.get(tipo, "un texto")
    t = f"«{titulo}»" if titulo else ""
    a = f"de {autor}" if autor else ""
    return f"{base}: {', '.join(x for x in (t, a) if x)}" if (t or a) else base


def referencia(tipo: str, capitulo: int, pagina: str | None, varias_secciones: bool = True) -> str:
    """Cómo se cita un lugar de la fuente: capítulo y página en un libro, minuto en una nota de voz."""
    if tipo == "nota_de_voz":
        return f"min. {pagina}" if pagina else ""
    partes = []
    if varias_secciones and capitulo:
        partes.append(f"cap. {capitulo}" if tipo == "libro" else f"parte {capitulo}")
    if pagina:
        partes.append(f"pág. {pagina}")
    return ", ".join(partes)


def candidatos(caracteres: int) -> int:
    """Cuántos candidatos pedir según lo que da de sí la fuente: un artículo no da doce ideas."""
    if caracteres > 20000:
        return 12
    if caracteres > 6000:
        return 8
    return 6
