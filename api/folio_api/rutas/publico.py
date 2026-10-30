"""Archivos de las piezas listas para publicar, para que Instagram los descargue (folio.publicacion).

Es la única ruta que la web deja pasar sin contraseña (web/proxy.ts), así que solo sirve con una firma
válida y sin caducar (folio.publicacion.enlaces), y solo de informes/<fecha>/publicar/.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from folio.publicacion import enlaces
from folio_api.dependencias import Contexto, contexto

router = APIRouter()


@router.get("/api/publico/{caduca}/{firma}/{fecha}/{pieza}/{archivo}", include_in_schema=False)
def publico(caduca: int, firma: str, fecha: str, pieza: str, archivo: str, ctx: Contexto = Depends(contexto)):
    ruta = f"{fecha}/{pieza}/{archivo}"
    if not enlaces.valida(ctx.cfg.clave_enlaces or "", caduca, firma, ruta):
        raise HTTPException(404)
    destino = ctx.cfg.dir_informes / fecha / "publicar" / pieza / archivo
    if not destino.is_file():
        raise HTTPException(404)
    return FileResponse(destino, media_type="video/mp4" if archivo.endswith(".mp4") else "image/jpeg")
