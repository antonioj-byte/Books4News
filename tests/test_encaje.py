"""La foto de la noticia, de tamaño desde el chat (7/11: «¿cómo que no puede cambiar el tamaño? permitamos que eso pase»)."""
from PIL import Image

from folio import edicion, render
from folio.imagenes import libres
from folio.modelos import Arte, Pieza

from datos import ELECCION, LIBRO, guion_valido


def _accion(**k):
    base = dict(tipo="formato", enfoque_x=50, enfoque_y=50, composicion="", consultas=[], escena="", persona="", estilo="",
                material="", como="", destacado="", antetitulo="", acento="", libro="", autor="", sin_castellano="",
                editorial="", isbn="", desde=0)
    return edicion.AccionImagen(**{**base, **k})


def test_el_chat_cambia_el_encaje_y_el_render_lo_pinta(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    p = Pieza(id="2026-11-07-1", fecha="2026-11-07", estado="propuesta", historia_id="h1", eleccion=ELECCION, n_medios=3,
              libros=[LIBRO], guion=guion_valido(), arte=Arte(tono="reflexivo", recurso="foto", portada="sangre"))
    d = libres.dir_imagenes(cfg.dir_cache(p.fecha))
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 1600), (90, 90, 90)).save(d / f"{p.id}-noticia.jpg")
    libres.guardar_metadatos(libres.ImagenLibre(archivo="material:x", pagina="", url="", ancho=1200, alto=1600, licencia="",
                                                licencia_url=None, autor="", descripcion="", libre=True, motivo="",
                                                local=f"{p.id}-noticia.jpg"), f"{p.id}-noticia", cfg.dir_cache(p.fecha))
    pl = render.Plantillas(cfg)
    assert "imagen--arriba" in pl.html_diapositiva(p, 2)
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, _accion(encaje="entera"))
    assert nueva.arte.encaje_noticia == "entera" and "entera" in nota
    assert "imagen--entera" in pl.html_diapositiva(nueva, 2)
    nueva, _ = edicion.aplicar_imagen(None, cfg, nueva, _accion(encaje="sangre"))
    assert "imagen--sangre" in pl.html_diapositiva(nueva, 2)
    nueva, _ = edicion.aplicar_imagen(None, cfg, nueva, _accion(encaje="arriba"))
    assert nueva.arte.encaje_noticia is None and "imagen--arriba" in pl.html_diapositiva(nueva, 2)
    assert edicion.aplicar_imagen(None, cfg, p, _accion(encaje="enorme"))[0] is None
