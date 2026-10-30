import pytest

from folio import ilustracion


def test_sanear_quita_lo_peligroso():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" width="5" onload="alert(1)">'
           '<script>alert(1)</script><style>*{}</style><text x="1">Hola</text>'
           '<image href="http://x/y.png"/><rect x="1" y="1" width="5" height="5" fill="#E4432A" onclick="x()"/>'
           '<circle cx="5" cy="5" r="2" fill="url(http://malo)"/><g transform="rotate(10)"><path d="M0 0 L5 5"/></g></svg>')
    limpio = ilustracion.sanear(svg)
    for malo in ("script", "style", "text", "image", "onload", "onclick", "url(", "Hola", 'width="5" onload'):
        assert malo not in limpio
    assert 'viewBox="0 0 1080 600"' in limpio and "<rect" in limpio and "<path" in limpio and 'fill="#E4432A"' in limpio


def test_sanear_rechaza_lo_que_no_es_svg():
    with pytest.raises(ilustracion.SVGInvalido):
        ilustracion.sanear("<html><body/></html>")
    with pytest.raises(ilustracion.SVGInvalido):
        ilustracion.sanear("no es xml")
    with pytest.raises(ilustracion.SVGInvalido):
        ilustracion.sanear('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
