"""Acciones de imagen del chat de edición (folio.edicion.aplicar_imagen). Sin red ni gasto."""

from io import BytesIO

from PIL import Image

from folio import arte as direccion
from folio import edicion
from folio.edicion import AccionImagen
from folio.imagenes import editorial, libres
from folio.modelos import Arte, Pieza

from datos import ELECCION, LIBRO, guion_valido


def _accion(tipo, **k):
    datos = dict(tipo=tipo, enfoque_x=50, enfoque_y=50, composicion="", consultas=[], escena="", persona="", estilo="", material="", como="", destacado="", antetitulo="", acento="", libro="", autor="", sin_castellano="", editorial="", isbn="")
    return AccionImagen(**(datos | k))


def _pieza(**arte):
    return Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="h1", eleccion=ELECCION,
                 n_medios=3, libros=[LIBRO], guion=guion_valido(), arte=Arte(tono="sereno", recurso="foto", **arte))


def _fijar(cfg, clave, archivo="europeana:/1"):
    d = cfg.dir_cache("2026-10-30")
    libres.dir_imagenes(d).mkdir(parents=True, exist_ok=True)
    b = BytesIO()
    Image.new("RGB", (1200, 1500)).save(b, "JPEG")
    (libres.dir_imagenes(d) / f"{clave}.jpg").write_bytes(b.getvalue())
    libres.guardar_metadatos(libres.ImagenLibre(archivo=archivo, pagina="", url="", ancho=1200, alto=1500, licencia="CC0",
                                                licencia_url=None, autor="A", descripcion="", libre=True, motivo="",
                                                local=f"{clave}.jpg"), clave, d)


def test_encuadre_de_la_foto_del_autor_o_de_la_de_archivo(cfg):
    _fijar(cfg, "2026-10-30-1")
    _fijar(cfg, "2026-10-30-1-retrato", "commons:File:A.jpg")
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(registro="foto_autor"), _accion("encuadre", enfoque_y=25))
    assert nueva and libres.de_pieza("2026-10-30-1-retrato", cfg.dir_cache("2026-10-30")).enfoque == (50, 25)
    edicion.aplicar_imagen(None, cfg, _pieza(registro="archivo"), _accion("encuadre", enfoque_x=120, enfoque_y=-5))
    assert libres.de_pieza("2026-10-30-1", cfg.dir_cache("2026-10-30")).enfoque == (100, 0)   # dentro de 0–100


def test_composicion_y_que_imagen_va_en_la_portada(cfg):
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("composicion", composicion="banda"))
    assert nueva.arte.portada == "banda"
    assert edicion.aplicar_imagen(None, cfg, _pieza(), _accion("composicion", composicion="marco"))[0] is None
    assert edicion.aplicar_imagen(None, cfg, _pieza(), _accion("composicion", composicion="neon"))[0] is None   # sin color
    assert edicion.aplicar_imagen(None, cfg, _pieza(), _accion("usar_foto_autor"))[0] is None                 # no hay foto
    _fijar(cfg, "2026-10-30-1")
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(portada="panorama"), _accion("usar_archivo"))
    assert nueva.arte.registro == "archivo" and nueva.arte.portada == "sangre"


def test_buscar_otra_imagen_de_archivo(cfg, monkeypatch):
    def elegir(llm, cfg, pieza, datos, propuesta, ar, usadas, d):
        assert propuesta.consultas == ["printing press", "old library"]
        ar.imagen, ar.credito = "europeana:/2", "B · CC0 · Europeana"
    monkeypatch.setattr(direccion, "_imagen_de_archivo", elegir)
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("buscar_archivo", consultas=["printing press", "old library", "una búsqueda demasiado larga aquí"]))
    assert nueva.arte.imagen == "europeana:/2" and nueva.arte.registro == "archivo" and "B · CC0" in nota


