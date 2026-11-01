"""Director de arte (prompts/director_arte.md y director_arte_eleccion.md).

Para cada pieza con guion, después de la comprobación de hechos:
1. El modelo decide el tono, si conviene foto o grabado, qué buscar y si hay una cifra que
   destacar (copiada de la diapositiva de actualidad: el código lo comprueba).
2. El código busca en Europeana, se queda con las imágenes de licencia libre y tamaño suficiente
   (folio.imagenes) y monta una hoja de contactos numerada.
3. El modelo ve la hoja y elige una o ninguna, con el punto de interés para el recorte.
4. El código fija la imagen (data/cache/<fecha>/imagenes/) y busca las cubiertas de los libros.

Reglas que no dependen del modelo: con víctimas no hay personas reconocibles ni cifra destacada;
sin imagen válida la pieza sale con la composición sin foto. Nada de esto para la pieza.
"""

from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import httpx
import yaml
from PIL import Image, ImageDraw, ImageFont

from folio import infografia, sin_foto
from folio.imagenes import cubiertas, editorial, esquema, ilustracion, libres, prensa, retrato_generado, retratos
from folio.config import Config
from folio.llm import LLM, cargar_prompt, con_cache
from folio.modelos import Arte, EleccionIlustracion, EleccionImagen, EscenasLLM, Infografia, Pieza, PropuestaArte
from folio.verificacion_texto import normalizar

log = logging.getLogger(__name__)
MAX_CANDIDATAS = 9
LADO_MINIMO = 1000          # lado mayor de la imagen original
_CELDA = 360


def _bloque_pieza(pieza: Pieza, seccion: str | None) -> str:
    g = pieza.guion
    diapositivas = "\n".join(f"diapositiva {d.n} ({d.tipo}): {d.texto}" for d in g.diapositivas)
    libros = "\n".join(f"- {l.titulo}, {l.autor}" for l in g.libros) or "(ninguno: curiosidad del mundo del libro sin libro)"
    return (f"<pieza>\nsección de la noticia: {seccion or 'desconocida'}\n"
            f"titular de la historia: {pieza.eleccion.titular}\nidea: {g.idea_elegida}\n"
            f"{diapositivas}\nlibros:\n{libros}\n</pieza>")


def _texto_actualidad(pieza: Pieza) -> str:
    return " ".join(d.texto for d in pieza.guion.diapositivas if d.tipo == "actualidad")


def validar_cifra(propuesta: PropuestaArte, pieza: Pieza) -> list[str]:
    """Anula la cifra si no está literalmente en la diapositiva de actualidad, si su rótulo añade
    palabras que no están allí o si la pieza trata de víctimas. Devuelve los avisos."""
    avisos = []
    texto = normalizar(_texto_actualidad(pieza))
    if propuesta.cifra and propuesta.suceso_con_victimas:
        avisos.append("Cifra descartada: con víctimas no se destaca un número")
    elif propuesta.cifra and normalizar(propuesta.cifra) not in texto:
        avisos.append(f"Cifra descartada: «{propuesta.cifra}» no está en la diapositiva de actualidad")
    elif propuesta.cifra and propuesta.cifra_rotulo:
        palabras = normalizar(propuesta.cifra_rotulo).split()
        sobran = [p for p in palabras if p not in texto.split()]
        if sobran or not 1 <= len(palabras) <= 6:
            avisos.append(f"Rótulo de la cifra descartado: «{propuesta.cifra_rotulo}»")
            propuesta.cifra_rotulo = None
        return avisos
    else:
        return avisos
    propuesta.cifra = propuesta.cifra_rotulo = None
    return avisos


def validar_antetitulo(texto: str | None) -> str | None:
    """De 1 a 3 palabras y 26 caracteres como mucho; si no, sin antetítulo."""
    if not texto:
        return None
    texto = " ".join(texto.split()).strip(" .:·-").upper()
    return texto if 1 <= len(texto.split()) <= 3 and len(texto) <= 26 else None


_INICIOS_PREGUNTA = {"qué", "que", "por", "cómo", "como", "cuándo", "cuando", "dónde", "donde", "quién", "quien",
                     "quiénes", "cuál", "cuáles", "cuánto", "cuánta", "cuántos", "cuántas", "para", "puede", "pueden",
                     "se", "es", "son", "hay", "debe", "deben", "sirve", "sirven", "vale", "tiene", "tienen", "el",
                     "la", "los", "las", "un", "una", "lo", "a", "de", "en", "sin", "si", "libros", "leer"}


