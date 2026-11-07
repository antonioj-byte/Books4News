"""Libro → conceptos → guion aprobado, con un Claude simulado."""
import pytest

from videos import almacen, conceptos, guion
from videos.modelos import (CandidatosLLM, ConceptoLLM, CriticaLLM, GuionLLM, JuezGanchoLLM, NotasLLM, PlanoLLM,
                            RespuestaChatLLM, SalidaLibroLLM, ValoracionLLM)

PASAJE = "el cerebro que no hace nada se pone a rumiar, y rumiar cansa más que trabajar"
NOTAS = NotasLLM(sorpresa=8, utilidad=8, polemica=6, visualidad=7)


def _concepto(i, pasaje=PASAJE):
    return ConceptoLLM(titulo=f"Concepto {i}", idea=f"Idea {i}", gancho="Descansar el domingo te cansa más",
                       por_que="Choca con lo que creemos del descanso", pasaje=pasaje, capitulo=1, notas=NOTAS)


def _guion(locucion_extra=""):
    planos = [PlanoLLM(rol="gancho", locucion="Descansar el domingo te cansa más.", pantalla="", visual="un sofá vacío",
                       movimiento="zoom lento", duracion_estimada=2, cita="")]
    roles = ["tension"] * 3 + ["desarrollo"] * 4 + ["giro"] * 2 + ["cierre"] * 2
    for k, r in enumerate(roles):
        planos.append(PlanoLLM(rol=r, locucion="Una frase de prueba con unas ocho palabras más o menos aquí" + locucion_extra,
                               pantalla="El descanso · Ana Pérez" if r == "desarrollo" and k == 3 else "",
                               visual="una mano", movimiento="travelling lateral", duracion_estimada=3,
                               cita="rumiar cansa más que trabajar" if r == "desarrollo" and k == 4 else ""))
    return GuionLLM(titulo="El domingo cansa", planos=planos)


class Claude:
    """Responde por paso; apunta lo que se le pide."""
    def __init__(self, guiones=None):
        self.pasos, self.guiones = [], list(guiones or [_guion()])

    def estructurado(self, paso, mensajes, esquema, **kw):
        self.pasos.append(paso)
        if esquema is SalidaLibroLLM:          # las llamadas con el libro comparten esquema (y caché)
            if paso.startswith("conceptos"):
                c, contenido = self.estructurado(paso, mensajes, CandidatosLLM)
                return SalidaLibroLLM(conceptos=c.conceptos, guion=None, respuesta=None), contenido
            if paso.startswith("guion-chat"):
                r, _ = self.estructurado(paso, mensajes, RespuestaChatLLM)
                return SalidaLibroLLM(conceptos=None, guion=r.guion, respuesta=r.respuesta), []
            g, contenido = self.estructurado(paso, mensajes, GuionLLM)
            return SalidaLibroLLM(conceptos=None, guion=g, respuesta=None), contenido
        if esquema is CandidatosLLM:
            malos = [_concepto(9, "esto no está en el libro de ninguna manera posible ni imaginable")]
            return CandidatosLLM(conceptos=[_concepto(i) for i in range(7)] + malos), [{"type": "text", "text": "{}"}]
        if esquema is CriticaLLM:
            return CriticaLLM(valoraciones=[ValoracionLLM(indice=i, veredicto="elegido" if i < 5 else "descartado",
                                                          motivo="m", notas=NOTAS) for i in range(7)]), []
        if esquema is JuezGanchoLLM:
            return JuezGanchoLLM(nota=9, curiosidad=9, concrecion=9, sin_contexto=9, motivo="funciona",
                                 reescritura="Descansar el domingo te cansa más"), []
        if esquema is GuionLLM:
            return self.guiones.pop(0) if len(self.guiones) > 1 else self.guiones[0], [{"type": "text", "text": "{}"}]
        if esquema is RespuestaChatLLM:
            g = _guion()
            g.titulo = "Nuevo título"
            return RespuestaChatLLM(respuesta="Cambiado el título.", guion=g), []
        raise AssertionError(esquema)


@pytest.fixture
def pid(cfg, libro_txt):
    return almacen.crear(cfg, "libro.txt", libro_txt.read_bytes(), "El descanso", "Ana Pérez").id