def test_ilustrar_con_escena_valida_y_tope_del_dia(cfg, monkeypatch):
    assert "nombres propios" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena="Madrid at night " * 5))[1]
    llamadas = []
    monkeypatch.setattr(editorial, "generar_limpia", lambda llm, cfg, pid, d, escena: (llamadas.append(escena) or libres.ImagenLibre(
        archivo=editorial.CLAVE, pagina="", url="", ancho=1, alto=1, licencia="ilustración generada con IA (Magnific)",
        licencia_url=None, autor="Folio", descripcion=escena, libre=True, motivo="", fuente=""), []))
    escena = "a vast quiet suburban block at dusk where every house is a hollow stage set propped up by wooden beams"
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))
    assert nueva.arte.portada == "panorama" and nueva.arte.registro == "ilustracion" and llamadas
    monkeypatch.setattr(editorial, "generar_limpia", lambda *a: (None, ["letras (arriba)", "letras (esquina)"]))
    assert "salieron con letras" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))[1]
    cfg.pipeline.arte.ilustracion_editorial.max_por_dia = 0
    assert "máximo del día" in edicion.aplicar_imagen(None, cfg, _pieza(), _accion("ilustrar", escena=escena))[1]
    assert "graves" in edicion.aplicar_imagen(None, cfg, _pieza().model_copy(update={"arte": Arte(tono="grave", recurso="foto")}),
                                              _accion("ilustrar", escena=escena))[1]


def test_buscar_otra_imagen_que_falla_no_deja_la_pieza_sin_imagen(cfg, monkeypatch):
    _fijar(cfg, "2026-10-30-1")
    def falla(llm, cfg, pieza, datos, propuesta, ar, usadas, d):
        libres.olvidar(pieza.id, d)                 # como la de verdad, borra antes de elegir
        raise RuntimeError("Europeana caída")
    monkeypatch.setattr(direccion, "_imagen_de_archivo", falla)
    nueva, nota = edicion._imagen_sin_romper(None, cfg, _pieza(registro="archivo"), _accion("buscar_archivo", consultas=["printing press"]))
    assert nueva is None and "Europeana caída" in nota
    assert (libres.dir_imagenes(cfg.dir_cache("2026-10-30")) / "2026-10-30-1.jpg").exists()
    def no_encuentra(llm, cfg, pieza, datos, propuesta, ar, usadas, d):
        libres.olvidar(pieza.id, d)
    monkeypatch.setattr(direccion, "_imagen_de_archivo", no_encuentra)
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(registro="archivo"), _accion("buscar_archivo", consultas=["printing press"]))
    assert nueva is None and (libres.dir_imagenes(cfg.dir_cache("2026-10-30")) / "2026-10-30-1.jpg").exists()



def test_retrato_de_una_persona_real_solo_desde_una_foto_libre(cfg, monkeypatch):
    from folio.imagenes import retrato_generado, retratos
    sin_libro = Pieza(id="2026-10-30-1", fecha="2026-10-30", estado="propuesta", historia_id="cajon-el-secuestro-perec",
                      eleccion=ELECCION.model_copy(update={"formato": "curiosidad", "libros_candidatos": []}), n_medios=1,
                      libros=[], guion=guion_valido(), arte=Arte(tono="sereno", recurso="ilustracion", portada="panorama"))
    # Sin foto libre: se dice claro y no se dibuja nada
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda *a, **k: (None, "Commons no tiene ninguna libre"))
    nueva, nota = edicion.aplicar_imagen(None, cfg, sin_libro, _accion("buscar_retrato", persona="Georges Perec"))
    assert nueva is None and "no puedo poner su cara" in nota
    # Con foto libre: va en la portada y la pieza sin libro guarda a quién retrata
    def fija(persona, pid, d, sa):
        _fijar(cfg, f"{pid}-retrato", "commons:File:Perec.jpg")
        return libres.de_pieza(f"{pid}-retrato", d), ""
    monkeypatch.setattr(retratos, "buscar_y_fijar", fija)
    nueva, nota = edicion.aplicar_imagen(None, cfg, sin_libro, _accion("buscar_retrato", persona="Georges Perec"))
    assert nueva.eleccion.protagonista == "Georges Perec" and nueva.arte.registro == "foto_autor"
    assert nueva.arte.portada == "sangre" and "Retrato de Georges Perec" in nota
    # Ilustrarlo: desde esa foto, en un estilo de la casa, con revisión humana
    estilos = []
    monkeypatch.setattr(retrato_generado, "aplicar", lambda cfg, pid, d, estilo: estilos.append(estilo) or libres.de_pieza(f"{pid}-retrato", d))
    otra, nota = edicion.aplicar_imagen(None, cfg, nueva, _accion("retrato_ilustrado", estilo="voxel"))
    assert estilos == ["voxel"] and otra.arte.registro == "retrato_ia" and "parecido" in nota
    assert direccion.AVISO_RETRATO_GENERADO in otra.revision_humana
    # Con libro, la cara es la del autor y no otra
    con_libro = _pieza()
    nueva, nota = edicion.aplicar_imagen(None, cfg, con_libro, _accion("buscar_retrato", persona="Georges Perec"))
    assert nueva is None and "Hannah Arendt" in nota


