"""Fuentes que no son libros: texto pegado, artículos y notas de voz."""
import pytest

from videos import almacen, fuente, libro as lib, transcripcion
from conftest import CAPITULO_2


def test_texto_pegado_es_una_fuente(cfg):
    p = almacen.crear(cfg, almacen.PEGADO, CAPITULO_2.encode(), "La atención", "Luis Gil", "articulo")
    assert p.libro.tipo == "articulo" and len(p.libro.capitulos) == 1 and p.libro.capitulos[0]["titulo"] == "La atención"
    texto = lib.texto_para_modelo(almacen.libro(cfg, p.id))
    assert texto.startswith('<fuente tipo="articulo"')


def test_texto_demasiado_corto(cfg):
    with pytest.raises(ValueError):
        almacen.crear(cfg, almacen.PEGADO, "Muy poco texto.".encode(), tipo="texto")


def test_descripcion_y_referencias():
    assert fuente.descripcion("libro", "El descanso", "Ana Pérez") == "un libro: «El descanso», de Ana Pérez"
    assert fuente.descripcion("nota_de_voz", "", "") == "una nota de voz transcrita"
    assert fuente.referencia("libro", 3, "64") == "cap. 3, pág. 64"
    assert fuente.referencia("articulo", 1, None, varias_secciones=False) == ""
    assert fuente.referencia("nota_de_voz", 2, "3:15") == "min. 3:15"
    assert fuente.candidatos(3000) == 6 and fuente.candidatos(100000) == 12


def test_nota_de_voz_por_tramos_con_minutos():
    palabras, t = [], 0.0
    for k in range(400):
        texto = "fin." if k % 20 == 19 else "palabra"
        palabras += [{"text": texto, "type": "word", "start": t, "end": t + 0.4}, {"text": " ", "type": "spacing", "start": t + 0.4, "end": t + 0.5}]
        t += 0.6
    l = transcripcion.a_libro({"words": palabras}, "Nota", "Yo")
    assert l.tipo == "nota_de_voz" and len(l.capitulos) == 2
    assert l.capitulos[0].paginas[0][1] == "0:00" and l.capitulos[0].titulo.startswith("Minutos 0:00")
    ref = lib.buscar_literal(l, " ".join(["palabra"] * 6))
    assert ref is not None and ":" in ref.pagina


def test_nota_de_voz_sin_clave_lo_dice(cfg, tmp_path):
    audio = tmp_path / "nota.m4a"
    audio.write_bytes(b"x" * 100)
    with pytest.raises(transcripcion.ErrorTranscripcion, match="ELEVENLABS_API_KEY"):
        almacen.crear(cfg, "nota.m4a", audio.read_bytes())
