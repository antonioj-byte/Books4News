"""Voz con tiempos, estilo, imágenes simuladas y montaje, sin red ni gasto."""
import subprocess
import wave

import pytest

from videos import almacen, conceptos, estilo, guion, imagenes, montaje, voz
from videos.modelos import EscenaLLM, EscenasLLM, Palabra
from test_flujo import Claude


def test_tiempos_por_plano_desde_la_alineacion():
    textos = [("p01", "Hola mundo."), ("p02", "Otra frase aquí.")]
    texto = " ".join(t for _, t in textos)
    alin = voz.alineacion_simulada(texto)
    palabras, planos, _ = voz.tiempos(textos, alin, 5.0)
    assert [w.t for w in palabras] == ["Hola", "mundo.", "Otra", "frase", "aquí."]
    assert planos["p01"].inicio == 0.0 and planos["p02"].inicio == palabras[2].i
    assert planos["p01"].fin == planos["p02"].inicio and planos["p02"].fin == 5.0
    assert all(a.f <= b.i + 1e-6 for a, b in zip(palabras, palabras[1:]))


def test_alineacion_que_no_casa_se_aproxima():
    alin = voz.alineacion_simulada("Hola  mundo")       # dos espacios: no casa con el texto
    tc = voz._caracteres(alin, "Hola mundo")
    assert len(tc) == len("Hola mundo")


def test_trozos_de_subtitulos_no_cruzan_planos_ni_puntos():
    ws = [Palabra(t=t, i=k, f=k + 0.5, plano=p) for k, (t, p) in enumerate(
        [("Uno", "p1"), ("dos.", "p1"), ("Tres", "p1"), ("cuatro", "p2"), ("cinco", "p2"), ("seis", "p2"), ("siete", "p2")])]
    grupos = [[w.t for w in g] for g in montaje.trozos(ws)]
    assert grupos == [["Uno", "dos."], ["Tres"], ["cuatro", "cinco", "seis"], ["siete"]]


def test_prompt_de_imagen_lleva_el_estilo_delante():
    e = estilo.predefinidos()["collage"]
    from videos.modelos import Estilo
    pr = estilo.prompt_imagen(Estilo(id="collage", **e), "a red chair in an empty room.")
    assert pr.startswith("Conceptual paper collage: a red chair") and "No text" in pr


@pytest.fixture
def proyecto_listo(cfg, libro_txt):
    cfg.forzar_simulado = True
    pid = almacen.crear(cfg, "libro.txt", libro_txt.read_bytes(), "El descanso", "Ana Pérez").id
    c = Claude()
    nuevos = conceptos.proponer(cfg, c, pid)
    conceptos.elegir(cfg, pid, nuevos[0].id)
    guion.escribir(cfg, c, pid)
    guion.aprobar(cfg, pid)
    estilo.elegir(cfg, pid, "collage")
    return pid


class Escenas:
    def estructurado(self, paso, mensajes, esquema, **kw):
        assert esquema is EscenasLLM
        import json, re
        ids = re.findall(r'"id": "(p\d+)"', mensajes[0]["content"])
        return EscenasLLM(escenas=[EscenaLLM(id=i, escena=f"an empty chair number {i}", animacion="the chair spins")
                                   for i in ids]), []


def test_de_guion_a_mp4_en_simulado(cfg, proyecto_listo):
    pid = proyecto_listo
    v = voz.generar(cfg, pid)
    assert v.simulada and v.palabras and abs(sum(t.fin - t.inicio for t in v.planos.values()) - v.duracion) < 0.01
    imagenes.generar_todas(cfg, Escenas(), pid)
    p = almacen.cargar(cfg, pid)
    assert all(len(x.variantes) == 2 and x.elegida == 0 for x in p.imagenes.values())
    imagenes.elegir(cfg, pid, "p02", 1)
    m = montaje.montar(cfg, pid)
    ruta = almacen.carpeta(cfg, pid) / m.archivo
    salida = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "csv=p=0",
                             str(ruta)], capture_output=True, text=True).stdout
    assert "video,1080,1920" in salida and "audio" in salida
    assert abs(m.duracion - (v.duracion + montaje.TARJETA_S)) < 0.05
    ass = (almacen.carpeta(cfg, pid) / "salida" / "subtitulos-1.ass").read_text(encoding="utf-8")
    assert "Style: Subs" in ass and "Cita" in ass and "El descanso" in ass


def test_rehacer_la_voz_de_un_plano_desplaza_los_siguientes(cfg, proyecto_listo):
    pid = proyecto_listo
    v1 = voz.generar(cfg, pid)
    antes = v1.planos["p05"].inicio
    v2 = voz.rehacer_plano(cfg, pid, "p03", "Una frase bastante más larga que la que había antes en este plano.")
    assert v2.version == 2 and v2.planos["p05"].inicio > antes
    with wave.open(str(almacen.carpeta(cfg, pid) / v2.audio)) as w:
        assert abs(w.getnframes() / w.getframerate() - v2.duracion) < 0.01
    p = almacen.cargar(cfg, pid)
    assert p.etapas["guion"].estado == "bloqueado" and p.guion_actual.planos[2].locucion.startswith("Una frase")
    assert [w.t for w in v2.palabras if w.plano == "p03"][0] == "Una"