def validar_pregunta(texto: str | None) -> str | None:
    """La pregunta del buscador (B2): de 3 a 9 palabras y 48 caracteres, sin cifras ni nombres propios
    (solo siglas en mayúsculas), sin signos de interrogación (el buscador no los lleva)."""
    if not texto:
        return None
    palabras = " ".join(texto.split()).strip(" ¿?.").split()
    if palabras and palabras[0][:1].isupper() and not palabras[0].isupper():
        # La mayúscula de inicio de frase no cuenta, pero solo en las palabras con que empieza una pregunta:
        # «Madrid puede vivir sin coches» lleva un nombre propio
        if palabras[0].lower() not in _INICIOS_PREGUNTA:
            return None
        palabras[0] = palabras[0].lower()
    t = " ".join(palabras)
    # Siglas en mayúsculas (IA, ONU) sí; nombres propios (una mayúscula y minúsculas) no
    propios = [w for w in palabras if w[:1].isupper() and not (w.isupper() and len(w) <= 5)]
    if not 3 <= len(palabras) <= 9 or len(t) > 48 or any(c.isdigit() for c in t) or propios:
        return None
    return t


def validar_remate(remate: str | None, titular: str) -> str | None:
    """El remate tiene que ser literalmente el final del titular, de 2 a 6 palabras, y no todo él."""
    if not remate:
        return None
    r, t = remate.strip().rstrip("."), titular.strip().rstrip(".")
    if not t.endswith(r) or t == r or not 2 <= len(r.split()) <= 6:
        return None
    return r


def _descargar(c: httpx.Client, cand: libres.ImagenLibre) -> Image.Image | None:
    try:
        r = c.get(cand.url)
        r.raise_for_status()
        im = Image.open(BytesIO(r.content))
        im.load()
    except Exception:
        return None
    cand.ancho, cand.alto = im.size
    return im if max(im.size) >= LADO_MINIMO else None


_GRABADO = " AND (engraving OR illustration OR drawing OR lithograph OR woodcut)"


def candidatas(propuesta: PropuestaArte, excluir: set[str] = frozenset()) -> list[tuple[libres.ImagenLibre, Image.Image]]:
    """Imágenes libres para las consultas, ya descargadas y con tamaño suficiente. Si con el
    recurso pedido salen pocas, se completa con las mismas consultas sin restringir el tipo."""
    vistas, out = set(excluir), []
    consultas = [c + _GRABADO if propuesta.recurso == "grabado" else c for c in propuesta.consultas[:4]]
    if propuesta.recurso == "grabado":
        consultas += propuesta.consultas[:4]
    for i, q in enumerate(consultas):
        if i >= 4 and len(out) >= 3:
            break
        try:
            encontradas = [c for c in libres.buscar_europeana(q, 10)
                           if c.libre and c.archivo not in vistas and c.url not in vistas]
        except httpx.HTTPError:
            continue
        for c in encontradas:
            vistas |= {c.archivo, c.url}
        with httpx.Client(headers={"User-Agent": libres.AGENTE}, timeout=30, follow_redirects=True) as cli, \
                ThreadPoolExecutor(max_workers=6) as pool:
            for c, im in zip(encontradas, pool.map(lambda x: _descargar(cli, x), encontradas)):
                if im is not None:
                    out.append((c, im))
        if len(out) >= MAX_CANDIDATAS:
            break
    return out[:MAX_CANDIDATAS]


