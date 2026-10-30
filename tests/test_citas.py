"""Citas literales: solo pasan las que aparecen letra por letra en el texto del libro."""

import httpx

from folio import guion
from folio.libros.citas import verificador_google_books
from folio.libros.fuentes import GoogleBooks
from folio.modelos import CitaVerificada

from datos import ELECCION, FUENTES, LIBRO, guion_valido

CITA = "el mal puede ser obra de gente corriente"


class GBFalso:
    """Devuelve el fragmento que se le dé para cada autor buscado."""
    def __init__(self, fragmento, autores=("Hannah Arendt",)):
        self.fragmento, self.autores, self.buscadas = fragmento, list(autores), []

    def buscar_frase_en_texto(self, frase, autor):
        self.buscadas.append((frase, autor))
        return [{"id": "vol1", "titulo": "Eichmann en Jerusalén", "autores": self.autores, "fragmento": self.fragmento}]


def test_verificador_exige_la_frase_literal_y_el_autor():
    ok = verificador_google_books(GBFalso(f"… y sostiene que {CITA.upper()}, sin más.…"))(CITA, [LIBRO])
    assert ok and ok.volumen_google == "vol1" and ok.autor == "Hannah Arendt"
    # La sinopsis (o una paráfrasis) no vale
    assert verificador_google_books(GBFalso("Un estudio sobre la banalidad del mal."))(CITA, [LIBRO]) is None
    # La frase en un libro de otro autor tampoco
    assert verificador_google_books(GBFalso(CITA, autores=["Otra Persona"]))(CITA, [LIBRO]) is None


def test_google_books_busca_la_frase_por_autor_y_limpia_el_fragmento():
    def responder(req):
        q = req.url.params["q"]
        assert q == f'"{CITA}" inauthor:"arendt"'
        return httpx.Response(200, json={"items": [{"id": "v9", "volumeInfo": {"title": "T", "authors": ["Hannah Arendt"]},
                                                    "searchInfo": {"textSnippet": "dice que <b>el mal</b> &quot;puede&quot;"}}]})
    gb = GoogleBooks(httpx.Client(transport=httpx.MockTransport(responder)), "clave")
    assert gb.buscar_frase_en_texto(CITA, "arendt") == [
        {"id": "v9", "titulo": "T", "autores": ["Hannah Arendt"], "fragmento": 'dice que el mal "puede"'}]


def _con_cita(texto=CITA):
    g = guion_valido()
    g.diapositivas[2].texto = f"Arendt lo escribió en *Eichmann en Jerusalén*: «{texto}»."
    return g


def test_validar_acepta_solo_las_citas_encontradas(cfg):
    from folio.verificacion_texto import normalizar
    g = _con_cita()
    assert any("ni una cita encontrada" in e for e in guion.validar(cfg, g, [LIBRO], FUENTES))
    assert guion.validar(cfg, g, [LIBRO], FUENTES, frozenset({normalizar(CITA)})) == []
    corta = _con_cita("el mal")
    assert any("tiene 2 palabras" in e for e in guion.validar(cfg, corta, [LIBRO], FUENTES, frozenset({"el mal"})))
    dos = _con_cita()
    dos.diapositivas[3].texto = f"Y añade: «{CITA}»."
    assert any("2 citas literales" in e for e in guion.validar(cfg, dos, [LIBRO], FUENTES, frozenset({normalizar(CITA)})))


class LLMGuiones:
    def __init__(self, cfg, guiones):
        self.cfg, self.guiones, self.mensajes = cfg, list(guiones), []

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        self.mensajes.append(mensajes)
        return self.guiones.pop(0), []


def test_escribir_devuelve_las_citas_verificadas(cfg):
    verificar = lambda frase, libros: CitaVerificada(texto=frase, libro="Eichmann en Jerusalén", autor="Hannah Arendt",
                                                     volumen_google="vol1", fragmento=frase) if frase == CITA else None
    g, avisos, citas = guion.escribir(LLMGuiones(cfg, [_con_cita()]), "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO], verificar)
    assert [c.texto for c in citas] == [CITA] and not avisos


def test_cita_no_encontrada_pide_parafrasear_y_se_reintenta(cfg):
    llm = LLMGuiones(cfg, [_con_cita("una frase que el libro no contiene en absoluto"), guion_valido()])
    g, avisos, citas = guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO], lambda f, l: None)
    assert citas == [] and "Rechazado en el intento 1" in avisos[0]
    assert "ni una cita encontrada en su texto" in llm.mensajes[-1][-1]["content"]


def test_sin_red_la_cita_no_pasa(cfg):
    def roto(frase, libros):
        raise httpx.ConnectError("sin red")
    llm = LLMGuiones(cfg, [_con_cita(), guion_valido()])
    _, avisos, citas = guion.escribir(llm, "p1", ELECCION, [(FUENTES[0], "Texto")], [LIBRO], roto)
    assert citas == [] and any("No se pudo verificar la cita" in a for a in avisos)
