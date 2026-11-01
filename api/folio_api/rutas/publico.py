"""Archivos de las piezas listas para publicar, para que Instagram los descargue (folio.publicacion).

Es la única ruta que la web deja pasar sin contraseña (web/proxy.ts), así que solo sirve con una firma
válida y sin caducar (folio.publicacion.enlaces), y solo de informes/<fecha>/publicar/.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from folio.publicacion import enlaces
from folio_api.dependencias import Contexto, contexto

router = APIRouter()


# GET y HEAD: Buffer pregunta con HEAD el tipo y el tamaño antes de descargar el vídeo; con solo GET respondía
# 405 y Buffer rechazaba el borrador («Video could not be read from its URL», 2/11)
@router.api_route("/api/publico/{caduca}/{firma}/{fecha}/{pieza}/{archivo}", methods=["GET", "HEAD"], include_in_schema=False)
def publico(caduca: int, firma: str, fecha: str, pieza: str, archivo: str, ctx: Contexto = Depends(contexto)):
    ruta = f"{fecha}/{pieza}/{archivo}"
    if not enlaces.valida(ctx.cfg.clave_enlaces or "", caduca, firma, ruta):
        raise HTTPException(404)
    destino = ctx.cfg.dir_informes / fecha / "publicar" / pieza / archivo
    if not destino.is_file():
        raise HTTPException(404)
    return FileResponse(destino, media_type="video/mp4" if archivo.endswith(".mp4") else "image/jpeg")
