"""El Archivo (3/11, a petición del usuario: «¿cómo puedo ver el histórico? Puede interesar publicar o editar contenidos
ya hechos, pero que se quedan en nevera»): todas las piezas de todos los días, con en qué punto están y si siguen vigentes.
"""

from __future__ import annotations

from datetime import date

from folio.modelos import Pieza

# En qué punto está una pieza, para los filtros del Archivo
CATEGORIAS = ("nevera", "aprobada", "programada", "publicada", "pendiente", "descartada")
SIN_PERCHA = ("curiosidad", "recomendado")          # no dependen de una noticia: no caducan
DIAS_VIGENTE, DIAS_REVISAR = 7, 30


def categoria(p: Pieza, programada: bool) -> str:
    """«nevera»: escrita y sin publicar, aprobar ni descartar; las aprobadas que ya están en Buffer, «programada»."""
    if p.estado == "descartada":
        return "descartada"
    if p.estado == "publicada":
        return "publicada"
    if not p.guion or p.estado in ("pendiente", "fallida"):
        return "pendiente"
    if p.estado == "aprobada":
        return "programada" if programada else "aprobada"
    return "nevera"


def vigencia(p: Pieza, fecha: str, hoy: date | None = None) -> tuple[str, str]:
    """(clave, texto) de si la pieza sigue valiendo: «atemporal» (sin percha: historia editorial, recomendado, cajón,
    catálogo), «vigente», «revisar» (sus noticias tienen más de una semana: hay que poner las fechas al día) o «caducada»
    (más de un mes). Cuenta la noticia más reciente de sus fuentes; sin fechas, el día de la pieza."""
    hoy = hoy or date.today()
    if p.eleccion.formato in SIN_PERCHA or p.historia_id.startswith(("cajon-", "catalogo-")):
        return "atemporal", "Atemporal"
    fechas = [f.publicado for f in p.fuentes if f.publicado]
    try:
        mas_reciente = max(date.fromisoformat(x[:10]) for x in fechas) if fechas else date.fromisoformat(fecha)
    except ValueError:
        mas_reciente = date.fromisoformat(fecha)
    dias = (hoy - mas_reciente).days
    if dias <= DIAS_VIGENTE:
        return "vigente", "Vigente"
    if dias <= DIAS_REVISAR:
        return "revisar", f"Revisar fechas · {dias} días"
    return "caducada", f"Caducada · {dias} días"
