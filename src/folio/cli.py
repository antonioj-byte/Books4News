"""Línea de comandos: `folio run`, `folio libro`."""

from __future__ import annotations

import json
import logging
from datetime import date

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
    video: bool = typer.Option(False, "--video", help="También la portada en MP4 (solo las que tienen imagen)"),
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
            typer.echo(f"{len(videos)} portadas en vídeo en {destino}")


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
                       sin_video: bool = typer.Option(False, "--sin-video", help="La portada en imagen, no en vídeo")):
    """Publica una pieza «aprobada» (en su versión actual de la web) como carrusel en Instagram.

    Sin --confirmar no publica nada: prepara los archivos, enseña el pie y comprueba la cuenta."""
    import json as _json

    from folio.almacen import Almacen
    from folio.publicacion import enlaces
    from folio.publicacion.instagram import ErrorInstagram
    from folio.publicacion.preparar import preparar

    cfg = config.cargar()
    fecha = fecha or pieza[:10]
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
    ig = _instagram(cfg)
    lista = preparar(cfg, p, con_video=not sin_video)
    for a in lista.avisos:
        typer.echo(f"Aviso: {a}")
    typer.echo(f"Pieza {pieza} (versión {version}): {len(lista.medios)} diapositivas"
               f"{', portada en vídeo' if lista.medios[0][0] == 'video' else ''}; archivos en {lista.carpeta}")
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