def hoja_de_contactos(imgs: list[Image.Image]) -> bytes:
    """Rejilla de 3 columnas con el número de cada candidata, en JPEG."""
    cols = 3
    filas = (len(imgs) + cols - 1) // cols
    hoja = Image.new("RGB", (cols * _CELDA, filas * _CELDA), "white")
    dibujo = ImageDraw.Draw(hoja)
    try:
        fuente = ImageFont.load_default(size=40)
    except TypeError:
        fuente = ImageFont.load_default()
    for i, im in enumerate(imgs):
        mini = im.convert("RGB")
        mini.thumbnail((_CELDA - 12, _CELDA - 12))
        x, y = (i % cols) * _CELDA, (i // cols) * _CELDA
        hoja.paste(mini, (x + (_CELDA - mini.width) // 2, y + (_CELDA - mini.height) // 2))
        dibujo.rectangle((x + 6, y + 6, x + 62, y + 56), fill="black")
        dibujo.text((x + 16, y + 8), str(i + 1), fill="white", font=fuente)
    b = BytesIO()
    hoja.save(b, "JPEG", quality=80)
    return b.getvalue()


def _guardar_imagen(cand: libres.ImagenLibre, im: Image.Image, eleccion: EleccionImagen,
                    pieza_id: str, dir_cache_fecha: Path, sufijo: str = "") -> None:
    carpeta = libres.dir_imagenes(dir_cache_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(carpeta / f"{pieza_id}{sufijo}.jpg", quality=92)
    cand.local = f"{pieza_id}{sufijo}.jpg"
    cand.enfoque = (max(0, min(100, eleccion.enfoque_x)), max(0, min(100, eleccion.enfoque_y))) if not sufijo else (50, 50)
    libres.guardar_metadatos(cand, pieza_id + sufijo, dir_cache_fecha)


SUFIJO_NOTICIA = "-noticia"


def _huella(im: Image.Image) -> int:
    """Huella visual (dHash de 64 bits): la misma obra en dos copias o recortes da huellas casi iguales."""
    g = im.convert("L").resize((9, 8))
    px = list(g.tobytes())
    return sum(1 << i for i, (a, b) in enumerate((px[f * 9 + c], px[f * 9 + c + 1]) for f in range(8) for c in range(8)) if a > b)


def misma_imagen(a: Image.Image, b: Image.Image, umbral: int = 10) -> bool:
    """¿Son la misma imagen (otra copia, otro tamaño u otro recorte leve)? Menos de `umbral` bits distintos."""
    return bin(_huella(a) ^ _huella(b)).count("1") < umbral


def _propuesta(llm: LLM, cfg: Config, pieza: Pieza, datos: str, portadas_del_dia: list[str] | None) -> PropuestaArte:
    ya = (f"\ncomposiciones, colores y recursos sin foto ya elegidos hoy para otras piezas (no repitas composición "
          f"ni, si puedes, color ni recurso sin foto): {', '.join(portadas_del_dia)}") if portadas_del_dia else ""
    prompt = cargar_prompt(cfg, "director_arte", {"[pegar pieza]": datos + ya})
    propuesta, _ = llm.estructurado(f"arte:{pieza.id}", [{"role": "user", "content": con_cache(cfg, "director_arte", prompt)}],
                                    PropuestaArte, etapa_modelo="arte", max_tokens=4000)
    return propuesta


def _imagen_de_archivo(llm: LLM, cfg: Config, pieza: Pieza, datos: str, propuesta: PropuestaArte, arte: Arte,
                       usadas: set[str], dir_fecha: Path) -> None:
    """Busca candidatas libres, el modelo elige una viendo la hoja de contactos y se fija.

    Reglas del usuario (1/11): la imagen de archivo no se repite en la pieza. Si va en la portada (no hay
    cara), el director elige una segunda, distinta, para la noticia; si no hay, la noticia lleva la cifra
    o un recurso sin foto. Y nunca dos caras: si la pieza lleva la cara del autor o protagonista, la de
    archivo no puede mostrar personas reconocibles."""
    libres.olvidar(pieza.id, dir_fecha)
    libres.olvidar(pieza.id + SUFIJO_NOTICIA, dir_fecha)
    arte.imagen_noticia = arte.credito_noticia = None
    en_portada = arte.registro == "archivo"
    con_cara = arte.registro in ("foto_autor", "retrato_ia")
    cands = candidatas(propuesta, usadas)
    if not cands:
        arte.avisos.append("Sin imagen: ninguna candidata libre y con tamaño suficiente")
        return
    lista = "\n".join(f"{i}. {c.descripcion[:160]} ({c.institucion or c.fuente})" for i, (c, _) in enumerate(cands, 1))
    texto = cargar_prompt(cfg, "director_arte_eleccion", {
        "[pegar pieza]": f"{datos}\nevitar: {', '.join(propuesta.evitar) or 'nada en particular'}\n"
                         f"suceso con víctimas: {'sí' if propuesta.suceso_con_victimas else 'no'}\n"
                         f"la pieza ya lleva la cara de una persona: {'sí' if con_cara else 'no'}\n"
                         f"hace falta una segunda imagen para la noticia: {'sí' if en_portada else 'no'}",
        "[pegar candidatas]": lista,
    })
    hoja = base64.b64encode(hoja_de_contactos([im for _, im in cands])).decode()
    eleccion, _ = llm.estructurado(f"arte-eleccion:{pieza.id}", [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": hoja}},
        {"type": "text", "text": texto},
    ]}], EleccionImagen, etapa_modelo="arte", max_tokens=2000)
    arte.por_que += f" Imagen: {eleccion.por_que}"
    if eleccion.elegida is None or not 1 <= eleccion.elegida <= len(cands):
        arte.avisos.append("Sin imagen: el director de arte no vio ninguna a la altura")
    elif propuesta.suceso_con_victimas and eleccion.personas_reconocibles:
        arte.avisos.append("Sin imagen: la elegida tiene personas reconocibles y la noticia tiene víctimas")
    elif con_cara and eleccion.personas_reconocibles:
        arte.avisos.append("Sin imagen de archivo: la elegida tiene personas reconocibles y la pieza ya lleva una cara (nunca dos caras)")
    else:
        cand, im = cands[eleccion.elegida - 1]
        _guardar_imagen(cand, im, eleccion, pieza.id, dir_fecha)
        arte.imagen, arte.credito = cand.archivo, cand.credito
        usadas |= {cand.archivo, cand.url}
        if en_portada:
            _segunda(eleccion, cands, cand, propuesta, arte, pieza, usadas, dir_fecha)


def _segunda(eleccion: EleccionImagen, cands, primera: libres.ImagenLibre, propuesta: PropuestaArte, arte: Arte,
             pieza: Pieza, usadas: set[str], dir_fecha: Path) -> None:
    """La segunda imagen de archivo, para la noticia: otra candidata, nunca la misma (ni otra copia suya)."""
    n = eleccion.segunda
    if n is None or not 1 <= n <= len(cands) or n == eleccion.elegida:
        arte.avisos.append("Noticia sin imagen de archivo: no había una segunda distinta; lleva la cifra o un recurso sin foto")
        return
    cand, im = cands[n - 1]
    im_primera = next(i for c, i in cands if c is primera)
    if cand.archivo == primera.archivo or cand.url == primera.url or misma_imagen(im, im_primera):
        arte.avisos.append("Noticia sin imagen de archivo: la segunda era la misma; lleva la cifra o un recurso sin foto")
        return
    if propuesta.suceso_con_victimas and eleccion.segunda_personas_reconocibles:
        arte.avisos.append("Noticia sin imagen de archivo: la segunda tiene personas reconocibles y la noticia tiene víctimas")
        return
    _guardar_imagen(cand, im, eleccion, pieza.id, dir_fecha, SUFIJO_NOTICIA)
    arte.imagen_noticia, arte.credito_noticia = cand.archivo, cand.credito
    usadas |= {cand.archivo, cand.url}


def _del_dia(contar, cfg: Config, pieza: Pieza, dir_fecha: Path) -> int:
    """Lo hecho hoy contra el tope diario: las piezas de verdad y, en una prueba (--solo-pieza, --dev), también
    las de la carpeta de prueba."""
    real = cfg.dir_cache(pieza.fecha)
    return contar(real, pieza.id) + (contar(dir_fecha, pieza.id) if dir_fecha != real else 0)


def _escenas(llm: LLM, cfg: Config, pieza: Pieza, sugerida: str | None, n: int) -> list[tuple[str, str]]:
    """El ilustrador (Opus, prompts/escena_editorial.md) propone escenas distintas a partir de la idea de la pieza
    y de la que sugirió el director. Devuelve [(escena, idea)] válidas; si falla, la del director si vale."""
    validas: list[tuple[str, str]] = []
    try:
        prompt = cargar_prompt(cfg, "escena_editorial", {"[pegar n]": str(max(n, 2)), "[pegar sugerencia]": sugerida or "(ninguna)",
                                                         "[pegar pieza]": _bloque_pieza(pieza, None)})
        r, _ = llm.estructurado(f"escena:{pieza.id}", [{"role": "user", "content": prompt}], EscenasLLM, etapa_modelo="escena", max_tokens=4000)
        prohibidos = editorial.nombres_de_pieza(pieza)
        for e in r.escenas:
            escena, motivo = editorial.validar_escena(e.escena, prohibidos)
            if not escena:
                log.info("Escena descartada para %s (%s): %s", pieza.id, motivo, e.escena[:80])
            if escena and escena not in (x for x, _ in validas):
                validas.append((escena, e.idea.strip()))
    except Exception as exc:
        log.warning("El ilustrador no pudo proponer escenas para %s: %s", pieza.id, exc)
    if not validas and sugerida:
        escena, _ = editorial.validar_escena(sugerida, editorial.nombres_de_pieza(pieza))
        if escena:
            validas.append((escena, ""))
    return validas[:n]


def _elegir_ilustracion(llm: LLM, cfg: Config, pieza: Pieza, dibujos: list[tuple[str, str, Path]]) -> int | None:
    """El director de arte elige una de las ilustraciones viendo la hoja de contactos. Índice o None si ninguna."""
    imgs = [Image.open(r) for _, _, r in dibujos]
    lista = "\n".join(f"{i}. {idea or escena}" for i, (escena, idea, _) in enumerate(dibujos, 1))
    texto = cargar_prompt(cfg, "director_arte_ilustracion", {"[pegar pieza]": _bloque_pieza(pieza, None), "[pegar escenas]": lista})
    hoja = base64.b64encode(hoja_de_contactos(imgs)).decode()
    r, _ = llm.estructurado(f"arte-ilustracion:{pieza.id}", [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": hoja}},
        {"type": "text", "text": texto}]}], EleccionIlustracion, etapa_modelo="arte", max_tokens=1500)
    return r.elegida - 1 if 1 <= r.elegida <= len(dibujos) else None


