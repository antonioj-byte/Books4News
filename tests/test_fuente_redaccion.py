"""Un enlace que da la redacción, a las fuentes aunque no se pueda leer (7/11: «le pido que meta un link verificado
humanamente por mí y no me deja»; el FT tiene muro)."""
from folio import edicion, render
from folio.modelos import Arte, Pieza

from datos import ELECCION, LIBRO, guion_valido
from test_encaje import _accion

FT = "https://www.ft.com/content/5e49f0f3-f66e-44fd-989a-c1fdeec9b433"


def test_la_fuente_de_la_redaccion_entra_en_el_colofon(cfg):
    (cfg.raiz / "diseno").symlink_to(render.dir_diseno(type(cfg)(pipeline={}, fuentes=[])).resolve())
    p = Pieza(id="2026-11-07-1", fecha="2026-11-07", estado="propuesta", historia_id="h1", eleccion=ELECCION, n_medios=3,
              libros=[LIBRO], guion=guion_valido(), arte=Arte(tono="reflexivo", recurso="foto"))
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, _accion(tipo="fuente", fuente_url=FT + "."))
    f = nueva.fuentes[-1]
    assert f.url == FT and f.medio == "Financial Times" and f.redaccion and f.acceso == "muro"
    assert "Financial Times" in nota
    pl = render.Plantillas(cfg)
    assert "Financial Times" in pl.html_diapositiva(nueva, len(nueva.guion.diapositivas) + 1)   # el colofón
    assert edicion.aplicar_imagen(None, cfg, nueva, _accion(tipo="fuente", fuente_url=FT))[0] is None   # ya está
    sin_https = edicion.aplicar_imagen(None, cfg, p, _accion(tipo="fuente", fuente_url="ft.com/x"))[0]
    assert sin_https.fuentes[-1].url == "https://ft.com/x"                    # sin https, se le pone
    assert edicion.aplicar_imagen(None, cfg, p, _accion(tipo="fuente", fuente_url="no es un enlace"))[0] is None


def test_el_chat_corrige_la_firma_de_una_opinion(cfg):
    from folio import newsletter
    from test_newsletter import TEXTO, _guion
    f = newsletter.guardar_firmante(cfg, "Diego Prueba", "Director de producto")
    p = newsletter.a_pieza(cfg, _guion(), "2026-11-07-3", "2026-11-07", TEXTO, firma=f, formato=newsletter.OPINION)
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, _accion(tipo="firma", firma_cargo="Director de Producto"))
    assert nueva.firmante.cargo == "Director de Producto" and nueva.firmante.en_pieza and "Director de Producto" in nota
    assert "firma de la portada" in edicion._bloque_pieza(p)
