from io import BytesIO

from PIL import Image

from folio import arte
from folio.modelos import Infografia, Pieza, PropuestaArte, SinFoto

from datos import ELECCION, LIBRO, guion_valido


def _pieza():
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1",
                 eleccion=ELECCION, n_medios=3, libros=[LIBRO], guion=guion_valido())


def _propuesta(**cambios):
    datos = dict(tono="sereno", portada="circulo", suceso_con_victimas=False, recurso="foto", consultas=["court"], evitar=[],
                 cifra=None, cifra_rotulo=None, por_que="x", sin_foto=SinFoto(recurso="golpe"), infografia=Infografia(tipo="ninguna"))
    return PropuestaArte(**(datos | cambios))


def test_cifra_literal_de_la_actualidad():
    # La diapositiva de actualidad dice: «Un tribunal juzga a un funcionario que firmaba órdenes.»
    p = _propuesta(cifra="tribunal", cifra_rotulo="juzga a un funcionario")
    assert arte.validar_cifra(p, _pieza()) == [] and p.cifra == "tribunal"


def test_cifra_inventada_o_con_victimas_se_descarta():
    p = _propuesta(cifra="500 millones", cifra_rotulo="de euros")
    assert "no está" in arte.validar_cifra(p, _pieza())[0] and p.cifra is None
    p = _propuesta(cifra="tribunal", suceso_con_victimas=True)
    assert "víctimas" in arte.validar_cifra(p, _pieza())[0] and p.cifra is None


def test_rotulo_con_palabras_de_mas_se_descarta():
    p = _propuesta(cifra="tribunal", cifra_rotulo="juzga a un ministro corrupto")
    assert "Rótulo" in arte.validar_cifra(p, _pieza())[0]
    assert p.cifra == "tribunal" and p.cifra_rotulo is None


def test_hoja_de_contactos():
    hoja = Image.open(BytesIO(arte.hoja_de_contactos([Image.new("RGB", (800, 600), "red")] * 4)))
    assert hoja.size == (3 * 360, 2 * 360)


def test_antetitulo():
    assert arte.validar_antetitulo(" prensa y poder. ") == "PRENSA Y PODER"
    assert arte.validar_antetitulo("una etiqueta demasiado larga") is None
    assert arte.validar_antetitulo(None) is None


def test_remate_literal_al_final_del_titular():
    t = "Nóvaya Gazeta apaga la luz y Rusia pierde a quien la anotaba."
    assert arte.validar_remate("a quien la anotaba.", t) == "a quien la anotaba"
    assert arte.validar_remate("pierde a quien", t) is None          # no es el final
    assert arte.validar_remate("anotaba", t) is None                 # una sola palabra
    assert arte.validar_remate(t, t) is None                         # el titular entero


def test_el_retrato_es_del_autor_del_libro_principal_del_guion():
    from folio.modelos import LibroGuion
    otro = LIBRO.model_copy(update={"titulo": "Ficciones", "titulo_propuesto": "Ficciones", "autores": ["Jorge Luis Borges"], "olid": "OL1W"})
    p = _pieza()
    p.libros = [otro, LIBRO]                       # verificados en otro orden
    assert arte.autor_principal(p) == "Hannah Arendt"   # el guion lleva Eichmann en Jerusalén como principal
    p.guion.libros = [LibroGuion(titulo="Ficciones", autor="Jorge Luis Borges", editorial_espanola=None, traductor=None, edicion_original="x")]
    assert arte.autor_principal(p) == "Jorge Luis Borges"


def test_el_esquema_del_director_cabe_en_las_salidas_estructuradas():
    """Con un null en cada campo opcional anidado, la API rechazó el esquema («Schema is too complex»)."""
    import json
    assert json.dumps(PropuestaArte.model_json_schema()).count("anyOf") <= 6


def _imagenes_distintas():
    """Tres candidatas: dos distintas y una copia de la primera, más pequeña (como otra institución en Europeana)."""
    from folio.imagenes import libres
    a = Image.new("RGB", (1200, 900), "white")
    for x in range(0, 1200, 150):
        a.paste((0, 0, 0), (x, 0, x + 70, 900))
    b = Image.new("RGB", (1200, 900), "white")
    for y in range(0, 900, 120):
        b.paste((0, 0, 0), (0, y, 1200, y + 40))
    b.paste((90, 90, 90), (300, 200, 900, 700))
    copia = a.resize((900, 675))
    def cand(n):
        return libres.ImagenLibre(archivo=f"europeana:/{n}", pagina="", url=f"https://x/{n}.jpg", ancho=1200, alto=900,
                                  licencia="CC0", licencia_url=None, autor="A", descripcion=f"imagen {n}", libre=True, motivo="")
    return [(cand(1), a), (cand(2), b), (cand(3), copia)]


class _LLMEleccion:
    def __init__(self, cfg, **eleccion):
        self.cfg, self.eleccion, self.textos = cfg, eleccion, []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.textos.append(mensajes[0]["content"][1]["text"])
        datos = dict(elegida=1, personas_reconocibles=False, enfoque_x=50, enfoque_y=50, por_que="x") | self.eleccion
        return esquema(**datos), []


def _archivo(cfg, monkeypatch, registro, **eleccion):
    from folio.modelos import Arte
    monkeypatch.setattr(arte, "candidatas", lambda propuesta, excluir=(): _imagenes_distintas())
    a = Arte(tono="sereno", recurso="foto", registro=registro)
    llm = _LLMEleccion(cfg, **eleccion)
    arte._imagen_de_archivo(llm, cfg, _pieza(), "datos", _propuesta(), a, set(), cfg.dir_cache("2026-10-30"))
    return a, llm


def test_sin_cara_la_noticia_lleva_otra_imagen_de_archivo(cfg, monkeypatch):
    from folio.imagenes import libres
    a, llm = _archivo(cfg, monkeypatch, "archivo", segunda=2)
    assert "hace falta una segunda imagen para la noticia: sí" in llm.textos[0]
    assert a.imagen == "europeana:/1" and a.imagen_noticia == "europeana:/2" and a.credito_noticia
    assert libres.de_pieza("2026-10-30-1-noticia", cfg.dir_cache("2026-10-30")).archivo == "europeana:/2"
    # La misma imagen en otra copia no vale como segunda: la noticia va sin foto
    a, _ = _archivo(cfg, monkeypatch, "archivo", segunda=3)
    assert a.imagen_noticia is None and any("misma" in x for x in a.avisos)
    a, _ = _archivo(cfg, monkeypatch, "archivo", segunda=1)
    assert a.imagen_noticia is None
    # Con cara en la portada, no hace falta segunda
    a, llm = _archivo(cfg, monkeypatch, "foto_autor", segunda=2)
    assert a.imagen == "europeana:/1" and a.imagen_noticia is None and "segunda imagen para la noticia: no" in llm.textos[0]


def test_nunca_dos_caras(cfg, monkeypatch):
    a, llm = _archivo(cfg, monkeypatch, "retrato_ia", personas_reconocibles=True)
    assert a.imagen is None and any("nunca dos caras" in x for x in a.avisos)
    assert "ya lleva la cara de una persona: sí" in llm.textos[0]
    a, _ = _archivo(cfg, monkeypatch, "archivo", personas_reconocibles=True, segunda=2)
    assert a.imagen == "europeana:/1"            # sin cara de autor, una persona en la imagen de archivo vale


def test_misma_imagen():
    (_, a), (_, b), (_, copia) = _imagenes_distintas()
    assert arte.misma_imagen(a, copia) and not arte.misma_imagen(a, b)