def _sin_letras(llm: LLM, cfg: Config, pieza: Pieza, dibujos: list[tuple[str, str, Path]],
                fallos: list[str]) -> tuple[list[tuple[str, str, Path]], list[str]]:
    """Quita las variantes con letras o manchas sueltas (2/11). Si no queda ninguna, vuelve a dibujar una vez la
    primera escena (la descartada se borró de la caché, así que sale otra)."""
    limpios, descartes = [], []
    for escena, idea, dibujo in dibujos:
        motivo = editorial.revisar(llm, cfg, pieza.id, dibujo)
        (descartes.append(motivo) if motivo else limpios.append((escena, idea, dibujo)))
    if dibujos and not limpios and not retrato_generado.bloqueado():
        escena, idea, _ = dibujos[0]
        try:
            dibujo = editorial.dibujar(cfg, pieza.id, escena)
            motivo = editorial.revisar(llm, cfg, pieza.id, dibujo)
            (descartes.append(motivo) if motivo else limpios.append((escena, idea, dibujo)))
        except Exception as exc:
            fallos.append(str(exc))
    return limpios, descartes


def _ilustracion_editorial(llm: LLM, cfg: Config, pieza: Pieza, propuesta: PropuestaArte, arte: Arte, dir_fecha: Path) -> bool:
    """La ilustración editorial de la pieza (B1): el ilustrador (Opus) escribe escenas distintas, Magnific dibuja
    `variantes` y el director de arte elige una viendo la hoja de contactos. Si no se puede (desactivada, máximo
    del día, sin escena válida, víctimas, Magnific o ninguna a la altura), se avisa y se busca una foto de archivo:
    devuelve False."""
    ie = cfg.pipeline.arte.ilustracion_editorial
    motivo = None
    if not ie.activo:
        motivo = "desactivada en la configuración"
    elif propuesta.suceso_con_victimas:
        motivo = "con víctimas no se ilustra"
    elif _del_dia(editorial.del_dia, cfg, pieza, dir_fecha) >= ie.max_por_dia:
        motivo = f"ya hay {ie.max_por_dia} hoy (máximo del día)"
    else:
        escenas = _escenas(llm, cfg, pieza, propuesta.escena, ie.variantes)
        dibujos, fallos = [], []
        for escena, idea in escenas:
            try:
                dibujos.append((escena, idea, editorial.dibujar(cfg, pieza.id, escena)))
            except Exception as exc:
                fallos.append(str(exc))
                if retrato_generado.bloqueado():
                    break
        dibujos, descartes = _sin_letras(llm, cfg, pieza, dibujos, fallos)
        if descartes:
            arte.avisos.append(f"Ilustración editorial: descartadas {len(descartes)} con letras o manchas ({'; '.join(descartes)[:240]})")
        if not dibujos:
            motivo = ("sin escena válida" if not escenas else
                      "todas salieron con letras o manchas" if descartes and not fallos else
                      f"no se pudo dibujar ({'; '.join(fallos)[:200]})")
        else:
            try:
                i = _elegir_ilustracion(llm, cfg, pieza, dibujos) if len(dibujos) > 1 else 0
            except Exception as exc:
                arte.avisos.append(f"Ilustración editorial: el director no pudo elegir ({type(exc).__name__}); va la primera")
                i = 0
            if i is None:
                motivo = f"el director no vio ninguna de las {len(dibujos)} a la altura"
            else:
                escena, idea, dibujo = dibujos[i]
                libres.olvidar(pieza.id, dir_fecha)
                img = editorial.fijar(cfg, pieza.id, dir_fecha, escena, dibujo)
                arte.imagen, arte.credito, arte.escena, arte.escena_idea = img.archivo, img.credito, escena, idea or None
                if len(dibujos) > 1:
                    arte.por_que += f" Ilustración: elegida la {i + 1} de {len(dibujos)}."
                return True
    arte.avisos.append(f"Ilustración editorial: {motivo}; se busca una foto de archivo")
    propuesta.recurso = arte.recurso = "foto"
    return False


