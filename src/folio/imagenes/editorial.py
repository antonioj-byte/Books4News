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


def estilo(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "ilustracion_editorial.md").read_text(encoding="utf-8")
    m = re.search(r"^## estilo\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if not m or not m.group(1).strip():
        raise ValueError("prompts/ilustracion_editorial.md no tiene la sección «## estilo»")
    return m.group(1).strip()


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
    return e, None


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


def dibujar(cfg: Config, pieza_id: str, escena: str, cliente: httpx.Client | None = None) -> Path:
    """Dibuja una escena (una variante) y devuelve su archivo en la caché común (cache/ilustraciones/): la
    misma escena no se vuelve a pagar. ErrorMagnific si no se puede."""
    if rg.bloqueado():
        raise rg.ErrorMagnific(f"Magnific bloqueado en esta ejecución: {rg.bloqueado()}", bloqueo=True)
    if not cfg.magnific_api_key:
        raise rg.ErrorMagnific("Falta MAGNIFIC_API_KEY")
    ie = cfg.pipeline.arte.ilustracion_editorial
    texto = f"{escena} {estilo(cfg)}"
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
            im.convert("RGB").save(cache, "JPEG", quality=90)
    return cache


def fijar(cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, dibujo: Path) -> libres.ImagenLibre:
    """La ilustración elegida pasa a ser la imagen de la pieza (<pieza>.jpg con sus metadatos)."""
    carpeta = libres.dir_imagenes(dir_fecha)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pieza_id}.jpg").write_bytes(dibujo.read_bytes())
    with Image.open(dibujo) as im:
        ancho, alto = im.size
    img = libres.ImagenLibre(archivo=CLAVE, pagina="", url="", ancho=ancho, alto=alto,
                             licencia="ilustración generada con IA (Magnific)", licencia_url=None, autor="Folio",
                             descripcion=escena, libre=True, motivo="", local=f"{pieza_id}.jpg", fuente="")
    libres.guardar_metadatos(img, pieza_id, dir_fecha)
    return img


class RevisionLetras(BaseModel):
    letras: bool = Field(description="True si hay letras, pseudotexto, números, logotipos o firmas")
    manchas: bool = Field(description="True si hay manchas o recuadros sueltos que no pertenecen a la escena")
    donde: str = Field(description="Dónde están, en pocas palabras; vacío si no hay nada")


def _prompt_revisor(cfg: Config) -> str:
    texto = (cfg.dir_prompts / "revisor_letras.md").read_text(encoding="utf-8")
    return texto.split("\n---\n", 1)[1].strip()


def revisar(llm, cfg: Config, pieza_id: str, dibujo: Path) -> str | None:
    """None si la ilustración está limpia; si tiene letras o manchas sueltas, el motivo (y se borra de la caché
    para que otra petición dibuje otra). Si el revisor falla, la imagen pasa (lo mira después el director)."""
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
    if not (r.letras or r.manchas):
        return None
    dibujo.unlink(missing_ok=True)
    que = " y ".join(x for x, si in (("letras", r.letras), ("manchas sueltas", r.manchas)) if si)
    return f"{que}{f' ({r.donde.strip()})' if r.donde.strip() else ''}"


def generar(cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, cliente: httpx.Client | None = None) -> libres.ImagenLibre:
    """Dibuja la escena y la fija como imagen de la pieza (una sola variante). ErrorMagnific si no se puede."""
    return fijar(cfg, pieza_id, dir_fecha, escena, dibujar(cfg, pieza_id, escena, cliente))


def generar_limpia(llm, cfg: Config, pieza_id: str, dir_fecha: Path, escena: str, intentos: int = 2,
                   cliente: httpx.Client | None = None) -> tuple[libres.ImagenLibre | None, list[str]]:
    """Como `generar`, pero revisando las letras: si sale con letras, se dibuja otra (hasta `intentos`).
    Devuelve (imagen o None, motivos de los descartes)."""
    descartes = []
    for _ in range(intentos):
        dibujo = dibujar(cfg, pieza_id, escena, cliente)
        motivo = revisar(llm, cfg, pieza_id, dibujo)
        if not motivo:
            return fijar(cfg, pieza_id, dir_fecha, escena, dibujo), descartes
        descartes.append(motivo)
    return None, descartes
