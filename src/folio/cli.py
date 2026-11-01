"""Línea de comandos: `folio run`, `folio libro`."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

import typer
from pathlib import Path

from folio import config

app = typer.Typer(add_completion=False, help="Folio Lateral: la actualidad leída a través de libros.")


def _logging(verbose: bool):
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for ruidoso in ("httpx", "httpcore", "huggingface_hub", "trafilatura"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


@app.command()
def run(
    fecha: str = typer.Option(None, help="Fecha del informe (AAAA-MM-DD). Por defecto, hoy; con --dev, la última con selección guardada"),
    desde: str = typer.Option(None, help="Etapa desde la que ejecutar: ingesta | seleccion | guion | hechos | arte. Por defecto, ingesta; con --dev, guion"),
    sin_llm: bool = typer.Option(False, "--sin-llm", help="Solo ingesta y agrupación, sin llamar a modelos"),
    dev: bool = typer.Option(False, "--dev", help="Modo desarrollo: modelo barato en todas las etapas, informe en informes/<fecha>-dev/ y sin tocar historial ni etapas guardadas"),
    solo_pieza: int = typer.Option(None, "--solo-pieza", help="Genera solo la pieza N de la selección (prueba: no se registra en el historial)"),
    reutilizar_llm: bool = typer.Option(False, "--reutilizar-llm", help="Sirve de data/cache/llm/ las peticiones idénticas a otras ya hechas (0 $)"),
    verbose: bool = typer.Option(True, "--verbose/--quiet"),
):
    """Ejecuta el pipeline diario y escribe informes/<fecha>/informe.{json,md}."""
    _logging(verbose)
    from folio.llm import LLM
    from folio.pipeline import Pipeline

    desde = desde or ("guion" if dev else "ingesta")
    if desde not in ("ingesta", "seleccion", "guion", "hechos", "arte"):
        raise typer.BadParameter("--desde debe ser ingesta, seleccion, guion, hechos o arte")
    cfg = config.cargar()
    if not fecha:
        fecha = (config.ultima_fecha_con_seleccion(cfg) if dev else None) or date.today().isoformat()
    if dev:
        cfg = config.perfil_dev(cfg)
    if not sin_llm and not cfg.anthropic_api_key:
        typer.echo("Falta ANTHROPIC_API_KEY (o FOLIO_ANTHROPIC_API_KEY): ponla en las variables de entorno del "
                   "servicio (en local, en .env). Para probar solo la ingesta: --sin-llm.", err=True)
        raise typer.Exit(1)
    pipeline = Pipeline(cfg, fecha, llm=LLM(cfg, reutilizar=reutilizar_llm), dev=dev, solo_pieza=solo_pieza)
    inf, (ruta_json, ruta_md) = pipeline.ejecutar(desde=desde, sin_llm=sin_llm)
    buenas = sum(p.estado == "propuesta" for p in inf.piezas)
    typer.echo(f"\nPiezas propuestas: {buenas}/{len(inf.piezas)} · coste estimado {inf.coste_total_usd:.2f} $")
    typer.echo(f"Informe: {ruta_md}\nDatos:   {ruta_json}")


@app.command()
def render(
    fecha: str = typer.Option(None, help="Fecha (AAAA-MM-DD). Por defecto, la última con selección guardada"),
    pieza: str = typer.Option(None, help="Solo esta pieza (p. ej. 2026-10-30-1)"),
    direccion: str = typer.Option(None, help="Propuesta de diseno/propuestas/ («todas» para todas); "
                                             "sin ella, el design system en uso"),
    video: bool = typer.Option(False, "--video", help="También en MP4 las diapositivas animadas (portada, noticia, idea)"),
):
    """Render de las piezas del día a PNG (1080×1350) en informes/<fecha>/render/."""
    _logging(False)
    from folio.modelos import Pieza
    from folio.render import direcciones, renderizar, renderizar_video
    from pydantic import TypeAdapter

    cfg = config.cargar()
    fecha = fecha or config.ultima_fecha_con_seleccion(cfg) or date.today().isoformat()
    ruta = cfg.dir_informes / fecha / "informe.json"
    if not ruta.exists():
        typer.echo(f"No existe {ruta}: ejecuta antes folio run", err=True)
        raise typer.Exit(1)
    piezas = TypeAdapter(list[Pieza]).validate_python(json.loads(ruta.read_text(encoding="utf-8"))["piezas"])
    piezas = [p for p in piezas if p.guion and (pieza is None or p.id == pieza)]
    for d in (direcciones(cfg) if direccion == "todas" else [direccion]):
        destino = cfg.dir_informes / fecha / "render" / (d or "")
        archivos, avisos = renderizar(cfg, piezas, destino, d)
        for a in avisos:
            typer.echo(f"Aviso: {a}")
        typer.echo(f"{len(archivos)} diapositivas en {destino}")
        if video:
            videos, avisos = renderizar_video(cfg, piezas, destino, d)
            for a in avisos:
                typer.echo(f"Aviso: {a}")
            typer.echo(f"{len(videos)} diapositivas en vídeo en {destino}")
        if not d:
            # Las piezas del informe son la versión 1 de la última ejecución del día
            from folio.almacen import Almacen
            from folio.render import marcar_render
            eid = Almacen(cfg.ruta_db).ultima_ejecucion(fecha) if cfg.ruta_db.exists() else None
            for p in piezas:
                marcar_render(destino / p.id, eid, 1)


@app.command("fuentes-editoriales")
def fuentes_editoriales(csv_medios: Path = typer.Argument(..., help="medios.csv de publishing-monitor")):
    """Importa los feeds RSS activos de publishing-monitor a config/fuentes_editoriales.yaml (carril editorial)."""
    import csv

    import yaml

    cfg = config.cargar()
    filas = [f for f in csv.DictReader(csv_medios.open(encoding="utf-8"))
             if f.get("activo", "").lower() == "true" and f.get("metodo") == "rss" and f.get("url_rss")]
    fuentes = [{"medio": f["nombre"], "idioma": f.get("idioma") or "en", "acceso": "abierto",
                "url": f["url_rss"], "tier": int(f["tier"]) if (f.get("tier") or "").isdigit() else None} for f in filas]
    destino = cfg.raiz / "config" / "fuentes_editoriales.yaml"
    cabecera = ("# Carril editorial: medios del mundo del libro, importados de publishing-monitor (medios.csv)\n"
                "# con `folio fuentes-editoriales`. Solo los feeds RSS activos. tier 1 = medio de referencia.\n")
    destino.write_text(cabecera + yaml.safe_dump({"fuentes": fuentes}, allow_unicode=True, sort_keys=False, width=200),
                       encoding="utf-8")
    typer.echo(f"{len(fuentes)} fuentes en {destino}")


imagen_app = typer.Typer(help="Imágenes libres de uso (Wikimedia Commons) para las piezas")
app.add_typer(imagen_app, name="imagen")


@imagen_app.command("buscar")
def imagen_buscar(consulta: str, n: int = typer.Option(12, help="Resultados"),
                  fuente: str = typer.Option("europeana", help="europeana o commons")):
    """Busca imágenes libres y muestra la licencia comprobada de cada resultado."""
    from folio.imagenes import libres as imgs

    for c in imgs.buscar(consulta, n, fuente):
        marca = "libre" if c.libre else f"NO ({c.motivo})"
        typer.echo(f"{c.archivo}\n    {c.descripcion[:90]}\n    {c.licencia} · {marca} · {c.credito[:90]}")


@imagen_app.command("fijar")
def imagen_fijar(pieza: str, archivo: str, fecha: str = typer.Option(None, help="Por defecto, la de la pieza")):
    """Descarga la imagen para la pieza (clave de «folio imagen buscar»; solo si es libre)."""
    from folio.imagenes import libres as imgs

    cfg = config.cargar()
    fecha = fecha or pieza[:10]
    try:
        img = imgs.ficha(archivo)
        ruta = imgs.fijar(img, pieza, cfg.dir_cache(fecha))
    except ValueError as e:
        typer.echo(f"Rechazada: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{ruta} · {img.credito}")


PIEZA_LISTA = "La pieza ya está en la mesa"     # la web (Proceder.tsx) recarga al ver esta etapa


@app.command()
def desarrollar(pieza: str, ejecucion: int = typer.Option(None, help="Por defecto, la última ejecución de la fecha de la pieza"),
                quiet: bool = typer.Option(False, "--quiet", help="Solo la etapa en curso (lo usa la web)")):
    """Escribe una propuesta pendiente de la mesa del día («Proceder» en la web): textos, guion,
    hechos, arte, PNG y vídeos. Guarda la pieza como versión nueva en la base de datos."""
    _logging(quiet)
    from folio.almacen import Almacen
    from folio.etapas import EtapasGuardadas
    from folio.pipeline import Pipeline, progreso
    from folio.render import renderizar, renderizar_video

    cfg = config.cargar()
    fecha = pieza[:10]
    almacen = Almacen(cfg.ruta_db)
    eid = ejecucion or almacen.ultima_ejecucion(fecha)
    r = almacen.pieza(eid, pieza) if eid else None
    if not r:
        typer.echo(f"No encuentro la pieza {pieza} en la ejecución {eid}", err=True)
        raise typer.Exit(1)
    p, _ = r
    if p.estado not in ("pendiente", "fallida") or p.guion:
        typer.echo(f"La pieza está «{p.estado}» y ya tiene guion: no hay nada que desarrollar", err=True)
        raise typer.Exit(1)
    if not p.libros and p.eleccion.formato not in ("curiosidad", "radar"):
        typer.echo("La propuesta no tiene ningún libro verificado", err=True)
        raise typer.Exit(1)
    al_jefe, _, _ = EtapasGuardadas(cfg.dir_cache(fecha)).historias()
    otras = [x for x, _ in almacen.piezas(eid) if x.id != pieza]
    tuberia = Pipeline(cfg, fecha)
    tuberia.embedder.liberar = True        # puede haber otros «Proceder» a la vez (2/11): el modelo, solo mientras se usa
    progreso(f"Desarrollando {pieza}")
    hecha = tuberia.desarrollar(p, al_jefe, otras)
    destino = cfg.dir_informes / fecha / "render"
    if hecha.estado == "propuesta":
        progreso("Pintando las diapositivas")
        renderizar(cfg, [hecha], destino)
        tuberia.historial.anadir_libros(fecha, [(l.titulo_propuesto, l.autores[0] if l.autores else "", l.olid) for l in hecha.libros])
        from folio import cajon
        if cajon.es_del_cajon(hecha.historia_id):
            tuberia.historial.anadir_curiosidad(fecha, hecha.historia_id.removeprefix(cajon.PREFIJO))
    coste = round(sum(t.coste_usd for t in tuberia.llm.trazas), 4)
    v = almacen.guardar_version(eid, pieza, hecha, "pipeline", f"Desarrollada desde la mesa ({coste} $)")
    if hecha.estado == "propuesta":
        from folio.render import marcar_render
        marcar_render(destino / pieza, eid, v)
    almacen.cambiar_estado(eid, pieza, hecha.estado)
    if hecha.estado != "propuesta":
        typer.echo(f"No se pudo escribir: {hecha.error}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{pieza}: versión {v}, {coste} $")
    # La pieza ya está en la mesa con sus PNG (2/11, a petición del usuario: que «Proceder» la enseñe antes); los
    # vídeos, después: la web recarga al ver esta etapa y los enseña cuando estén (render.json ya es de esta versión)
    progreso(f"{PIEZA_LISTA} · pintando los vídeos")
    renderizar_video(cfg, [hecha], destino)


retrato_app = typer.Typer(help="Retratos de autor generados con IA a partir de su foto libre (Magnific)")
app.add_typer(retrato_app, name="retrato")


@retrato_app.command("generar")
def retrato_generar(pieza: str, estilo: str = typer.Option(..., help="low_poly, voxel, dithering o render_2000"),
                    fecha: str = typer.Option(None, help="Por defecto, la de la pieza")):
    """Pasa el retrato fijado de la pieza a un estilo de la casa (aunque arte.retrato_generado esté
    desactivado) y actualiza el crédito en piezas.json. Parte siempre de la foto original."""
    from folio.arte import AVISO_RETRATO_GENERADO
    from folio.etapas import EtapasGuardadas
    from folio.imagenes import retrato_generado

    cfg = config.cargar()
    fecha = fecha or pieza[:10]
    try:
        img = retrato_generado.aplicar(cfg, pieza, cfg.dir_cache(fecha), estilo)
    except (ValueError, retrato_generado.ErrorMagnific) as e:
        typer.echo(f"No se pudo: {e}", err=True)
        raise typer.Exit(1)
    etapas = EtapasGuardadas(cfg.dir_cache(fecha))
    if (etapas.directorio / "piezas.json").exists():
        piezas = etapas.piezas()
        for p in piezas:
            if p.id == pieza and p.arte:
                p.arte.retrato = img.credito
                if AVISO_RETRATO_GENERADO not in p.revision_humana:
                    p.revision_humana.append(AVISO_RETRATO_GENERADO)
        etapas.guardar_piezas(piezas)
    origen = "caché" if img.generado["desde_cache"] else f"{img.generado['segundos']} s"
    typer.echo(f"{img.local} ({origen}) · {img.credito}")


instagram_app = typer.Typer(help="Publicación en la cuenta de Instagram de Folio (docs/instagram.md)")
app.add_typer(instagram_app, name="instagram")


def _instagram(cfg):
    from folio.publicacion.instagram import ErrorInstagram, Instagram
    try:
        return Instagram(cfg.instagram_token, cfg.instagram_usuario)
    except ErrorInstagram as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


def _pieza_aprobada(cfg, pieza: str, fecha: str):
    """La pieza en la última ejecución del día, solo si está «aprobada» y hay URL pública y clave de enlaces."""
    from folio.almacen import Almacen
    almacen = Almacen(cfg.ruta_db)
    eid = almacen.ultima_ejecucion(fecha)
    r = almacen.pieza(eid, pieza) if eid else None
    if not r:
        typer.echo(f"No encuentro la pieza {pieza} en la última ejecución del {fecha}", err=True)
        raise typer.Exit(1)
    p, version = r
    if p.estado != "aprobada":
        typer.echo(f"La pieza está «{p.estado}»: solo se publican las aprobadas (apruébala en la web)", err=True)
        raise typer.Exit(1)
    if not (cfg.url_publica and cfg.clave_enlaces):
        typer.echo("Faltan FOLIO_URL_PUBLICA o FOLIO_CLAVE_ENLACES (docs/instagram.md)", err=True)
        raise typer.Exit(1)
    return almacen, eid, p, version


@instagram_app.command("comprobar")
def instagram_comprobar():
    """Comprueba la conexión con la cuenta (solo lectura): usuario, tipo de cuenta y publicaciones en 24 h."""
    from folio.publicacion.instagram import ErrorInstagram

    cfg = config.cargar()
    ig = _instagram(cfg)
    try:
        c = ig.cuenta()
        usadas, maximo = ig.limite()
    except ErrorInstagram as e:
        typer.echo(f"No se pudo: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Conectada: @{c.get('username')} ({c.get('account_type', 'tipo desconocido')}), id {ig.usuario}")
    typer.echo(f"Publicaciones por la API en las últimas 24 h: {usadas} de {maximo}")
    for nombre, valor in (("FOLIO_URL_PUBLICA", cfg.url_publica), ("FOLIO_CLAVE_ENLACES", cfg.clave_enlaces)):
        if not valor:
            typer.echo(f"Falta {nombre}: sin ella no se puede publicar (Instagram descarga las imágenes de ahí)")


@instagram_app.command("publicar")
def instagram_publicar(pieza: str, fecha: str = typer.Option(None, help="Por defecto, la de la pieza"),
                       confirmar: bool = typer.Option(False, "--confirmar", help="Publicar de verdad; sin él, solo prepara y comprueba"),
                       sin_video: bool = typer.Option(False, "--sin-video", help="Todas las diapositivas en imagen, sin vídeo")):
    """Publica una pieza «aprobada» (en su versión actual de la web) como carrusel en Instagram.

    Sin --confirmar no publica nada: prepara los archivos, enseña el pie y comprueba la cuenta."""
    import json as _json

    from folio.publicacion import enlaces
    from folio.publicacion.instagram import ErrorInstagram
    from folio.publicacion.preparar import preparar

    cfg = config.cargar()
    fecha = fecha or pieza[:10]
    almacen, eid, p, version = _pieza_aprobada(cfg, pieza, fecha)
    ig = _instagram(cfg)
    lista = preparar(cfg, p, con_video=not sin_video)
    for a in lista.avisos:
        typer.echo(f"Aviso: {a}")
    typer.echo(f"Pieza {pieza} (versión {version}): {len(lista.medios)} diapositivas"
               f"{', en vídeo la ' + ', '.join(str(i) for i, (t, _) in enumerate(lista.medios, 1) if t == 'video') if any(t == 'video' for t, _ in lista.medios) else ''}"
               f"; archivos en {lista.carpeta}")
    typer.echo(f"Pie ({len(lista.pie)} caracteres):\n{lista.pie}\n")
    try:
        c = ig.cuenta()
        usadas, maximo = ig.limite()
        typer.echo(f"Cuenta: @{c.get('username')} · {usadas} de {maximo} publicaciones en 24 h")
        if not confirmar:
            typer.echo("Prueba: no se ha publicado nada. Repite con --confirmar para publicar.")
            return
        medios = [(tipo, enlaces.firmar(cfg.url_publica, cfg.clave_enlaces, f"{fecha}/{pieza}/{archivo}"))
                  for tipo, archivo in lista.medios]
        publicada = ig.publicar_carrusel(medios, lista.pie)
    except ErrorInstagram as e:
        typer.echo(f"No se pudo: {e}", err=True)
        raise typer.Exit(1)
    almacen.cambiar_estado(eid, pieza, "publicada")
    (lista.carpeta / "publicada.json").write_text(_json.dumps({**publicada, "version": version}, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Publicada: {publicada.get('permalink') or publicada['id']}")


buffer_app = typer.Typer(help="Programar el carrusel de una pieza en el Instagram de Folio a través de Buffer (docs/instagram.md)")
app.add_typer(buffer_app, name="buffer")


def _buffer(cfg):
    from folio.publicacion.buffer import Buffer, ErrorBuffer
    try:
        return Buffer(cfg.buffer_clave)
    except ErrorBuffer as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


def hora_de_publicacion(texto: str, zona: str, ahora: datetime | None = None) -> datetime:
    """«2026-11-02 09:30» o «09:30» (la próxima vez que sea esa hora) en la zona de Folio."""
    from folio.publicacion import programar
    try:
        return programar.hora_de_publicacion(texto, zona, ahora)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None


@buffer_app.command("comprobar")
def buffer_comprobar():
    """Comprueba la conexión (solo lectura): organización, canales y el de Instagram que se usará."""
    from folio.publicacion.buffer import ErrorBuffer

    cfg = config.cargar()
    b = _buffer(cfg)
    try:
        for o in b.organizaciones():
            typer.echo(f"Organización: {o['name']} ({o['id']})")
            for c in b.canales(o["id"]):
                typer.echo(f"  canal {c['service']}: {c['name']} ({c['id']})")
        canal = b.canal_instagram(cfg.buffer_canal)
        typer.echo(f"Se programará en: {canal['name']} ({canal['id']})")
        typer.echo(f"Tipos de publicación que admite: {', '.join(b.valores('PostType')) or 'no se pudo leer'}")
    except ErrorBuffer as e:
        typer.echo(f"No se pudo: {e}", err=True)
        raise typer.Exit(1)
    for nombre, valor in (("FOLIO_URL_PUBLICA", cfg.url_publica), ("FOLIO_CLAVE_ENLACES", cfg.clave_enlaces)):
        if not valor:
            typer.echo(f"Falta {nombre}: sin ella no se puede programar (Buffer descarga las imágenes de ahí)")


@buffer_app.command("programar")
def buffer_programar(pieza: str,
                     a: str = typer.Option(None, "--a", help="Hora de publicación, «AAAA-MM-DD HH:MM» o «HH:MM» (hora de Madrid); sin ella, a la cola de Buffer"),
                     fecha: str = typer.Option(None, help="Por defecto, la de la pieza"),
                     confirmar: bool = typer.Option(False, "--confirmar", help="Programar de verdad; sin él, solo prepara y comprueba"),
                     borrador: bool = typer.Option(False, "--borrador", help="Con --confirmar, lo deja en los borradores de Buffer: no se publica"),
                     reemplazar: bool = typer.Option(False, "--reemplazar", help="La pieza ya estaba programada y esa publicación se ha borrado en Buffer"),
                     sin_video: bool = typer.Option(False, "--sin-video", help="Todas las diapositivas en imagen, sin vídeo")):
    """Programa en Buffer una pieza «aprobada» (en su versión actual de la web) como carrusel de Instagram.

    Sin --confirmar no programa nada: prepara los archivos, enseña el pie y comprueba el canal."""
    import os

    from folio.publicacion import programar as prog
    from folio.publicacion.buffer import ErrorBuffer

    cfg = config.cargar()
    fecha = fecha or pieza[:10]
    almacen, eid, p, version = _pieza_aprobada(cfg, pieza, fecha)
    cuando = hora_de_publicacion(a, os.getenv("FOLIO_ZONA") or "Europe/Madrid") if a else None
    try:
        r = prog.programar(cfg, p, version, fecha, cuando, borrador=borrador, reemplazar=reemplazar,
                           confirmar=confirmar, con_video=not sin_video, buffer=_buffer(cfg))
    except (prog.NoSePuede, ErrorBuffer) as e:
        typer.echo(f"No se pudo: {e}", err=True)
        raise typer.Exit(1)
    for aviso in r.avisos:
        typer.echo(f"Aviso: {aviso}")
    videos = f", en vídeo la {', '.join(map(str, r.videos))}" if r.videos else ""
    typer.echo(f"Pieza {pieza} (versión {version}): {r.diapositivas} diapositivas{videos}; archivos en {r.carpeta}")
    typer.echo(f"Pie ({len(r.pie)} caracteres):\n{r.pie}\n")
    typer.echo(f"Hora: {cuando.strftime('%d/%m/%Y %H:%M') if cuando else 'la siguiente de la cola de Buffer'}")
    typer.echo(f"Canal: {r.canal}")
    if not r.post:
        typer.echo("Prueba: no se ha programado nada. Repite con --confirmar para programarlo.")
        return
    typer.echo(f"{'Borrador guardado' if borrador else 'Programada'} en Buffer (post {r.post['id']}, "
               f"{'no se publica' if borrador else r.post.get('dueAt') or 'en cola'}). Los archivos que "
               f"descargará están en {r.carpeta}: no los borres hasta que salga.")


def _nevera_y_memoria_de_dia(cfg, quiet: bool) -> None:
    from folio import memoria, nevera
    from folio.almacen import Almacen
    from folio.llm import LLM
    hoy = date.today()
    if cfg.pipeline.seleccion.nevera_por_dia and not nevera.intentada_hoy(cfg, hoy):
        nevera.marcar_intento(cfg, hoy)          # antes de buscar: un fallo no se reintenta en cada vuelta
        try:
            nuevas, avisos = nevera.buscar(LLM(cfg), cfg)
            if not quiet:
                typer.echo(f"Nevera: {len(nuevas)} historias nuevas" + "".join(f"\n{a}" for a in avisos))
        except Exception as exc:                # noqa: BLE001
            typer.echo(f"Nevera: no se pudo ({type(exc).__name__}: {exc})")
    try:
        almacen = Almacen(cfg.ruta_db)
        toca, motivo = memoria.toca_analisis(almacen)
        if toca:
            ids, aviso, n = memoria.analizar(LLM(cfg), cfg, almacen, origen="semanal")
            if not quiet:
                typer.echo(f"Memoria: análisis semanal ({motivo}): {n} piezas, {len(ids)} patrones")
    except Exception as exc:                    # noqa: BLE001
        typer.echo(f"Memoria: no se pudo ({type(exc).__name__}: {exc})")


@app.command()
def leer(quiet: bool = typer.Option(False, "--quiet"),
         de_dia: bool = typer.Option(True, "--de-dia/--solo-rss", help="Además: embeddings, catálogo, nevera y Memoria")):
    """Lectura periódica: descarga los RSS y guarda lo nuevo con su primera lectura; de día, además, los embeddings,
    unas pocas editoriales del catálogo, la nevera del cajón (una vez al día) y, si toca, la Memoria."""
    from folio import catalogo
    from folio.ingesta import lecturas
    cfg = config.cargar()
    nuevos, total, errores = lecturas.leer(cfg)
    if not quiet:
        typer.echo(f"Lectura: {nuevos} artículos nuevos; {total} guardados; {len(errores)} feeds fallidos")
    # Los embeddings de los artículos nuevos, para que la madrugada no los calcule todos (2/11)
    if de_dia and cfg.pipeline.ingesta.embeddings_de_dia:
        try:
            calculados, en_cache = lecturas.embeber(cfg)
            if not quiet:
                typer.echo(f"Embeddings: {calculados} nuevos; {en_cache} en la caché")
        except Exception as exc:                # noqa: BLE001 — la lectura periódica nunca falla por esto
            typer.echo(f"Embeddings: no se pudieron calcular ({type(exc).__name__}: {exc})")
    # La nevera del cajón (una vez al día) y, los lunes, el análisis de la Memoria: fuera de la madrugada (2/11)
    if de_dia:
        _nevera_y_memoria_de_dia(cfg, quiet)
    # Y el catálogo de las independientes, de fondo (2/11): unas pocas editoriales caducadas por vuelta, sin modelo
    if de_dia and cfg.pipeline.seleccion.reparto.get("recomendado"):
        try:
            ref, fichas, avisos = catalogo.leer_de_fondo(cfg, date.today())
        except Exception as exc:                # noqa: BLE001 — la lectura periódica nunca falla por el catálogo
            ref, fichas, avisos = 0, 0, [f"Catálogo de fondo: {type(exc).__name__}: {exc}"]
        if not quiet:
            typer.echo(f"Catálogo: {ref} editoriales refrescadas, {fichas} fichas" + "".join(f"\n{a}" for a in avisos))


cajon_app = typer.Typer(help="Cajón de historias editoriales y su nevera (historias nuevas que se buscan cada día)")
app.add_typer(cajon_app, name="cajon")


@cajon_app.command("buscar")
def cajon_buscar(n: int = typer.Option(None, "--n", help="Cuántas historias nuevas (por defecto, seleccion.nevera_por_dia)")):
    """Busca en la web historias editoriales nuevas, comprueba sus fuentes y las guarda en la nevera (~0,03 $).
    Nunca falla la ejecución diaria: si no encuentra nada, lo dice y sale bien."""
    from folio import nevera
    from folio.llm import LLM, ErrorLLM
    cfg = config.cargar()
    llm = LLM(cfg)
    try:
        nuevas, avisos = nevera.buscar(llm, cfg, n)
    except ErrorLLM as e:
        typer.echo(f"Nevera: no se pudo buscar ({e})")
        return
    for a in avisos:
        typer.echo(a)
    for c in nuevas:
        typer.echo(f"+ {c.id}: {c.titular} ({len(c.fuentes)} fuentes)")
    coste = round(sum(t.coste_usd for t in llm.trazas), 4)
    typer.echo(f"Nevera: {len(nuevas)} historias nuevas guardadas en {nevera.ruta(cfg)} · {coste} $")


@cajon_app.command("lista")
def cajon_lista():
    """Las historias del cajón (repositorio y nevera) y cuándo se usó cada una."""
    from folio import cajon, nevera
    from folio.historial import Historial
    cfg = config.cargar()
    usadas = Historial(cfg.ruta_db).curiosidades_recientes("9999-12-31", 100000)
    for c in cajon.cargar(cfg.raiz, nevera.ruta(cfg)):
        marca = "usada" if c.id in usadas else ("nevera " + (c.añadida or "")) if c.origen == "busqueda" else "repositorio"
        typer.echo(f"[{marca}] {c.id}: {c.titular}")


memoria_app = typer.Typer(help="Memoria del feedback: patrones de las evaluaciones y ediciones, con propuestas de regla")
app.add_typer(memoria_app, name="memoria")


@memoria_app.command("analizar")
def memoria_analizar(dias: int = typer.Option(14, help="Días de feedback que se leen"),
                     si_toca: bool = typer.Option(False, "--si-toca", help="Solo si toca el análisis semanal (los lunes); "
                                                  "nunca sale con error: es el último paso de la diaria")):
    """Lee el feedback de los últimos días y guarda los patrones que se repiten (una llamada a Opus, ~0,03 $)."""
    from folio import memoria
    from folio.almacen import Almacen
    from folio.llm import LLM

    cfg = config.cargar()
    almacen = Almacen(cfg.ruta_db)
    if si_toca:
        toca, motivo = memoria.toca_analisis(almacen)
        if not toca:
            typer.echo(f"Memoria: no toca el análisis semanal ({motivo})")
            return
        typer.echo(f"Memoria: análisis semanal ({motivo})")
    llm = LLM(cfg)
    try:
        ids, aviso, n = memoria.analizar(llm, cfg, almacen, dias, origen="semanal" if si_toca else "manual")
    except Exception as e:                      # noqa: BLE001 — el semanal nunca hace fallar la diaria
        if not si_toca:
            raise
        typer.echo(f"Memoria: no se pudo analizar ({type(e).__name__}: {e})")
        return
    typer.echo(f"{n} piezas con feedback; {len(ids)} patrones guardados o reforzados"
               f" · {round(sum(t.coste_usd for t in llm.trazas), 4)} $")
    if aviso:
        typer.echo(aviso)


@memoria_app.command("importar")
def memoria_importar():
    """Carga en la memoria las reglas decididas en las conversaciones (config/memoria_conversacion.yaml) como
    «aplicada». La API lo hace también al arrancar."""
    from folio import memoria
    from folio.almacen import Almacen
    cfg = config.cargar()
    entradas = memoria.cargar_conversacion(cfg.raiz)
    nuevas = Almacen(cfg.ruta_db).importar_conversacion(entradas)
    typer.echo(f"Memoria: {len(entradas)} reglas de las conversaciones; {nuevas} nuevas")


@memoria_app.command("exportar")
def memoria_exportar():
    """La memoria en markdown (para pasar las propuestas aceptadas a los prompts y a CLAUDE.md)."""
    from folio import memoria
    from folio.almacen import Almacen
    typer.echo(memoria.markdown(Almacen(config.cargar().ruta_db)))


@app.command()
def ab(
    fecha: str = typer.Option(None, help="Fecha (AAAA-MM-DD). Por defecto, la última con selección guardada"),
    reutilizar_llm: bool = typer.Option(False, "--reutilizar-llm", help="Sirve de data/cache/llm/ las peticiones ya hechas"),
):
    """Prueba A/B del guion: reescribe las piezas del día con cada variante de config `ab`."""
    _logging(True)
    from folio.ab import generar
    from folio.pipeline import Pipeline

    cfg = config.cargar()
    fecha = fecha or config.ultima_fecha_con_seleccion(cfg) or date.today().isoformat()
    pipeline = Pipeline(cfg, fecha)
    from folio.modelos import Historia
    from pydantic import TypeAdapter
    historias = {h.id: h for h in TypeAdapter(list[Historia]).validate_python(
        json.loads((cfg.dir_cache(fecha) / "historias.json").read_text(encoding="utf-8"))["al_jefe"])}
    ruta_md, ruta_clave = generar(cfg, fecha, lambda hid: pipeline.textos_de_historia(historias[hid]), reutilizar=reutilizar_llm)
    typer.echo(f"Para evaluar (a ciegas): {ruta_md}\nClave y métricas (abrir después): {ruta_clave}")


@app.command("ab-resultados")
def ab_resultados():
    """Agrega las pruebas A/B evaluadas y compara cada variante con el control."""
    from folio.ab import resultados
    typer.echo(resultados(config.cargar()))


@app.command()
def web(
    puerto: int = typer.Option(8000, envvar="PORT", help="Puerto de la API (o la variable PORT)"),
    host: str = typer.Option("127.0.0.1", help="Dirección; en Railway, «::» para la red privada (IPv6)"),
    recargar: bool = typer.Option(False, "--recargar", help="Recarga al cambiar el código (desarrollo)"),
):
    """API de la web (Fase 3) en http://<host>:<puerto>. La web: cd web && npm run dev."""
    import uvicorn

    uvicorn.run("folio_api.main:app_desde_entorno", factory=True, host=host, port=puerto, reload=recargar)


@app.command()
def importar():
    """Importa a la base de datos de la web los informes de informes/<fecha>/ (idempotente)."""
    from folio.almacen import Almacen

    cfg = config.cargar()
    ids = Almacen(cfg.ruta_db).importar_informes(cfg.dir_informes)
    typer.echo(f"{len(ids)} ejecuciones en la base de datos")


@app.command()
def libro(titulo: str, autor: str):
    """Verifica un libro contra Open Library / Google Books y muestra la ficha."""
    _logging(False)
    from folio.libros.verificacion import NoVerificado, Verificador
    from folio.modelos import LibroCandidato

    try:
        l = Verificador(config.cargar()).verificar(LibroCandidato(titulo=titulo, autor=autor))
    except NoVerificado as exc:
        typer.echo(f"NO VERIFICADO: {exc.motivo}")
        raise typer.Exit(1)
    typer.echo(json.dumps(l.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