def _composicion(cfg: Config, pieza: Pieza, propuesta: PropuestaArte, arte: Arte) -> None:
    """Composición, antetítulo, remate y color, ajustados a lo permitido y a lo que hay."""
    permitidas = cfg.pipeline.arte.portadas
    if arte.portada not in permitidas:
        arte.portada = permitidas[0]
    # La ilustración editorial cruza la portada y la noticia como una panorámica (B6)
    if arte.recurso == "ilustracion" and arte.imagen:
        arte.portada = "panorama"
    # El buscador responde con el libro: sin libro (curiosidad del cajón), no hay buscador
    arte.pregunta = validar_pregunta(propuesta.pregunta) if cfg.pipeline.arte.buscador and pieza.guion.libros else None
    arte.antetitulo = validar_antetitulo(propuesta.antetitulo)
    arte.remate = validar_remate(propuesta.remate, pieza.guion.diapositivas[0].texto)
    arte.acento = None if propuesta.suceso_con_victimas or propuesta.tono == "grave" else propuesta.acento
    if arte.portada == "neon" and not arte.acento:
        arte.portada = "sangre"
    if arte.portada == "collage" and not arte.imagen:
        arte.portada = "circulo"
    # El recurso de la diapositiva de actualidad sin foto ni cifra: se guarda siempre que sea válido
    # (la imagen puede fijarse o quitarse después a mano); el render decide si se usa
    grave = propuesta.suceso_con_victimas or propuesta.tono == "grave"
    permitidos = [r for r in cfg.pipeline.arte.sin_foto if not (grave and r == "collage")]   # el collage, nunca en graves
    arte.sin_foto, avisos = sin_foto.validar(propuesta.sin_foto, _texto_actualidad(pieza), permitidos,
                                             propuesta.suceso_con_victimas)
    arte.avisos += avisos
    tipos = [t for t in cfg.pipeline.arte.infografias if not grave or t == "linea"]     # en graves, solo la línea
    arte.infografia, avisos = infografia.validar(propuesta.infografia, pieza, tipos, bool(arte.imagen))
    arte.avisos += avisos
    if not arte.infografia and propuesta.infografia.tipo in ("mapa", "esquema") and "linea" in tipos:
        # Si el mapa o el esquema no se sostienen (rótulos que no salen del guion), la línea de tiempo
        arte.infografia, _ = infografia.validar(Infografia(tipo="linea", titulo=propuesta.infografia.titulo),
                                                pieza, tipos, bool(arte.imagen))
        if arte.infografia:
            arte.avisos.append("Infografía: pasa a la línea de tiempo")


