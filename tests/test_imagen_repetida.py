"""Una imagen de archivo usada no vuelve en los días siguientes (5/11, a petición del usuario: «me la ha hecho varias veces»)."""
import json

from folio.imagenes import libres


def _usar(cfg, fecha, pieza, archivo, url):
    carpeta = libres.dir_imagenes(cfg.dir_cache(fecha))
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pieza}.json").write_text(json.dumps({"archivo": archivo, "url": url}), encoding="utf-8")


def test_las_de_los_ultimos_dias_no_vuelven_salvo_las_de_la_misma_pieza(cfg):
    _usar(cfg, "2026-11-03", "2026-11-03-4", "europeana:/prensa", "https://iiif.ejemplo/prensa.jpg")
    _usar(cfg, "2026-10-01", "2026-10-01-1", "europeana:/vieja", "https://iiif.ejemplo/vieja.jpg")
    _usar(cfg, "2026-11-05", "2026-11-05-2", "europeana:/propia", "https://iiif.ejemplo/propia.jpg")
    _usar(cfg, "2026-11-05", "2026-11-05-2-retrato", "commons:File:Cara.jpg", "")
    _usar(cfg, "2026-11-04", "2026-11-04-1", "magnific:ilustracion", "")          # las ilustraciones no cuentan
    usadas = libres.usadas_recientes(cfg.dir_cache("2026-11-05"), 30, sin="2026-11-05-2")
    assert {"europeana:/prensa", "https://iiif.ejemplo/prensa.jpg"} <= usadas
    assert "europeana:/vieja" not in usadas                  # hace más de 30 días
    assert "europeana:/propia" not in usadas and "commons:File:Cara.jpg" not in usadas   # la pieza que se rehace
    assert "magnific:ilustracion" not in usadas
    assert libres.usadas_recientes(cfg.dir_cache("2026-11-05"), 0) == {"europeana:/propia", "https://iiif.ejemplo/propia.jpg", "commons:File:Cara.jpg"}
