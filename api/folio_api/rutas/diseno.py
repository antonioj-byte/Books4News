"""El design system para la web."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from folio.render import cargar_tokens, css_tokens
from folio_api.dependencias import Contexto, contexto

router = APIRouter()


@router.get("/api/diseno/tokens.css", response_class=PlainTextResponse)
def tokens_css(ctx: Contexto = Depends(contexto)):
    """Variables CSS del design system, para que la web use los mismos colores y fuentes."""
    return PlainTextResponse(css_tokens(cargar_tokens(ctx.cfg)), media_type="text/css")