def test_el_retrato_del_autor_casa_por_apellido(cfg, monkeypatch):
    """2/11: «Gonçalo Tavares» es el autor «Gonçalo M. Tavares»; antes se comparaba letra por letra y se negaba."""
    from folio.imagenes import retratos
    pedidos = []
    monkeypatch.setattr(retratos, "buscar_y_fijar", lambda persona, *a, **k: pedidos.append(persona) or (None, "sin foto"))
    p = _pieza()
    autor = p.libros[0].autores[0]                       # Hannah Arendt
    nota = edicion.aplicar_imagen(None, cfg, p, _accion("buscar_retrato", persona="Arendt"))[1]
    assert pedidos == ["Arendt"] and "otra persona" not in nota
    nota = edicion.aplicar_imagen(None, cfg, p, _accion("buscar_retrato", persona="Simone Weil"))[1]
    assert "otra persona" in nota and autor in nota


def test_si_dice_que_cambio_el_texto_tiene_que_traer_el_guion(cfg):
    """2/11: el editor describió cambios en el texto, devolvió solo la imagen y la «versión nueva» no los tenía."""
    from datos import guion_valido
    llamadas = []

    class LLM:
        def estructurado(self, paso, mensajes, esquema, **k):
            llamadas.append(mensajes[-1]["content"])
            if len(llamadas) == 1:
                return esquema(respuesta="He reescrito la diapositiva 3 y quitado la gráfica.", guion=None,
                               imagen=_accion("composicion", composicion="sangre")), []
            g = guion_valido()
            g.diapositivas[3].texto = "El mal administrativo necesita gente que nunca se pregunte nada."
            return esquema(respuesta="Aquí va entero.", guion=g, imagen=None), []

    respuesta, nueva, avisos = edicion.chat(LLM(), cfg, _pieza(), [], "quita la gráfica")
    assert len(llamadas) == 2 and "`guion` va a null" in llamadas[1]
    assert nueva is not None and "nunca se pregunte" in nueva.guion.diapositivas[3].texto
    assert any("sin devolver el guion" in a for a in avisos)


def test_formato_destacado_antetitulo_y_color(cfg):
    """2/11, a petición del usuario («si pido edits de formato, no me deja»): el chat destaca un trozo del titular en
    cualquier sitio, cambia el antetítulo y el color; lo que no casa no se aplica y se dice."""
    from folio.render.textos import titular_con_remate
    p = _pieza(remate="también se elige", acento="marcador")          # titular: «La obediencia también se elige»
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, _accion("formato", destacado="La obediencia", antetitulo="pensamiento",
                                                               acento="pluma"))
    assert nueva and nueva.arte.remate == "La obediencia" and nueva.arte.antetitulo == "PENSAMIENTO"
    assert nueva.arte.acento == "pluma" and "destacado" in nota
    html = str(titular_con_remate("La obediencia también se elige", nueva.arte.remate))
    assert html == '<span class="remate">La obediencia</span> también se elige'
    assert str(titular_con_remate("La obediencia también se elige.", "también se elige")).endswith('<span class="remate">también se elige.</span>')
    nada, nota = edicion.aplicar_imagen(None, cfg, p, _accion("formato", destacado="Premio Formentor"))
    assert nada is None and "no está tal cual" in nota
    sin, _ = edicion.aplicar_imagen(None, cfg, p, _accion("formato", destacado="ninguno"))
    assert sin.arte.remate is None
    grave, nota = edicion.aplicar_imagen(None, cfg, _pieza(tono="grave") if False else p.model_copy(update={"arte": p.arte.model_copy(update={"tono": "grave"})}),
                                         _accion("formato", acento="pluma"))
    assert grave is None and "grave" in nota


def test_cubierta_de_otra_edicion_cambia_tambien_la_ficha(cfg, monkeypatch):
    """«Pon la portada de la edición de Mondadori»: cubierta y ficha de esa edición, con los datos de la API."""
    from folio.imagenes import cubiertas
    from folio.modelos import EdicionEspanola
    vistos = {}

    def de_edicion(libro, dir_cache, editorial="", isbn="", clave_gb=None):
        vistos["editorial"] = editorial
        ruta = dir_cache / "cubiertas" / "x.jpg"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"jpg")
        return ruta, EdicionEspanola(editorial="Mondadori", anio="2008", isbn="9788439721000"), ""
    monkeypatch.setattr(cubiertas, "de_edicion", de_edicion)
    nueva, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("cubierta", libro="eichmann en jerusalén", editorial="Mondadori"))
    assert nueva and vistos["editorial"] == "Mondadori" and "Mondadori, 2008" in nota
    l = nueva.libros[0]
    assert l.edicion_es_detalle.editorial == "Mondadori" and l.edicion_es_detalle.titulo == "Eichmann en Jerusalén"
    assert nueva.guion.libros[0].editorial_espanola == "Mondadori"
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("cubierta", libro="Eichmann"))
    assert nada is None and "editorial o el ISBN" in nota


