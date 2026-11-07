"""El informe del libro por Telegram (7/11): lo que Folio ya seleccionó, una vez al día y sin reintentar bloqueos."""
import httpx

from folio import cinco, telegram


def _propuesta(cfg, fecha="2026-11-07"):
    cs = [cinco.Candidata(historia="h1", titular="Margarita García Robayo gana el Herralde", por_que="Un premio de la lengua.",
                          medio="El País", url="https://elpais.com/x", n_medios=6, marcada=True),
          cinco.Candidata(historia="h2", titular="Cierra una librería <histórica>", por_que="Otra más.", medio="ABC",
                          url="https://abc.es/y")]
    ruta = cinco.ruta_propuesta(cfg, fecha)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(cinco.PropuestaCinco(fecha=fecha, candidatas=cs).model_dump_json(), encoding="utf-8")


def test_el_informe_sale_de_la_lista_del_dia(cfg):
    assert telegram.informe(cfg, "2026-11-07") == ""
    _propuesta(cfg)
    texto = telegram.informe(cfg, "2026-11-07")
    assert "7 de noviembre" in texto and "⭐ <b>Lo más importante</b>" in texto
    assert '<a href="https://elpais.com/x">El País</a> · 6 medios' in texto
    assert "&lt;histórica&gt;" in texto                     # escapado para el HTML de Telegram


def test_trocear_respeta_el_limite():
    texto = "\n\n".join(f"<b>Noticia {i}</b>\n" + "x" * 300 for i in range(40))
    trozos = telegram.trocear(texto, 1000)
    assert all(len(t) <= 1000 for t in trozos) and "".join(trozos).count("<b>") == 40


def test_envia_una_vez_y_para_ante_un_bloqueo(cfg, monkeypatch):
    _propuesta(cfg)
    assert "sin TELEGRAM_BOT_TOKEN" in telegram.enviar_informe(cfg, "2026-11-07")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secreto")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    llamadas = []

    def responder(req):
        llamadas.append(req)
        return httpx.Response(200, json={"ok": True})
    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    assert "enviado (1 mensaje)" in telegram.enviar_informe(cfg, "2026-11-07", cliente=cliente)
    assert "ya salió" in telegram.enviar_informe(cfg, "2026-11-07", cliente=cliente) and len(llamadas) == 1
    bloqueo = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    nota = telegram.enviar_informe(cfg, "2026-11-07", forzar=True, cliente=bloqueo)
    assert "429" in nota and "sin reintentar" in nota and "secreto" not in nota
