"""Ilustración editorial de la pieza (31/10, B1 del catálogo): una metáfora visual dibujada por Magnific
(Flux 2 Pro desde el 2/11, antes Seedream 4.5, desde texto) con el estilo de la casa (prompts/ilustracion_editorial.md), en 16:9 para que
cruce la portada y la noticia como una panorámica (B6).

La escena la propone el director de arte, en inglés; aquí se comprueba que no trae nombres propios (ni
personas reales, ni marcas, ni artistas), comillas ni cifras, y se le añade el estilo. La imagen se guarda
como la imagen de la pieza (<pieza>.jpg, con sus metadatos), así que el render y la web la tratan como
cualquier otra; su crédito dice que es una ilustración generada con IA para Folio. Caché por prompt en
data/cache/ilustraciones/: relanzar no vuelve a pagar. Comparte con los retratos el cliente y el bloqueo
ante 401, 403 o 429 (folio.imagenes.retrato_generado).

Letras (2/11, a petición del usuario: «evitar esas letras de IA»): Seedream a veces pinta una cabecera de revista
inventada o rótulos ilegibles aunque el prompt lo prohíba. `revisar` enseña cada variante a un modelo barato
(prompts/revisor_letras.md) antes de que el director elija; la que tenga letras o manchas sueltas se descarta y se
borra de la caché (si se vuelve a pedir, se paga y sale otra).
"""

from __future__ import annotations

import hashlib
from datetime import date
import re
import time
from io import BytesIO
from pathlib import Path

import base64

import httpx
from PIL import Image
from pydantic import BaseModel, Field

from folio import gastos
from folio.config import Config
from folio.imagenes import libres, retrato_generado as rg

# Modelos de Magnific para la ilustración (2/11: Flux 2 Pro, elegido por el usuario tras compararlo con Mystic,
# RunWay y Seedream; Seedream 4.5 queda de reserva): ruta, cuerpo de la petición y nombre para el panel de gasto
MODELOS = {
    "flux_2_pro": ("/v1/ai/text-to-image/flux-2-pro", lambda p: {"prompt": p, "width": 1440, "height": 810}, "Flux 2 Pro"),
    "seedream_4_5": ("/v1/ai/text-to-image/seedream-v4-5", lambda p: {"prompt": p, "aspect_ratio": "widescreen_16_9"}, "Seedream 4.5"),
}
CLAVE = "magnific:ilustracion"


def _nombres_propios(texto: str, prohibidos: set[str] = frozenset()) -> list[str]:
    """Palabras con mayúscula dentro de una frase (en inglés, nombres propios) y cualquier palabra que sea un
    nombre propio de la pieza, esté donde esté. La palabra con que empieza una frase sí vale («Wide landscape…»)."""
    propios = []
    for frase in re.split(r"[.!?;:]\s*", texto):
        palabras = re.findall(r"[A-Za-zÀ-ÿ']+", frase)
        propios += [w for i, w in enumerate(palabras) if (i > 0 and w[0].isupper()) or w.lower() in prohibidos]
    return propios


