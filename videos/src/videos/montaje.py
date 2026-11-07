"""Paso 7: el montaje con FFmpeg. Cada plano dura lo que dice la voz (los tiempos de ElevenLabs); su imagen elegida
se mueve con Ken Burns (o va su clip de Kling, recortado a su duración), los subtítulos salen palabra a palabra con la
que suena resaltada (ASS, libass), el texto en pantalla arriba, la cita con su referencia, una tarjeta final con el
libro y, si se quiere, la cama musical bajo la voz con ducking. MP4 1080×1920, H.264 + AAC, y un .srt aparte.

Zonas seguras (Reels y TikTok) sobre 1080×1920: nada de texto en los 220 px de arriba, los 420 de abajo ni los 140 de
la derecha. El texto en pantalla va entre 330 y 560 px; los subtítulos, con su base en 1290 px.

Ninguna imagen está quieta: todo plano se mueve; uno que pase de `LARGO_S` se parte y entra la otra variante.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from videos import almacen
from videos.config import RAIZ, Config
from videos.modelos import Montaje, Palabra, ahora

W, H, FPS = 1080, 1920, 30
LARGO_S = 4.5
TARJETA_S = 2.2
FUENTES = RAIZ / "fuentes"
SUB_BASE_Y = 1290
PANTALLA_Y = 330
MARGEN_IZQ, MARGEN_DCHA = 64, 64 + 140


class ErrorMontaje(RuntimeError):
    pass


def _ffmpeg(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorMontaje(f"ffmpeg: {r.stderr[-600:]}")


def _huella(*partes) -> str:
    return hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()[:16]


# ── Movimiento ────────────────────────────────────────────────────────────────────────────────────────────────────

def _expresiones(movimiento: str, n: int) -> tuple[str, str, str]:
    m = movimiento.lower()
    p = f"(on/{max(n - 1, 1)})"
    centro_x, centro_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if "alej" in m or "zoom out" in m:
        return f"1.14-0.14*{p}", centro_x, centro_y
    if "travelling" in m or "lateral" in m or "paneo horizontal" in m:
        x = f"(iw-iw/zoom)*{p}" if "derecha" in m else f"(iw-iw/zoom)*(1-{p})"
        return "1.14", x, centro_y
    if "vertical" in m or "arriba" in m or "abajo" in m:
        y = f"(ih-ih/zoom)*(1-{p})" if "arriba" in m else f"(ih-ih/zoom)*{p}"
        return "1.14", centro_x, y
    return f"1+0.14*{p}", centro_x, centro_y          # zoom lento hacia el centro (y lo que no se reconoce)


def ken_burns(imagen: Path, destino: Path, segundos: float, movimiento: str) -> None:
    n = max(2, int(round(segundos * FPS)))
    z, x, y = _expresiones(movimiento, n)
    # Se escala al doble antes del zoompan para que el movimiento no tiemble
    _ffmpeg("-i", str(imagen), "-vf",
            f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p",
            "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), str(destino))


def tramo_de_clip(clip: Path, destino: Path, segundos: float) -> None:
    _ffmpeg("-i", str(clip), "-vf",
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
            f"tpad=stop_mode=clone:stop_duration={segundos:.3f},format=yuv420p",
            "-t", f"{segundos:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(destino))


def tarjeta(destino: Path, titulo: str, autor: str, fondo: str, tinta: str) -> None:
    im = Image.new("RGB", (W, H), fondo)
    d = ImageDraw.Draw(im)
    f_a = ImageFont.truetype(str(FUENTES / "EBGaramond-Italic.ttf"), 64)
    ancho_max = W - 2 * (MARGEN_IZQ + 40)
    for tam in (104, 92, 80, 68, 58, 50):          # el cuerpo mayor con el que caben las palabras sin partirlas
        f_t = ImageFont.truetype(str(FUENTES / "Alexandria-Bold.ttf"), tam)
        lineas = textwrap.wrap(titulo, max(6, int(ancho_max / (tam * 0.58))), break_long_words=False)[:4]
        if all(d.textlength(l, font=f_t) <= ancho_max for l in lineas):
            break
    y = H // 2 - int(tam * 0.75) * len(lineas)
    for l in lineas:
        w = d.textlength(l, font=f_t)
        d.text(((W - w) / 2, y), l, fill=tinta, font=f_t)
        y += int(tam * 1.18)
    if autor:
        w = d.textlength(autor, font=f_a)
        d.text(((W - w) / 2, y + 30), autor, fill=tinta, font=f_a)
    im.save(destino, "JPEG", quality=92)


# ── Subtítulos ────────────────────────────────────────────────────────────────────────────────────────────────────

def _ass_color(hexa: str) -> str:
    h = hexa.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _t(s: float) -> str:
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _esc(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def trozos(palabras: list[Palabra], max_palabras: int = 3, max_chars: int = 18) -> list[list[Palabra]]:
    """Grupos de palabras para los subtítulos: pocos, que no crucen de plano ni pasen un punto."""
    grupos, actual = [], []
    for w in palabras:
        if actual and (w.plano != actual[-1].plano or len(actual) >= max_palabras
                       or len(" ".join(x.t for x in actual + [w])) > max_chars):
            grupos.append(actual)
            actual = []
        actual.append(w)
        if re.search(r"[.?!…:]$", w.t):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def escribir_ass(ruta: Path, palabras: list[Palabra], pantallas: list[tuple[float, float, str]],
                 citas: list[tuple[float, float, str, str]], acento: str = "#FFF500") -> None:
    papel, tinta = _ass_color("#F6F3EE"), _ass_color("#1C1618")
    resalte = _ass_color(acento)
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subs,Alexandria,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,-1,0,1,6,2,2,{MARGEN_IZQ},{MARGEN_DCHA},{H - SUB_BASE_Y},1
Style: Pantalla,Alexandria,64,{tinta},{tinta},{papel},{papel},0,0,0,0,100,100,-1,0,3,18,0,8,{MARGEN_IZQ + 40},{MARGEN_DCHA + 40},{PANTALLA_Y},1
Style: Cita,EB Garamond,54,{tinta},{tinta},{papel},{papel},0,1,0,0,100,100,0,0,3,20,0,8,{MARGEN_IZQ + 30},{MARGEN_DCHA + 30},{PANTALLA_Y},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    grupos = trozos(palabras)
    for g, grupo in enumerate(grupos):
        fin_grupo = grupos[g + 1][0].i if g + 1 < len(grupos) and grupos[g + 1][0].i - grupo[-1].f < 0.6 else grupo[-1].f + 0.25
        for k, w in enumerate(grupo):
            ini = grupo[0].i if k == 0 else w.i
            fin = grupo[k + 1].i if k + 1 < len(grupo) else fin_grupo
            texto = " ".join((f"{{\\c{resalte}}}{_esc(x.t)}{{\\c&H00FFFFFF&}}" if x is w else _esc(x.t)) for x in grupo)
            ev.append(f"Dialogue: 1,{_t(ini)},{_t(fin)},Subs,,0,0,0,,{texto}")
    for ini, fin, texto in pantallas:
        ev.append(f"Dialogue: 0,{_t(ini)},{_t(fin)},Pantalla,,0,0,0,,{{\\fad(120,120)}}{_esc(texto)}")
    for ini, fin, texto, ref in citas:
        ev.append(f"Dialogue: 0,{_t(ini)},{_t(fin)},Cita,,0,0,0,,{{\\fad(150,150)}}«{_esc(texto)}»\\N{{\\fs36\\i0}}{_esc(ref)}")
    ruta.write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")


def escribir_srt(ruta: Path, palabras: list[Palabra]) -> None:
    def t(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    grupos = trozos(palabras, 6, 42)
    bloques = [f"{n}\n{t(g[0].i)} --> {t(g[-1].f)}\n{' '.join(w.t for w in g)}\n" for n, g in enumerate(grupos, 1)]
    ruta.write_text("\n".join(bloques), encoding="utf-8")


# ── El vídeo ──────────────────────────────────────────────────────────────────────────────────────────────────────

def montar(cfg: Config, pid: str, anunciar=lambda _: None) -> Montaje:
    p = almacen.cargar(cfg, pid)
    v, voz = p.guion_actual, p.voz
    if voz is None:
        raise ValueError("Falta la locución")
    faltan = [x.id for x in v.planos if x.id not in p.imagenes or p.imagenes[x.id].elegida is None]
    if faltan:
        raise ValueError(f"Faltan imágenes elegidas en {', '.join(faltan)}")
    carpeta = almacen.carpeta(cfg, pid)
    seg_dir = carpeta / "segmentos"
    seg_dir.mkdir(parents=True, exist_ok=True)
    tramos: list[Path] = []
    for n, x in enumerate(v.planos, 1):
        anunciar(f"Montando el plano {n} de {len(v.planos)}")
        t = voz.planos[x.id]
        dur = max(0.4, t.fin - t.inicio)
        ip = p.imagenes[x.id]
        img = carpeta / ip.variantes[ip.elegida].archivo
        if ip.clip and (carpeta / ip.clip).exists():
            destino = seg_dir / f"{x.id}-{_huella(ip.clip, dur)}.mp4"
            if not destino.exists():
                tramo_de_clip(carpeta / ip.clip, destino, dur)
            tramos.append(destino)
            continue
        partes = [(img, dur, x.movimiento)]
        otra = next((carpeta / var.archivo for i, var in enumerate(ip.variantes) if i != ip.elegida and not var.aviso), None)
        if dur > LARGO_S and otra:
            mitad = round(dur / 2, 3)
            contrario = "alejamiento lento" if "alej" not in x.movimiento.lower() else "zoom lento hacia el centro"
            partes = [(img, mitad, x.movimiento), (otra, round(dur - mitad, 3), contrario)]
        for k, (im, d, mov) in enumerate(partes):
            destino = seg_dir / f"{x.id}-{k}-{_huella(im.name, im.stat().st_mtime_ns, d, mov)}.mp4"
            if not destino.exists():
                ken_burns(im, destino, d, mov)
            tramos.append(destino)
    est = p.estilo
    fondo = est.paleta[0] if est and est.paleta else "#1C1618"
    tinta = "#F6F3EE" if sum(int(fondo.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) < 380 else "#1C1618"
    tarjeta_img = seg_dir / "tarjeta.jpg"
    tarjeta(tarjeta_img, p.libro.titulo, p.libro.autor, fondo, tinta)
    tarjeta_mp4 = seg_dir / f"tarjeta-{_huella(p.libro.titulo, p.libro.autor, fondo)}.mp4"
    ken_burns(tarjeta_img, tarjeta_mp4, TARJETA_S, "zoom lento hacia el centro")
    tramos.append(tarjeta_mp4)

    anunciar("Uniendo los planos")
    lista = seg_dir / "lista.txt"
    lista.write_text("".join(f"file '{t.resolve()}'\n" for t in tramos), encoding="utf-8")
    mudo = seg_dir / "mudo.mp4"
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(mudo))
    total = round(voz.duracion + TARJETA_S, 3)

    pantallas, citas = [], []
    for x in v.planos:
        t = voz.planos[x.id]
        if x.cita and x.cita.texto:
            ref = f"— {p.libro.autor}, cap. {x.cita.capitulo}" + (f", pág. {x.cita.pagina}" if x.cita.pagina else "")
            citas.append((t.inicio, t.fin, x.cita.texto, ref))
        elif x.pantalla:
            pantallas.append((t.inicio, t.fin, x.pantalla))
    acento = "#FFF500"
    if est and len(est.paleta) >= 4:
        acento = est.paleta[3]
    version = len(p.montajes) + 1
    salida_dir = carpeta / "salida"
    salida_dir.mkdir(exist_ok=True)
    ass = salida_dir / f"subtitulos-{version}.ass"
    escribir_ass(ass, voz.palabras, pantallas, citas, acento)
    srt = salida_dir / f"video-{version}.srt"
    escribir_srt(srt, voz.palabras)

    anunciar("Mezclando voz, música y subtítulos")
    salida = salida_dir / f"video-{version}.mp4"
    entradas = ["-i", str(mudo), "-i", str(carpeta / voz.audio)]
    con_musica = bool(p.musica_activa and p.musica and (carpeta / p.musica).exists())
    if con_musica:
        entradas += ["-stream_loop", "-1", "-i", str(carpeta / p.musica)]
        audio = (f"[1:a]apad=whole_dur={total},asplit=2[voz][lado];"
                 f"[2:a]atrim=0:{total},volume=0.32,afade=t=out:st={total - 1.5}:d=1.5[mus];"
                 f"[mus][lado]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=400[duck];"
                 f"[voz][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    else:
        audio = f"[1:a]apad=whole_dur={total}[a]"
    filtro = f"[0:v]ass='{ass}':fontsdir='{FUENTES}'[v];{audio}"
    _ffmpeg(*entradas, "-filter_complex", filtro, "-map", "[v]", "-map", "[a]", "-t", f"{total}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(salida))
    m = Montaje(version=version, archivo=f"salida/{salida.name}", srt=f"salida/{srt.name}", duracion=total,
                con_musica=con_musica)
    with almacen.editar(cfg, pid) as q:
        q.montajes.append(m)
        q.etapas["montaje"].estado = "hecha"
        q.etapas["montaje"].actualizado = ahora()
    return m