def test_cambiar_el_libro_lo_verifica_y_deja_la_pieza_pendiente(cfg, monkeypatch):
    """2/11: «te has confundido enteramente de libro; el bueno es Killer App, de Darren Loucaides; rehazlo de 0»."""
    from folio import materiales
    from folio.etapas import EtapasGuardadas
    from folio.pipeline import Pipeline
    p = _pieza()
    materiales.guardar(cfg, p, "https://www.ft.com/content/abc", b"Killer App\n\nUna biografia de Durov.", "text/plain",
                       credito="ft.com", nota=materiales.NOTA_ENLACE)

    def verificar(self, pieza, reservados):
        c = pieza.eleccion.libros_candidatos[0]
        if c.titulo == "Inventado":
            pieza.error = "Ningún libro candidato se pudo verificar"
            return False
        pieza.libros = [LIBRO.model_copy(update={"titulo": c.titulo, "titulo_propuesto": c.titulo, "autores": [c.autor]})]
        return True
    monkeypatch.setattr(Pipeline, "_verificar", verificar)
    monkeypatch.setattr(Pipeline, "_cubiertas_de", lambda self, pieza: None)
    nueva, nota = edicion.aplicar_imagen(None, cfg, p, _accion("cambiar_libro", libro="Killer App", autor="Darren Loucaides"))
    assert nueva and nueva.estado == "pendiente" and nueva.guion is None and nueva.arte is None
    assert nueva.libros[0].titulo_propuesto == "Killer App" and "Proceder" in nota
    textos = EtapasGuardadas(cfg.dir_cache(p.fecha)).textos(p.historia_id)
    assert any(f.url == "https://www.ft.com/content/abc" for f, _ in textos)
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("cambiar_libro", libro="Inventado", autor="Nadie"))
    assert nada is None and "Sin verificar" in nota


def test_los_enlaces_del_chat_se_leen_y_se_guardan(cfg):
    import httpx
    from folio import materiales
    html = "<html><head><title>Killer App</title></head><body><article>" + "<p>Pavel Durov y Telegram. " * 40 + "</p></article></body></html>"
    def manejar(req):
        return httpx.Response(403) if "bloquea" in req.url.host else httpx.Response(200, text=html)
    cliente = httpx.Client(transport=httpx.MockTransport(manejar))
    avisos = edicion.leer_enlaces(cfg, _pieza(), "Mira https://www.ft.com/content/abc?x=1 y https://bloquea.org/a.", cliente)
    ms = materiales.lista(cfg, _pieza())
    assert [m.nombre for m in ms] == ["https://www.ft.com/content/abc?x=1"] and ms[0].nota == materiales.NOTA_ENLACE
    assert len(avisos) == 1 and "403" in avisos[0]


def test_titulo_sin_traducir_solo_si_se_pide_expresamente(cfg, monkeypatch):
    """2/11, regla del usuario: «que yo pueda dar instrucciones a títulos extranjeros, excepcionalmente»."""
    from folio.pipeline import Pipeline
    vistos = []
    def verificar(self, pieza, reservados):
        vistos.append(self.permitir_sin_castellano)
        if not self.permitir_sin_castellano:
            from folio.modelos import LibroDescartado
            pieza.libros_descartados = [LibroDescartado(titulo="Killer App", autor="Darren Loucaides",
                                                        motivo="sin edición en castellano verificada")]
            return False
        pieza.libros = [LIBRO.model_copy(update={"titulo_propuesto": "Killer App", "edicion_es": "desconocido"})]
        return True
    monkeypatch.setattr(Pipeline, "_verificar", verificar)
    monkeypatch.setattr(Pipeline, "_cubiertas_de", lambda self, pieza: None)
    nada, nota = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("cambiar_libro", libro="Killer App", autor="Darren Loucaides"))
    assert nada is None and "por excepción" in nota
    nueva, _ = edicion.aplicar_imagen(None, cfg, _pieza(), _accion("cambiar_libro", libro="Killer App", autor="Darren Loucaides", sin_castellano="si"))
    assert nueva and vistos == [False, True]
