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
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import httpx
import yaml
from PIL import Image, ImageDraw, ImageFont

from folio import cubiertas, ilustracion, imagenes
from folio.config import Config
from folio.llm import LLM, cargar_prompt, con_cache
from folio.modelos import Arte, EleccionImagen, Pieza, PropuestaArte
from folio.verificacion_texto import normalizar

MAX_CANDIDATAS = 9
LADO_MINIMO = 1000          # lado mayor de la imagen original
_CELDA = 360


def _bloque_pieza(pieza: Pieza, seccion: str | None) -> str:
    g = pieza.guion
    diapositivas = "\n".join(f"diapositiva {d.n} ({d.tipo}): {d.texto}" for d in g.diapositivas)
    libros = "\n".join(f"- {l.titulo}, {l.autor}" for l in g.libros)
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


def _descargar(c: httpx.Client, cand: imagenes.ImagenLibre) -> Image.Image | None:
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


def candidatas(propuesta: PropuestaArte, excluir: set[str] = frozenset()) -> list[tuple[imagenes.ImagenLibre, Image.Image]]:
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
            encontradas = [c for c in imagenes.buscar_europeana(q, 10)
                           if c.libre and c.archivo not in vistas and c.url not in vistas]
        except httpx.HTTPError:
            continue
        for c in encontradas:
            vistas |= {c.archivo, c.url}
        with httpx.Client(headers={"User-Agent": imagenes.AGENTE}, timeout=30, follow_redirects=True) as cli, \
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


def _guardar_imagen(cand: imagenes.ImagenLibre, im: Image.Image, eleccion: EleccionImagen,
                    pieza_id: str, dir_cache_fecha: Path) -> None:
    carpeta = imagenes.dir_imagenes(dir_cache_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(carpeta / f"{pieza_id}.jpg", quality=92)
    cand.local = f"{pieza_id}.jpg"
    cand.enfoque = (max(0, min(100, eleccion.enfoque_x)), max(0, min(100, eleccion.enfoque_y)))
    imagenes.guardar_metadatos(cand, pieza_id, dir_cache_fecha)


def dirigir(llm: LLM, cfg: Config, pieza: Pieza, seccion: str | None, usadas: set[str] | None = None) -> Arte:
    """Etapa de arte de una pieza: propuesta, búsqueda, elección e imagen fijada (si la hay).
    `usadas`: imágenes ya elegidas para otras piezas del día (no se repiten); se añade la elegida."""
    usadas = usadas if usadas is not None else set()
    datos = _bloque_pieza(pieza, seccion)
    prompt = cargar_prompt(cfg, "director_arte", {"[pegar pieza]": datos})
    propuesta, _ = llm.estructurado(f"arte:{pieza.id}", [{"role": "user", "content": con_cache(cfg, "director_arte", prompt)}],
                                    PropuestaArte, etapa_modelo="arte", max_tokens=4000)
    avisos = validar_cifra(propuesta, pieza)
    arte = Arte(tono=propuesta.tono, recurso=propuesta.recurso, portada=propuesta.portada, consultas=propuesta.consultas,
                cifra=propuesta.cifra, cifra_rotulo=propuesta.cifra_rotulo, por_que=propuesta.por_que, avisos=avisos)
    dir_fecha = cfg.dir_cache(pieza.fecha)
    imagenes.olvidar(pieza.id, dir_fecha)

    cands = candidatas(propuesta, usadas)
    if not cands:
        arte.avisos.append("Sin imagen: ninguna candidata libre y con tamaño suficiente")
    else:
        lista = "\n".join(f"{i}. {c.descripcion[:160]} ({c.institucion or c.fuente})" for i, (c, _) in enumerate(cands, 1))
        texto = cargar_prompt(cfg, "director_arte_eleccion", {
            "[pegar pieza]": f"{datos}\nevitar: {', '.join(propuesta.evitar) or 'nada en particular'}\n"
                             f"suceso con víctimas: {'sí' if propuesta.suceso_con_victimas else 'no'}",
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
        else:
            cand, im = cands[eleccion.elegida - 1]
            _guardar_imagen(cand, im, eleccion, pieza.id, dir_fecha)
            arte.imagen, arte.credito = cand.archivo, cand.credito
            usadas |= {cand.archivo, cand.url}

    if arte.portada == "collage" and not arte.imagen:
        arte.portada = "circulo"
    if arte.portada == "ilustracion":
        ilustracion.ruta(dir_fecha, pieza.id).unlink(missing_ok=True)
        try:
            campos = yaml.safe_load((cfg.raiz / "diseno" / "tokens.yaml").read_text(encoding="utf-8")).get("campos_portada", {})
            pieza.arte = arte        # el ilustrador lee el tono
            arte.concepto, _ = ilustracion.dibujar(llm, cfg, pieza, campos.get(arte.tono) or campos["sereno"])
        except Exception as exc:
            arte.portada = "circulo"
            arte.avisos.append(f"Sin ilustración ({type(exc).__name__}: {exc}); la portada usa la imagen en círculo")

    for libro in pieza.libros:      # deja las cubiertas en la caché para el render
        try:
            cubiertas.buscar(libro, dir_fecha.parent, cfg.google_books_api_key)
        except Exception as exc:
            arte.avisos.append(f"No se pudo buscar la cubierta de {libro.titulo_propuesto}: {type(exc).__name__}")
    return arte
