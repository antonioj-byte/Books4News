"""Paso 6: una escena por plano (Claude), dos variantes por plano con Flux 2 Pro (Magnific) para elegir, un revisor
barato que descarta las que traen letras falsas, y los clips de imagen a vídeo (Kling O1) de los planos clave.

Cada imagen se guarda en una caché común por huella (modelo, prompt, semilla): repetir lo mismo no se paga dos veces.
En modo simulado, las variantes son láminas de relleno con el número del plano y la escena.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import textwrap
import zlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from videos import almacen, estilo as est, magnific
from videos.config import RAIZ, Config
from videos.llm import LLM, ErrorLLM
from videos.modelos import EscenasLLM, Gasto, ImagenPlano, RevisionLLM, Variante, ahora
from videos.prompts import cargar

CREDITOS_IMAGEN = 25            # medido en Folio el 31/10 (16.000 créditos = 16 €)
EUR_CREDITO = 0.001
VARIANTES = 2


def _semilla(pid: str, plano: str, k: int) -> int:
    return (zlib.crc32(f"{pid}/{plano}".encode()) + k * 7919) % 2_000_000_000


def escenas(cfg: Config, llm: LLM, pid: str, anunciar=lambda _: None) -> None:
    """Las escenas de todos los planos del guion bloqueado, en una llamada."""
    p = almacen.cargar(cfg, pid)
    v = p.guion_actual
    if v is None or p.etapas["guion"].estado != "bloqueado":
        raise ValueError("Aprueba antes el guion")
    c = p.concepto(p.concepto_elegido or "")
    planos = json.dumps([{"id": x.id, "rol": x.rol, "locucion": x.locucion, "visual": x.visual, "movimiento": x.movimiento}
                         for x in v.planos], ensure_ascii=False, indent=1)
    prompt, _ = cargar(cfg, "imagen", concepto=f"{c.titulo}: {c.idea}" if c else v.titulo, planos=planos)
    anunciar("La directora de arte escribe las escenas")
    r, _ = llm.estructurado("escenas", [{"role": "user", "content": prompt}], EscenasLLM, modelo=cfg.modelo_guion,
                            esfuerzo="medium", max_tokens=8000)
    por_id = {e.id: e for e in r.escenas}
    faltan = [x.id for x in v.planos if x.id not in por_id]
    if faltan:
        raise ErrorLLM(f"Faltan las escenas de {', '.join(faltan)}")
    clips = [x.id for x in v.planos if x.movimiento.lower().startswith("clip animado")][:cfg.max_clips]
    with almacen.editar(cfg, pid) as q:
        for x in v.planos:
            e = por_id[x.id]
            anterior = q.imagenes.get(x.id)
            if anterior and anterior.escena == e.escena.strip():
                continue
            q.imagenes[x.id] = ImagenPlano(escena=e.escena.strip(), animacion=e.animacion.strip() if x.id in clips else "",
                                           prompt=est.prompt_imagen(q.estilo, e.escena) if q.estilo else "")


# ── Una imagen ────────────────────────────────────────────────────────────────────────────────────────────────────

def _fuente(tam: int):
    try:
        return ImageFont.truetype(str(RAIZ / "fuentes" / "OpenSans-Bold.ttf"), tam)
    except OSError:
        return ImageFont.load_default()


def lamina_simulada(plano: str, escena: str, color: str, semilla: int) -> bytes:
    """Imagen de relleno para el modo simulado: el color del estilo, el plano y la escena."""
    im = Image.new("RGB", (magnific.ANCHO, magnific.ALTO), color)
    d = ImageDraw.Draw(im)
    tono = 255 if sum(int(color[i:i + 2], 16) for i in (1, 3, 5)) < 380 else 20
    d.ellipse([140 + semilla % 120, 420, 628 - semilla % 90, 900], outline=(tono,) * 3, width=6)
    d.text((48, 60), f"{plano} · simulada", fill=(tono,) * 3, font=_fuente(40))
    d.multiline_text((48, 980), "\n".join(textwrap.wrap(escena, 34)[:7]), fill=(tono,) * 3, font=_fuente(26), spacing=8)
    out = BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def _revisar(cfg: Config, llm: LLM, datos: bytes) -> RevisionLLM:
    with Image.open(BytesIO(datos)) as im:
        im = im.convert("RGB")
        im.thumbnail((1024, 1024))
        b = BytesIO()
        im.save(b, "JPEG", quality=85)
    prompt, _ = cargar(cfg, "revisor_letras")
    contenido = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": base64.b64encode(b.getvalue()).decode()}},
                 {"type": "text", "text": prompt}]
    r, _ = llm.estructurado("revisor-letras", [{"role": "user", "content": contenido}], RevisionLLM,
                            modelo=cfg.modelo_revisor, esfuerzo="low", max_tokens=1500)
    return r


def _una(cfg: Config, llm: LLM, pid: str, plano: str, prompt: str, escena: str, semilla: int, color: str) -> tuple[bytes, Variante]:
    if cfg.magnific_simulado:
        return lamina_simulada(plano, escena, color, semilla), Variante(archivo="", semilla=semilla, simulada=True)
    aviso = ""
    for intento in range(2):
        s = semilla + intento * 100_003
        h = hashlib.sha256(json.dumps(["flux-2-pro", magnific.ANCHO, magnific.ALTO, prompt, s]).encode()).hexdigest()
        cache = cfg.cache / "magnific" / f"{h}.jpg"
        if cache.exists():
            datos = cache.read_bytes()
        else:
            datos, _ = magnific.imagen(cfg.magnific_api_key, prompt, s)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(datos)
            with almacen.editar(cfg, pid) as q:
                q.gasto.append(Gasto(etapa="imagenes", servicio="magnific", modelo="flux-2-pro",
                                     usd=round(CREDITOS_IMAGEN * EUR_CREDITO, 3), detalle=f"{plano} · {CREDITOS_IMAGEN} créditos (€)"))
        try:
            rev = _revisar(cfg, llm, datos)
        except Exception:
            rev = RevisionLLM(tiene_texto=False, donde="")
        if not rev.tiene_texto:
            return datos, Variante(archivo="", semilla=s, aviso=aviso)
        aviso = f"Letras falsas en {rev.donde}" if rev.donde else "Letras falsas"
        cache.unlink(missing_ok=True)
    return datos, Variante(archivo="", semilla=s, aviso=aviso + " (se rehízo una vez y siguen)")


def generar_plano(cfg: Config, llm: LLM, pid: str, plano: str, anunciar=lambda _: None) -> int:
    """Dos variantes más para el plano. Devuelve cuántas tiene en total."""
    p = almacen.cargar(cfg, pid)
    ip = p.imagenes.get(plano)
    if ip is None or p.estilo is None:
        raise ValueError("Faltan la escena o el estilo de ese plano")
    prompt = est.prompt_imagen(p.estilo, ip.escena)
    ya = len(ip.variantes)
    color = p.estilo.paleta[0] if p.estilo.paleta else "#222222"
    dir_img = almacen.carpeta(cfg, pid) / "img"
    dir_img.mkdir(parents=True, exist_ok=True)
    nuevas = []
    for k in range(ya, ya + VARIANTES):
        datos, var = _una(cfg, llm, pid, plano, prompt, ip.escena, _semilla(pid, plano, k), color)
        nombre = f"img/{plano}-{k + 1}.jpg"
        (almacen.carpeta(cfg, pid) / nombre).write_bytes(datos)
        var.archivo = nombre
        nuevas.append(var)
    with almacen.editar(cfg, pid) as q:
        qi = q.imagenes[plano]
        qi.prompt = prompt
        qi.variantes.extend(nuevas)
        qi.error = None
        if qi.elegida is None:          # queda preelegida la primera sin avisos; quien edita la cambia
            limpias = [i for i, v in enumerate(qi.variantes) if not v.aviso]
            qi.elegida = limpias[0] if limpias else 0
        qi.estado = "lista"
        return len(qi.variantes)


def generar_todas(cfg: Config, llm: LLM, pid: str, anunciar=lambda _: None) -> int:
    p = almacen.cargar(cfg, pid)
    if not p.imagenes:
        escenas(cfg, llm, pid, anunciar)
        p = almacen.cargar(cfg, pid)
    pendientes = [k for k, v in p.imagenes.items() if not v.variantes]
    hechas = [0]

    def una(k):
        try:
            generar_plano(cfg, llm, pid, k)
        except magnific.ErrorMagnific as e:
            with almacen.editar(cfg, pid) as q:
                q.imagenes[k].estado, q.imagenes[k].error = "fallida", str(e)
            if e.bloqueo:
                raise
        hechas[0] += 1
        anunciar(f"Imágenes: {hechas[0]} de {len(pendientes)} planos")

    anunciar(f"Imágenes: 0 de {len(pendientes)} planos")
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(una, pendientes))
    with almacen.editar(cfg, pid) as q:
        q.etapas["imagenes"].estado = "propuesta"
        q.etapas["imagenes"].actualizado = ahora()
    return len(pendientes)


def elegir(cfg: Config, pid: str, plano: str, indice: int) -> None:
    with almacen.editar(cfg, pid) as p:
        ip = p.imagenes.get(plano)
        if ip is None or not 0 <= indice < len(ip.variantes):
            raise ValueError("Esa variante no existe")
        if ip.elegida != indice:
            ip.clip = None                     # el clip era de la otra imagen
        ip.elegida = indice
        ip.estado = "elegida"
        if p.etapas["montaje"].estado == "hecha":
            p.etapas["montaje"].estado = "desfasada"
        if all(x.elegida is not None for x in p.imagenes.values()):
            p.etapas["imagenes"].estado = "hecha"


# ── Muestras de los estilos ───────────────────────────────────────────────────────────────────────────────────────

def muestras(cfg: Config, llm: LLM, pid: str, anunciar=lambda _: None) -> int:
    """Una imagen del primer plano en cada estilo predefinido, para elegir viendo (3 × 25 créditos)."""
    p = almacen.cargar(cfg, pid)
    if not p.imagenes:
        escenas(cfg, llm, pid, anunciar)
        p = almacen.cargar(cfg, pid)
    primero = next(iter(p.imagenes))
    escena = p.imagenes[primero].escena
    dir_m = almacen.carpeta(cfg, pid) / "muestras"
    dir_m.mkdir(parents=True, exist_ok=True)
    from videos.modelos import Estilo
    hechas = 0
    for clave, datos in est.predefinidos().items():
        anunciar(f"Muestra del estilo «{datos['nombre']}»")
        e = Estilo(id=clave, **datos)
        img, _ = _una(cfg, llm, pid, primero, est.prompt_imagen(e, escena), escena, _semilla(pid, primero, 0), e.paleta[0])
        (dir_m / f"{clave}.jpg").write_bytes(img)
        hechas += 1
    return hechas


# ── Clips ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def clips(cfg: Config, llm: LLM, pid: str, anunciar=lambda _: None) -> int:
    """Imagen a vídeo de los planos clave (los que el guion marca como «clip animado», como mucho `max_clips`)."""
    from videos import montaje
    p = almacen.cargar(cfg, pid)
    planos = [(k, v) for k, v in p.imagenes.items() if v.animacion and v.elegida is not None and not v.clip]
    for n, (k, v) in enumerate(planos, 1):
        anunciar(f"Animando el plano {k} ({n} de {len(planos)})")
        origen = almacen.carpeta(cfg, pid) / v.variantes[v.elegida].archivo
        destino = f"clips/{k}-{v.elegida + 1}.mp4"
        ruta = almacen.carpeta(cfg, pid) / destino
        ruta.parent.mkdir(parents=True, exist_ok=True)
        simulado = cfg.magnific_simulado or v.variantes[v.elegida].simulada
        if simulado:
            montaje.ken_burns(origen, ruta, 5.0, "zoom lento hacia el centro")
        else:
            h = hashlib.sha256(json.dumps(["kling-o1-std", hashlib.sha256(origen.read_bytes()).hexdigest(), v.animacion]).encode()).hexdigest()
            cache = cfg.cache / "kling" / f"{h}.mp4"
            if not cache.exists():
                datos, _ = magnific.clip(cfg.magnific_api_key, origen.read_bytes(), v.animacion, 5)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(datos)
                with almacen.editar(cfg, pid) as q:
                    q.gasto.append(Gasto(etapa="imagenes", servicio="magnific", modelo="kling-o1-std", usd=0.0,
                                         detalle=f"{k} · clip de 5 s (créditos por medir en el panel)"))
            shutil.copyfile(cache, ruta)
        with almacen.editar(cfg, pid) as q:
            q.imagenes[k].clip = destino
            q.imagenes[k].clip_simulado = simulado
    return len(planos)
