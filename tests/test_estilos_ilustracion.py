"""El grabado se suma al collage (4/11): estilos por sección del prompt y alternancia en el día."""
from folio.imagenes import editorial, libres


def _ilustracion(cfg, dir_fecha, pid, estilo):
    libres.dir_imagenes(dir_fecha).mkdir(parents=True, exist_ok=True)
    img = libres.ImagenLibre(archivo=editorial.CLAVE, pagina="", url="", ancho=1440, alto=810, licencia="",
                             licencia_url=None, autor="Folio", descripcion="", libre=True, motivo="",
                             local=f"{pid}.jpg", fuente="", estilo=estilo)
    libres.guardar_metadatos(img, pid, dir_fecha)


def test_cada_estilo_es_su_seccion(cfg):
    collage, grabado = editorial.estilo(cfg), editorial.estilo(cfg, "grabado")
    assert "collage" in collage and "engraving" not in collage
    assert "engraving" in grabado and "## " not in grabado
    # el friso y la banda sustituyen estas frases del collage: siguen ahí
    assert "with points of interest on the left" in collage
    assert "No real or recognisable people; any human figures are anonymous." in collage


def test_se_alternan_en_el_dia_y_la_pieza_va_a_juego(cfg):
    d = cfg.dir_cache("2026-11-04")
    primero = editorial.estilo_de_pieza(cfg, "2026-11-04-1", d)
    _ilustracion(cfg, d, "2026-11-04-1", primero)
    segundo = editorial.estilo_de_pieza(cfg, "2026-11-04-2", d)
    assert {primero, segundo} == {"collage", "grabado"}
    # la noticia y lo que rehaga el chat, en el estilo de su pieza
    assert editorial.estilo_de_pieza(cfg, "2026-11-04-1-noticia", d) == primero
    assert editorial.estilo_de_pieza(cfg, "2026-11-04-1", d) == primero
    # al día siguiente empieza por el otro
    assert editorial.estilo_de_pieza(cfg, "2026-11-05-1", cfg.dir_cache("2026-11-05")) == segundo


def test_las_de_antes_eran_collage_y_un_solo_estilo_se_respeta(cfg):
    d = cfg.dir_cache("2026-11-04")
    _ilustracion(cfg, d, "2026-11-04-3", None)
    assert editorial.estilo_de_pieza(cfg, "2026-11-04-3", d) == "collage"
    cfg.pipeline.arte.ilustracion_editorial.estilos = ["collage"]
    assert editorial.estilo_de_pieza(cfg, "2026-11-04-9", d) == "collage"


def test_quita_el_marco_que_rodea_la_imagen_pero_no_el_suelo():
    from PIL import Image, ImageDraw
    escena = Image.new("RGB", (400, 200), (214, 36, 110))
    ImageDraw.Draw(escena).rectangle((200, 0, 400, 100), fill=(242, 225, 76))
    ImageDraw.Draw(escena).line((0, 150, 400, 160), fill=(0, 0, 0), width=3)
    con_marco = Image.new("RGB", (430, 230), (243, 239, 230))
    con_marco.paste(escena, (15, 15))
    assert editorial.quitar_marco(con_marco).size == (400, 200)
    # Un suelo liso solo abajo es parte de la escena: no se toca
    suelo = Image.new("RGB", (400, 240), (243, 239, 230))
    suelo.paste(escena.crop((0, 0, 400, 200)), (0, 0))
    assert editorial.quitar_marco(suelo).size == (400, 240)