def _ilustracion(llm: LLM, cfg: Config, pieza: Pieza, arte: Arte, dir_fecha: Path) -> None:
    ilustracion.ruta(dir_fecha, pieza.id).unlink(missing_ok=True)
    try:
        campos = yaml.safe_load((cfg.raiz / "diseno" / "tokens.yaml").read_text(encoding="utf-8")).get("campos_portada", {})
        pieza.arte = arte        # el ilustrador lee el tono
        arte.concepto, _ = ilustracion.dibujar(llm, cfg, pieza, campos.get(arte.tono) or campos["sereno"])
    except Exception as exc:
        arte.portada = "circulo"
        arte.avisos.append(f"Sin ilustración ({type(exc).__name__}: {exc}); la portada usa la imagen en círculo")


def autor_principal(pieza: Pieza) -> str | None:
    """El autor del libro principal: el primer libro del guion (con su ficha verificada)."""
    from folio.guion import libro_verificado
    principal = (libro_verificado(pieza.guion.libros[0], pieza.libros) if pieza.guion and pieza.guion.libros else None) \
        or (pieza.libros[0] if pieza.libros else None)
    if principal:
        return principal.autores[0] if principal.autores else None
    # Sin libro (historia editorial, radar): la persona que protagoniza la historia (1/11, a petición del usuario)
    return pieza.eleccion.protagonista.strip() or None


AVISO_RETRATO_GENERADO = "Retrato generado con IA: comprueba el parecido con la foto original antes de publicar"