def test_conceptos_verifica_pasajes_y_elige_cinco(cfg, pid):
    c = Claude()
    nuevos = conceptos.proponer(cfg, c, pid)
    assert len(nuevos) == 5 and all(x.pasaje.verificado and x.pasaje.capitulo == 1 for x in nuevos)
    assert "conceptos-pasajes" not in c.pasos          # 7 válidos de 8: no hace falta corregir
    p = almacen.cargar(cfg, pid)
    assert p.etapas["conceptos"].estado == "propuesta" and p.libro_en_cache


def test_juez_reescribe_un_gancho_flojo(cfg):
    class Juez:
        n = 0
        def estructurado(self, paso, mensajes, esquema, **kw):
            self.n += 1
            if self.n == 1:
                return JuezGanchoLLM(nota=5, curiosidad=5, concrecion=4, sin_contexto=6, motivo="genérico",
                                     reescritura="Tu domingo vacío te agota"), []
            return JuezGanchoLLM(nota=9, curiosidad=9, concrecion=9, sin_contexto=9, motivo="ok",
                                 reescritura="Tu domingo vacío te agota"), []
    texto, juicio = conceptos.juzgar_gancho(cfg, Juez(), "¿Alguna vez te has preguntado por qué te cansas?", "x")
    assert texto == "Tu domingo vacío te agota" and juicio.nota == 9 and juicio.intentos == 2


def test_guion_valido_se_aprueba_y_bloquea(cfg, pid):
    c = Claude()
    nuevos = conceptos.proponer(cfg, c, pid)
    conceptos.elegir(cfg, pid, nuevos[0].id)
    v = guion.escribir(cfg, c, pid)
    assert v.avisos == [], v.avisos
    assert v.planos[0].rol == "gancho" and any(x.cita for x in v.planos)
    guion.aprobar(cfg, pid)
    p = almacen.cargar(cfg, pid)
    assert p.etapas["guion"].estado == "bloqueado"
    with pytest.raises(ValueError):
        guion.editar(cfg, pid, {"p02": {"locucion": "otra"}})
    guion.desbloquear(cfg, pid)
    assert almacen.cargar(cfg, pid).etapas["guion"].estado == "propuesta"


def test_guion_que_rompe_reglas_se_corrige(cfg, pid):
    malo = _guion(" y además esto se alarga muchísimo más de la cuenta")
    c = Claude(guiones=[malo, _guion()])
    nuevos = conceptos.proponer(cfg, c, pid)
    conceptos.elegir(cfg, pid, nuevos[0].id)
    v = guion.escribir(cfg, c, pid)
    assert "guion-correccion-1" in c.pasos and v.avisos == []


def test_reglas_del_guion(cfg, pid):
    libro = almacen.libro(cfg, pid)
    planos = guion.a_planos(_guion(), libro)
    assert guion.validar(planos, libro, "Ana Pérez", "El descanso") == []
    planos[3].locucion = 'Como dice ella, «el descanso es un invento moderno»'
    planos[5].cita = None
    errores = guion.validar(planos, libro, "Ana Pérez", "El descanso")
    assert any("entre comillas" in e for e in errores)
    planos[0].rol = "tension"
    assert any("primer plano" in e for e in guion.validar(planos, libro))
    sin_autor = guion.a_planos(_guion(), libro)
    for x in sin_autor:
        x.pantalla = ""
    assert any("título del libro o el autor" in e for e in guion.validar(sin_autor, libro, "Ana Pérez", "El descanso"))


def test_edicion_manual_y_chat(cfg, pid):
    c = Claude()
    nuevos = conceptos.proponer(cfg, c, pid)
    conceptos.elegir(cfg, pid, nuevos[0].id)
    guion.escribir(cfg, c, pid)
    v = guion.editar(cfg, pid, {"p02": {"locucion": "Otra frase."}}, quitar=["p03"])
    assert v.origen == "manual" and len(v.planos) == 11 and v.planos[1].locucion == "Otra frase."
    respuesta = guion.chat(cfg, c, pid, "Cambia el título")
    p = almacen.cargar(cfg, pid)
    assert respuesta == "Cambiado el título." and p.guion_actual.titulo == "Nuevo título" and p.guion_actual.origen == "chat"
    assert [m.rol for m in p.chat] == ["usuario", "asistente"]
