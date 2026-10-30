import httpx

from folio import imagenes, retratos


def _img(licencia, libre=False):
    return imagenes.ImagenLibre(archivo="commons:File:x.jpg", pagina="", url="", ancho=1200, alto=1600,
                                licencia=licencia, licencia_url=None, autor="A", descripcion="", libre=libre, motivo="sa")


def test_variantes_del_nombre():
    assert retratos.variantes("Anna  Politkóvskaya") == ["Anna Politkóvskaya", "Anna Politkovskaya"]
    assert retratos.variantes("Simon Winchester") == ["Simon Winchester"]


def test_cc_by_sa_solo_si_se_permite():
    assert not retratos.licencia_retrato(_img("CC BY-SA 4.0"), False).libre
    assert retratos.licencia_retrato(_img("CC BY-SA 4.0"), True).libre
    assert not retratos.licencia_retrato(_img("CC BY-NC-SA 2.0"), True).libre
    assert not retratos.licencia_retrato(_img("Copyrighted"), True).libre


def test_archivo_en_commons_desde_wikidata():
    def responder(req):
        assert "query" in req.url.params and "Simon Winchester" in req.url.params["query"]
        return httpx.Response(200, json={"results": {"bindings": [{"img": {
            "value": "http://commons.wikimedia.org/wiki/Special:FilePath/Simon_Winchester%202018.jpg"}}]}})
    with httpx.Client(transport=httpx.MockTransport(responder)) as c:
        assert retratos.archivo_en_commons("Simon Winchester", c) == "Simon Winchester 2018.jpg"
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"results": {"bindings": []}}))) as c:
        assert retratos.archivo_en_commons("Nadie", c) is None