def _retrato(cfg: Config, pieza: Pieza, arte: Arte, dir_fecha: Path) -> libres.ImagenLibre | None:
    """Busca el retrato del autor del libro principal y lo fija: primero en Wikidata y Commons (fotos
    grandes, con licencia libre); si no hay, la foto de prensa de la web de su editorial (pequeña, con el
    crédito del fotógrafo; folio.imagenes.prensa). No genera nada: eso lo decide dirigir()."""
    for viejo in [*libres.dir_imagenes(dir_fecha).glob(f"{pieza.id}-retrato.*"),
                  *libres.dir_imagenes(dir_fecha).glob(f"{pieza.id}-retrato-original.*")]:
        viejo.unlink()
    pieza.revision_humana = [r for r in pieza.revision_humana if r != AVISO_RETRATO_GENERADO]
    autor = autor_principal(pieza)
    if not autor:
        return None
    img = None
    try:
        img, motivo = retratos.buscar_y_fijar(autor, pieza.id, dir_fecha, cfg.pipeline.arte.retratos_cc_by_sa)
        if not img:
            arte.avisos.append(motivo)
    except Exception as exc:
        arte.avisos.append(f"No se pudo buscar el retrato de {autor} en Commons: {type(exc).__name__}")
    if not img and cfg.pipeline.arte.fotos_editoriales:
        from folio.infografia import libro_principal
        libro = libro_principal(pieza)
        editorial_es = libro.edicion_es_detalle.editorial if libro and libro.edicion_es_detalle else None
        try:
            img, motivo = prensa.buscar_y_fijar(autor, editorial_es or (libro.editorial_original if libro else None),
                                                pieza.id, dir_fecha)
            if not img:
                arte.avisos.append(motivo)
        except prensa.BloqueoEditorial as exc:
            arte.avisos.append(f"Foto de prensa: {exc}; se para sin reintentar")
        except Exception as exc:
            arte.avisos.append(f"No se pudo buscar la foto de prensa de {autor}: {type(exc).__name__}")
    if img:
        arte.retrato = img.credito
    return img


def elegir_registro(hay_retrato: bool, quiere_ilustracion: bool, del_dia: list[str]) -> str:
    """La imagen de portada, por este orden (31/10, reglas del usuario): la foto del autor si la hay; si no,
    la ilustración editorial si el tema es conceptual; si no, el archivo. Para barajar en el día, si la
    pieza anterior ya fue foto de autor y esta admite ilustración, va ilustración. Nunca se baja al
    archivo por barajar."""
    preferido = "foto_autor" if hay_retrato else "ilustracion" if quiere_ilustracion else "archivo"
    anterior = next((r for r in reversed(del_dia) if r), None)
    if preferido == "foto_autor" and anterior in ("foto_autor", "retrato_ia") and quiere_ilustracion:
        return "ilustracion"
    # La vuelta (después de una ilustración, la foto del autor) ya la da el orden: la foto manda. Dos
    # ilustraciones seguidas solo se dan sin foto de autor, y entonces mejor ilustración que archivo.
    return preferido


def toca_retrato_ia(del_dia: list[str]) -> bool:
    """Foto real y retrato generado se alternan en el día: generado si hoy hay menos generados que reales
    (la primera foto de autor del día va real)."""
    return del_dia.count("retrato_ia") < del_dia.count("foto_autor")


def _retrato_generado(cfg: Config, pieza: Pieza, arte: Arte, dir_fecha: Path) -> bool:
    """Pasa el retrato al estilo que toca hoy. Si falla, la pieza se queda con la foto (False)."""
    estilo, hechos = retrato_generado.estilo_del_dia(cfg, pieza.id, dir_fecha, arte.tono)
    if not estilo:
        motivo = (f"ya hay {hechos} hoy (máximo del día)" if hechos >= cfg.pipeline.arte.retrato_generado.max_por_dia
                  else f"el tono «{arte.tono}» no lleva retrato generado")
        arte.avisos.append(f"Retrato generado: {motivo}; se usa la foto")
        return False
    try:
        img = retrato_generado.aplicar(cfg, pieza.id, dir_fecha, estilo)
    except Exception as exc:
        arte.avisos.append(f"Retrato generado: no se pudo ({exc}); se usa la foto")
        return False
    arte.retrato = img.credito
    pieza.revision_humana.append(AVISO_RETRATO_GENERADO)
    return True


def _esquema(cfg: Config, pieza: Pieza, arte: Arte, dir_fecha: Path) -> None:
    """La ilustración técnica de la infografía «esquema» (Magnific). Si no se puede, la infografía pasa a
    la línea de tiempo (si hay años) o se queda sin infografía; la etapa nunca se para."""
    esquema.ruta(dir_fecha, pieza.id).unlink(missing_ok=True)
    if not arte.infografia or arte.infografia.tipo != "esquema":
        return
    ec = cfg.pipeline.arte.esquema
    motivo = None
    if not ec.activo:
        motivo = "desactivado en la configuración"
    elif _del_dia(esquema.del_dia, cfg, pieza, dir_fecha) >= ec.max_por_dia:
        motivo = f"ya hay {ec.max_por_dia} hoy (máximo del día)"
    else:
        try:
            arte.esquema = esquema.generar(cfg, pieza.id, dir_fecha)
            return
        except Exception as exc:
            motivo = f"no se pudo ({exc})"
    linea, _ = infografia.validar(Infografia(tipo="linea", titulo=arte.infografia.titulo), pieza,
                                  cfg.pipeline.arte.infografias, bool(arte.imagen))
    arte.infografia = linea
    arte.avisos.append(f"Esquema: {motivo}; {'la infografía pasa a la línea de tiempo' if linea else 'sin infografía'}")


