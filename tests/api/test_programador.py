import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

from folio_api.ejecutor import Ejecutor
from folio_api.programador import Programador

MADRID = ZoneInfo("Europe/Madrid")


class EjecutorFalso:
    diaria = [["run"], ["render", "--video"]]

    def __init__(self, ocupado=False, codigo=0):
        self.lanzadas, self._ocupado, self.codigo = [], ocupado, codigo

    def ocupado(self):
        return self._ocupado

    def estado(self):
        from types import SimpleNamespace
        return SimpleNamespace(codigo=self.codigo)

    def lanzar(self, pasos=None):
        if self._ocupado:
            return False
        self.lanzadas.append(pasos)
        return True


def _programador(tmp_path, reloj, ejecutor=None):
    return Programador(ejecutor or EjecutorFalso(), time(4, 30), MADRID, tmp_path, ahora=lambda: reloj[0])


def test_lanza_una_vez_al_dia_a_su_hora(tmp_path):
    reloj = [datetime(2026, 10, 31, 4, 29, tzinfo=MADRID)]
    ej = EjecutorFalso()
    p = _programador(tmp_path, reloj, ej)
    assert not p.comprobar()
    reloj[0] = datetime(2026, 10, 31, 4, 30, tzinfo=MADRID)
    assert p.comprobar() and ej.lanzadas == [EjecutorFalso.diaria]
    assert not p.comprobar() and p.ultima() == "2026-10-31"            # una vez al día
    reloj[0] = datetime(2026, 11, 1, 4, 31, tzinfo=MADRID)
    assert p.comprobar() and len(ej.lanzadas) == 2


def test_hora_de_madrid_con_cambio_de_hora(tmp_path):
    # 04:30 en Madrid son las 03:30 UTC en invierno y las 02:30 UTC en verano
    ej = EjecutorFalso()
    reloj = [datetime(2026, 7, 1, 2, 30, tzinfo=ZoneInfo("UTC"))]
    assert _programador(tmp_path, reloj, ej).comprobar()
    reloj = [datetime(2026, 12, 1, 2, 30, tzinfo=ZoneInfo("UTC"))]
    assert not _programador(tmp_path / "b", reloj, ej).comprobar()


def test_fuera_de_la_ventana_no_se_recupera(tmp_path):
    reloj = [datetime(2026, 10, 31, 12, 0, tzinfo=MADRID)]               # la API arrancó a mediodía
    p = _programador(tmp_path, reloj)
    assert not p.comprobar() and p.estado().proxima == "2026-11-01T04:30+01:00"


def test_si_hay_otra_en_marcha_espera(tmp_path):
    reloj = [datetime(2026, 10, 31, 4, 30, tzinfo=MADRID)]
    ej = EjecutorFalso(ocupado=True)
    p = _programador(tmp_path, reloj, ej)
    assert not p.comprobar() and p.ultima() is None
    ej._ocupado = False
    reloj[0] = datetime(2026, 10, 31, 5, 10, tzinfo=MADRID)
    assert p.comprobar()


def test_sin_hora_no_hace_nada(tmp_path):
    p = Programador(EjecutorFalso(), None, MADRID, tmp_path)
    assert not p.comprobar() and not p.estado().activa


def test_ejecutor_encadena_pasos_y_para_si_uno_falla(tmp_path):
    import time as t
    ok = [sys.executable, "-c", "print('paso')"]
    falla = [sys.executable, "-c", "import sys; print('falla'); sys.exit(3)"]
    ej = Ejecutor(tmp_path)
    assert ej.lanzar([ok, ok])
    while ej.ocupado():
        t.sleep(0.05)
    assert ej.estado().codigo == 0 and ej.registro.read_text().count("paso") == 2
    assert ej.lanzar([falla, ok])
    while ej.ocupado():
        t.sleep(0.05)
    assert ej.estado().codigo == 3 and "paso" not in ej.registro.read_text()


def test_ruta_de_la_programada(cfg):
    from fastapi.testclient import TestClient
    from folio.almacen import Almacen
    from folio_api.main import crear_app
    (cfg.raiz / "diseno").symlink_to((type(cfg)(pipeline={}, fuentes=[]).raiz / "diseno").resolve())
    cliente_api = TestClient(crear_app(cfg, Almacen(cfg.ruta_db), importar=False))
    assert cliente_api.get("/api/ejecuciones/programada").json() == {
        "activa": False, "hora": None, "zona": None, "ultima": None, "proxima": None}


def test_si_un_despliegue_la_corta_se_relanza_una_vez(tmp_path):
    """Revisión general (2/11): un push de madrugada mataba la diaria y no se relanzaba."""
    reloj = [datetime(2026, 11, 3, 4, 30, tzinfo=MADRID)]
    ej = EjecutorFalso()
    p = _programador(tmp_path, reloj, ej)
    assert p.comprobar()
    ej.codigo = -1                                   # la API se reinició: el registro no tiene línea de fin
    reloj[0] = datetime(2026, 11, 3, 4, 50, tzinfo=MADRID)
    assert p.comprobar() and len(ej.lanzadas) == 2
    assert not p.comprobar()                         # una sola vez
    reloj[0] = datetime(2026, 11, 3, 7, 0, tzinfo=MADRID)
    ej2 = EjecutorFalso(codigo=-1)
    assert not _programador(tmp_path, reloj, ej2).comprobar()   # fuera de la ventana, no


def test_un_registro_sin_linea_de_fin_es_interrumpido(tmp_path):
    from folio_api.ejecutor import FIN, INTERRUMPIDO
    ej = Ejecutor(tmp_path)
    ej.registro.write_text("ETAPA: Guion\nalgo\n", encoding="utf-8")
    e = ej.estado()
    assert e.codigo == -1 and e.ultimas_lineas[-1] == INTERRUMPIDO
    ej.registro.write_text(f"algo\n{FIN}0\n", encoding="utf-8")
    assert ej.estado().codigo == 0
    (tmp_path / "desarrollos").mkdir()
    (tmp_path / "desarrollos" / "2026-11-02-3.log").write_text("ETAPA: Guion\n", encoding="utf-8")
    assert ej.estado_desarrollo("2026-11-02-3").codigo == -1 and ej.estado_desarrollo("otra") is None