def nombres_de_pieza(pieza) -> set[str]:
    """Los nombres propios de la pieza que una escena no puede llevar: los de los autores y las palabras con
    mayúscula dentro de una frase en el guion (personas, lugares, obras), en minúsculas."""
    nombres = {w.lower() for l in pieza.libros for a in l.autores for w in re.findall(r"[A-Za-zÀ-ÿ']{3,}", a)}
    if pieza.guion:
        for d in pieza.guion.diapositivas:
            for frase in re.split(r"[.!?;:]\s*", d.texto.replace("*", "")):
                nombres |= {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ']{3,}", frase)[1:] if w[0].isupper()}
    return nombres


def estilo(cfg: Config, nombre: str = "collage") -> str:
    """El estilo de la casa (`collage`, sección «## estilo») o el alternativo (`grabado`, «## estilo_grabado»,
    4/11). El friso, la banda y el recorte usan siempre el collage."""
    seccion = "estilo" if nombre == "collage" else f"estilo_{nombre}"
    texto = (cfg.dir_prompts / "ilustracion_editorial.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {seccion}\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m or not m.group(1).strip():
        raise ValueError(f"prompts/ilustracion_editorial.md no tiene la sección «## {seccion}»")
    return m.group(1).strip()


def pieza_base(pieza_id: str) -> str:
    """El id de la pieza sin el sufijo de la ilustración de la noticia (`-noticia`)."""
    return pieza_id[:-len("-noticia")] if pieza_id.endswith("-noticia") else pieza_id


def estilo_de_pieza(cfg: Config, pieza_id: str, dir_fecha: Path) -> str:
    """El estilo de las ilustraciones de una pieza (4/11, a petición del usuario: el grabado se suma al collage y se
    alternan en el día). Si la pieza ya tiene una ilustración, el suyo, para que la portada y la noticia (y lo que
    rehaga el chat) vayan a juego; si no, el siguiente de `estilos` según las piezas ya ilustradas hoy, empezando
    cada día por uno distinto."""
    estilos = cfg.pipeline.arte.ilustracion_editorial.estilos
    if len(estilos) == 1:
        return estilos[0]
    base = pieza_base(pieza_id)
    otras = set()
    for p in libres.dir_imagenes(dir_fecha).glob("*.json"):
        img = libres.de_pieza(p.stem, dir_fecha)
        if not img or img.archivo != CLAVE:
            continue
        if pieza_base(p.stem) == base:
            # Las de antes del 4/11 no guardan el estilo: eran collage
            return img.estilo if img.estilo in estilos else estilos[0]
        otras.add(pieza_base(p.stem))
    try:
        dia = date.fromisoformat(dir_fecha.name).toordinal()
    except ValueError:
        dia = 0
    return estilos[(dia + len(otras)) % len(estilos)]


def validar_escena(escena: str | None, prohibidos: set[str] = frozenset(), max_palabras: int = 70) -> tuple[str | None, str | None]:
    """La escena si sirve; si no, (None, motivo). Sin nombres propios (palabras con mayúscula que no
    empiezan frase), comillas ni cifras, y de 12 a `max_palabras` palabras (el friso, con tres motivos, admite más)."""
    if not escena:
        return None, "sin escena"
    e = " ".join(escena.split())
    if not 12 <= len(e.split()) <= max_palabras:
        return None, f"la escena tiene que tener de 12 a {max_palabras} palabras (tiene {len(e.split())})"
    if re.search(r"[\"“”«»]|\d", e):
        return None, "la escena no puede llevar comillas ni cifras"
    propios = _nombres_propios(e, prohibidos)
    if propios:
        return None, f"la escena no puede llevar nombres propios ({', '.join(propios[:3])})"
    tecnica = sorted({m.group(0).lower() for m in _TECNICA.finditer(e)})
    if tecnica:
        # 3/11 («tenemos un bonito estilo de ilustración, pero está haciendo cosas muy feas»): el chat pedía «luz
        # cálida», «comedor de época»… y Flux pintaba una ilustración realista que no era el collage de la casa
        return None, (f"la escena no puede decir la técnica, la luz ni el acabado ({', '.join(tecnica[:3])}): eso lo pone "
                      "el estilo de la casa (collage); describe solo qué hay, como una metáfora con objetos recortados")
    return e, None


# Palabras de técnica, luz o acabado que hacen a Flux ignorar el collage de la casa (3/11)
_TECNICA = re.compile(r"\b(?:realistic|realism|photo-?realistic|photograph(?:ic)?|cinematic|lighting|warm light|soft light|"
                      r"golden light|glow(?:ing)?|painting|painted|oil|watercolou?r|gouache|render(?:ed|ing)?|3d|detailed|"
                      r"sepia|illustration|illustrated|style)\b", re.I)


def con_estilo(escena: str, estilo: str) -> str:
    """El prompt de la imagen: el estilo de la casa primero, y después la escena (3/11: con la escena delante, una
    escena larga y literal mandaba sobre el estilo y salía una ilustración realista de época, no el collage)."""
    return f"{estilo} The scene: {escena}"


def _pedir(texto: str, clave: str, espera_max_s: float, cliente: httpx.Client | None, modelo: str = "flux_2_pro") -> bytes:
    ruta, cuerpo, _ = MODELOS[modelo]
    with cliente or httpx.Client(timeout=60) as c:
        t0 = time.monotonic()
        tarea = rg._api(c, clave, "POST", ruta, json=cuerpo(texto))
        tid = tarea["task_id"]
        while tarea.get("status") not in ("COMPLETED", "FAILED"):
            if time.monotonic() - t0 > espera_max_s:
                raise rg.ErrorMagnific(f"La tarea {tid} no terminó en {espera_max_s:.0f} s")
            time.sleep(rg.ESPERA_S)
            tarea = rg._api(c, clave, "GET", f"{ruta}/{tid}")
        if tarea["status"] == "FAILED" or not tarea.get("generated"):
            raise rg.ErrorMagnific(f"La tarea {tid} falló")
        r = c.get(tarea["generated"][0])
        r.raise_for_status()
        return r.content


def del_dia(dir_fecha: Path, sin: str) -> int:
    """Ilustraciones editoriales ya hechas hoy, sin contar las de la pieza `sin`."""
    n = 0
    for p in libres.dir_imagenes(dir_fecha).glob("*.json"):
        img = libres.de_pieza(p.stem, dir_fecha)
        n += bool(img and img.archivo == CLAVE and p.stem != sin)
    return n


def quitar_marco(im: Image.Image, maximo: float = 0.08) -> Image.Image:
    """Quita el marco que a veces pinta el modelo aunque el prompt lo prohíbe (4/11, el grabado salió con un margen
    de papel crema y una raya negra): desde cada borde (al menos tres, porque el marco rodea la imagen), las líneas lisas (claras u oscuras) hasta dar con la imagen,
    como mucho un `maximo` de cada lado. Sin marco, la imagen no cambia."""
    gris = im.convert("L")
    ancho, alto = gris.size
    px = gris.load()

    def lisa(valores: list[int]) -> bool:
        media = sum(valores) / len(valores)
        return (sum((v - media) ** 2 for v in valores) / len(valores)) ** 0.5 < 14

    def fila(y): return [px[x, y] for x in range(0, ancho, 4)]
    def columna(x): return [px[x, y] for y in range(0, alto, 4)]

    def cuanto(linea, n, desde_el_final):
        tope, k = int(n * maximo), 0
        while k < tope and lisa(linea(n - 1 - k if desde_el_final else k)):
            k += 1
        return k if k >= 3 else 0      # dos líneas lisas sueltas no son un marco
    izq, der = cuanto(columna, ancho, False), cuanto(columna, ancho, True)
    arr, aba = cuanto(fila, alto, False), cuanto(fila, alto, True)
    # Un marco rodea la imagen: si solo un lado es liso, es el suelo o el cielo de la escena, no un marco
    if sum(bool(k) for k in (izq, der, arr, aba)) < 3:
        return im
    return im.crop((izq, arr, ancho - der, alto - aba))


def dibujar(cfg: Config, pieza_id: str, escena: str, cliente: httpx.Client | None = None,
            nombre_estilo: str = "collage") -> Path:
    """Dibuja una escena (una variante) y devuelve su archivo en la caché común (cache/ilustraciones/): la
    misma escena no se vuelve a pagar. ErrorMagnific si no se puede."""
    if rg.bloqueado():
        raise rg.ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise rg.ErrorMagnific("Falta MAGNIFIC_API_KEY")
    ie = cfg.pipeline.arte.ilustracion_editorial
    texto = con_estilo(escena, estilo(cfg, nombre_estilo))
    huella = hashlib.sha256(f"{ie.modelo}\n{texto}".encode()).hexdigest()[:20]
    cache = cfg.dir_cache("x").parent / "ilustraciones" / f"{huella}.jpg"
    if not cache.exists():
        try:
            datos = _pedir(texto, cfg.magnific_api_key, ie.espera_max_s, cliente, ie.modelo)
            gastos.imagen_magnific(cfg, "ilustración", pieza_id, ie.creditos_imagen, MODELOS[ie.modelo][2])
        except rg.ErrorMagnific as e:
            if e.bloqueo:
                rg._bloqueo = str(e)
            raise
        with Image.open(BytesIO(datos)) as im:
            cache.parent.mkdir(parents=True, exist_ok=True)
            quitar_marco(im.convert("RGB")).save(cache, "JPEG", quality=90)
    return cache


def fijar(cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, dibujo: Path,
          nombre_estilo: str = "collage") -> libres.ImagenLibre:
    """La ilustración elegida pasa a ser la imagen de la pieza (<pieza>.jpg con sus metadatos)."""
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pieza_id}.jpg").write_bytes(dibujo.read_bytes())
    with Image.open(dibujo) as im:
        ancho, alto = im.size
    img = libres.ImagenLibre(archivo=CLAVE, pagina="", url="", ancho=ancho, alto=alto,
                             licencia="ilustración generada con IA (Magnific)", licencia_url=None, autor="Folio",
                             descripcion=escena, libre=True, motivo="", local=f"{pieza_id}.jpg", fuente="",
                             estilo=nombre_estilo)
    libres.guardar_metadatos(img, pieza_id, dir_fecha)
    return img


class RevisionLetras(BaseModel):
    letras: bool = Field(description="True si hay letras, pseudotexto, números, logotipos o firmas")
    manchas: bool = Field(description="True si hay manchas o recuadros sueltos que no pertenecen a la escena")
    donde: str = Field(description="Dónde están, en pocas palabras; vacío si no hay nada")


def _prompt_revisor(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "revisor_letras.md").read_text(encoding="utf-8")
    return texto.split("\n---\n", 1)[1].strip()


def revisar(llm, cfg: Config, pieza_id: str, dibujo: Path, manchas: bool = False) -> str | None:
    """None si la ilustración está limpia; si tiene letras o manchas sueltas, el motivo (y se borra de la caché
    para que otra petición dibuje otra). Si el revisor falla, la imagen pasa (lo mira después el director). Con
    `manchas=False` (por defecto desde el 3/11, cuando el collage pasó a ser el estilo de la casa) solo cuentan las
    letras: en un collage, el papel rasgado y los bloques de color son el estilo (2/11, «Cinco del libro»: el revisor
    tumbaba collages limpios por «manchas sueltas»)."""
    from folio.llm import ErrorLLM
    with Image.open(dibujo) as im:
        im = im.convert("RGB")
        im.thumbnail((1568, 1568))
        buf = BytesIO()
        im.save(buf, "JPEG", quality=88)
    try:
        r, _ = llm.estructurado(f"letras:{pieza_id}", [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": _prompt_revisor(cfg)}]}], RevisionLetras, etapa_modelo="arte", max_tokens=500)
    except (ErrorLLM, ValueError):
        return None
    con_manchas = r.manchas and manchas
    if not (r.letras or con_manchas):
        return None
    dibujo.unlink(missing_ok=True)
    que = " y ".join(x for x, si in (("letras", r.letras), ("manchas sueltas", con_manchas)) if si)
    return f"{que}{f' ({r.donde.strip()})' if r.donde.strip() else ''}"


def generar(cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, cliente: httpx.Client | None = None) -> libres.ImagenLibre:
    """Dibuja la escena y la fija como imagen de la pieza (una sola variante). ErrorMagnific si no se puede."""
    nombre = estilo_de_pieza(cfg, pieza_id, dir_fecha)
    return fijar(cfg, pieza_id, dir_fecha, escena, dibujar(cfg, pieza_id, escena, cliente, nombre), nombre)


def generar_limpia(llm, cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, intentos: int = 2,
                   cliente: httpx.Client | None = None) -> tuple[libres.ImagenLibre | None, list[str]]:
    """Como `generar`, pero revisando las letras: si sale con letras, se dibuja otra (hasta `intentos`).
    Devuelve (imagen o None, motivos de los descartes)."""
    descartes = []
    nombre = estilo_de_pieza(cfg, pieza_id, dir_fecha)
    for _ in range(intentos):
        dibujo = dibujar(cfg, pieza_id, escena, cliente, nombre)
        motivo = revisar(llm, cfg, pieza_id, dibujo)
        if not motivo:
            return fijar(cfg, pieza_id, dir_fecha, escena, dibujo, nombre), descartes
        descartes.append(motivo)
    return None, descartes