def _cubiertas(cfg: Config, pieza: Pieza, arte: Arte, dir_fecha: Path) -> None:
    """Deja las cubiertas en la caché: el render y la vista previa de la web las leen de ahí."""
    for libro in pieza.libros:
        try:
            cubiertas.buscar(libro, dir_fecha.parent, cfg.google_books_api_key)
        except Exception as exc:
            arte.avisos.append(f"No se pudo buscar la cubierta de {libro.titulo_propuesto}: {type(exc).__name__}")


def dirigir(llm: LLM, cfg: Config, pieza: Pieza, seccion: str | None, usadas: set[str] | None = None,
            portadas_del_dia: list[str] | None = None, dir_fecha: Path | None = None,
            registros_del_dia: list[str] | None = None) -> Arte:
    """Etapa de arte de una pieza: propuesta, imagen de archivo, composición, ilustración (si toca),
    retrato del autor y cubiertas. `usadas`: imágenes ya elegidas hoy (no se repiten; se añade la
    elegida). `portadas_del_dia`: composiciones y colores ya elegidos hoy, para variar.
    `registros_del_dia`: la imagen de portada de las piezas anteriores del día (foto de autor, retrato
    generado, ilustración, archivo), para barajar (elegir_registro). `dir_fecha`:
    dónde se guardan las imágenes (por defecto, data/cache/<fecha>; las ejecuciones de prueba usan otra
    carpeta para no pisar las de las piezas de verdad, que tienen los mismos ids)."""
    usadas = usadas if usadas is not None else set()
    datos = _bloque_pieza(pieza, seccion)
    dir_fecha = dir_fecha or cfg.dir_cache(pieza.fecha)
    propuesta = _propuesta(llm, cfg, pieza, datos, portadas_del_dia)
    arte = Arte(tono=propuesta.tono, recurso=propuesta.recurso, portada=propuesta.portada, consultas=propuesta.consultas,
                cifra=propuesta.cifra, cifra_rotulo=propuesta.cifra_rotulo, por_que=propuesta.por_que,
                avisos=validar_cifra(propuesta, pieza))
    del_dia = registros_del_dia or []
    retrato = _retrato(cfg, pieza, arte, dir_fecha) if cfg.pipeline.arte.retratos and autor_principal(pieza) else None
    # Apagada (2/11), la ilustración no cuenta ni para barajar: si no, la foto del autor cedía su sitio al archivo
    quiere_ilustracion = propuesta.recurso == "ilustracion" and cfg.pipeline.arte.ilustracion_editorial.activo
    arte.registro = elegir_registro(bool(retrato), quiere_ilustracion, del_dia)
    if arte.registro == "ilustracion" and not _ilustracion_editorial(llm, cfg, pieza, propuesta, arte, dir_fecha):
        arte.registro = "foto_autor" if retrato else "archivo"
    if arte.registro != "ilustracion":
        if quiere_ilustracion:
            if arte.registro == "foto_autor":
                arte.avisos.append("Ilustración editorial: la pieza lleva la foto del autor; se busca una foto de archivo para la noticia")
            propuesta.recurso = arte.recurso = "foto"
        _imagen_de_archivo(llm, cfg, pieza, datos, propuesta, arte, usadas, dir_fecha)
    _composicion(cfg, pieza, propuesta, arte)
    if arte.portada == "ilustracion":
        _ilustracion(llm, cfg, pieza, arte, dir_fecha)
    # El retrato generado (3D) se alterna con la foto real, nunca parte de una foto de prensa (la cesión
    # no permite obras derivadas) y solo cuando la portada es la foto del autor
    if (arte.registro == "foto_autor" and retrato and not prensa.es_de_prensa(retrato)
            and cfg.pipeline.arte.retrato_generado.activo and toca_retrato_ia(del_dia)):
        if _retrato_generado(cfg, pieza, arte, dir_fecha):
            arte.registro = "retrato_ia"
    if arte.registro == "archivo" and not arte.imagen:
        arte.registro = None
    _esquema(cfg, pieza, arte, dir_fecha)
    _cubiertas(cfg, pieza, arte, dir_fecha)
    return arte
