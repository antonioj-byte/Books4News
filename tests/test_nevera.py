"""La nevera del cajón: historias editoriales nuevas cada día, con las fuentes comprobadas. Sin red ni gasto."""

from datetime import date

import httpx

from folio import cajon, nevera

TEXTO_LARGO = "<html><body><article>" + "<p>" + "La historia del manuscrito salvado del fuego. " * 40 + "</p></article></body></html>"


class LLMFalso:
    def __init__(self, cfg, historias, urls):
        self.cfg, self.historias, self.urls, self.prompts = cfg, historias, urls, []

    def con_busqueda(self, paso, prompt, *, etapa_modelo, max_busquedas=6, max_tokens=8000):
        self.prompts.append(prompt)
        return "texto con las historias", self.urls

    def estructurado(self, paso, mensajes, esquema, *, etapa_modelo, max_tokens=16000):
        return esquema(historias=self.historias), []


def _h(titular, *urls):
    return nevera.HistoriaNueva(titular=titular, resumen="Dos frases.", protagonista="Edgar Allan Poe",
                                fuentes=[nevera.FuenteNueva(medio="ActuaLitté", titulo="t", url=u) for u in urls])


def _cliente(pedidas):
    def manejar(req):
        pedidas.append(str(req.url))
        if "bloqueada" in str(req.url):
            return httpx.Response(403)
        if "corta" in str(req.url):
            return httpx.Response(200, text="<p>poco</p>")
        return httpx.Response(200, text=TEXTO_LARGO)
    return httpx.Client(transport=httpx.MockTransport(manejar))


def test_guarda_las_buenas_y_descarta_lo_inventado_lo_bloqueado_y_lo_repetido(cfg):
    (cfg.raiz / "config").mkdir(exist_ok=True)
    (cfg.raiz / "config" / "cajon_curiosidades.yaml").write_text(
        "- id: biblia-malvada\n  titular: La Biblia de 1631 que olvidó un no\n  resumen: r\n  fuentes:\n    - {medio: m, url: 'https://x', titulo: t}\n",
        encoding="utf-8")
    urls = {"https://a.org/poe", "https://b.org/poe", "https://bloqueada.org/x", "https://corta.org/x", "https://c.org/biblia"}
    historias = [
        _h("Un manuscrito de Poe sobrevive a dos incendios", "https://a.org/poe", "https://inventada.org/poe", "https://b.org/poe"),
        _h("La Biblia de 1631 que olvidó un no", "https://c.org/biblia"),                   # ya estaba
        _h("Una imprenta clandestina en un sótano de Praga", "https://bloqueada.org/x", "https://corta.org/x"),  # ninguna vale
    ]
    llm, pedidas = LLMFalso(cfg, historias, urls), []
    nuevas, avisos = nevera.buscar(llm, cfg, 3, hoy=date(2026, 11, 2), cliente=_cliente(pedidas))
    assert [c.titular for c in nuevas] == ["Un manuscrito de Poe sobrevive a dos incendios"]
    assert [f.url for f in nuevas[0].fuentes] == ["https://a.org/poe", "https://b.org/poe"]
    assert nuevas[0].protagonista == "Edgar Allan Poe" and nuevas[0].origen == "busqueda"
    assert "https://inventada.org/poe" not in pedidas                                        # no se descarga lo inventado
    assert any("no salió en la búsqueda" in a for a in avisos) and any("403" in a for a in avisos)
    assert any("ya estaba" in a for a in avisos)
    assert "La Biblia de 1631" in llm.prompts[0]                                             # sabe lo que ya hay
    # La nevera se junta con el cajón del repositorio y entra en las disponibles
    todas = cajon.cargar(cfg.raiz, nevera.ruta(cfg))
    assert [c.id for c in todas] == ["biblia-malvada", nuevas[0].id] and todas[1].añadida == "2026-11-02"
    assert len(cajon.disponibles(cfg.raiz, {"biblia-malvada"}, nevera.ruta(cfg))) == 1
    # Relanzar el mismo día no la llena dos veces
    nuevas2, avisos2 = nevera.buscar(LLMFalso(cfg, historias, urls), cfg, 1, hoy=date(2026, 11, 2), cliente=_cliente([]))
    assert nuevas2 == [] and "no se busca más" in avisos2[0]


def test_temas_que_rotan_cada_dia():
    a, b = nevera.temas_del_dia(date(2026, 11, 2)), nevera.temas_del_dia(date(2026, 11, 3))
    assert len(a) == 3 and a != b


def test_detecta_la_misma_historia_con_otro_titular():
    viejo = cajon.Curiosidad(id="juicio-lady-chatterley", titular="«¿Querrían que su mujer o sus criados leyeran este libro?»",
                             resumen="En 1960 Penguin fue juzgada por publicar El amante de Lady Chatterley; Penguin ganó.",
                             protagonista="D. H. Lawrence", fuentes=[cajon.FuenteCajon(medio="m", url="https://x", titulo="t")])
    assert nevera.ya_esta("El juicio que convirtió «El amante de Lady Chatterley» en bestseller británico", "Penguin ganó en 1960.", viejo)
    assert not nevera.ya_esta("Una librería porteña escondió 235.000 libros prohibidos", "Durante la dictadura argentina.", viejo)
