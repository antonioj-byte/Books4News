"""Render de las piezas: HTML por diapositiva con las plantillas de diseno/ y PNG de 1080×1350.

- textos: el texto que se pinta (cursivas, ficha de libros, remate, libro de cada diapositiva).
- medios: las imágenes tal como las carga el navegador y la composición real de la portada.
- plantillas: tokens → CSS y HTML de cada diapositiva.
- png: las capturas con Playwright.
"""

from folio.render.medios import Medios, como_uri
from folio.render.plantillas import Plantillas, cargar_tokens, css_tokens, dir_diseno, direcciones
from folio.render.png import _lanzar, renderizar
from folio.render.textos import (color_de_pieza, fecha_larga, ficha_libros, libro_de_diapositiva, texto_html,
                                 titular_con_remate)

__all__ = ["Medios", "Plantillas", "cargar_tokens", "color_de_pieza", "como_uri", "css_tokens", "dir_diseno",
           "direcciones", "fecha_larga", "ficha_libros", "libro_de_diapositiva", "renderizar", "texto_html",
           "titular_con_remate", "_lanzar"]
