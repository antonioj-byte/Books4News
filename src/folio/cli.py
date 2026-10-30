"""Línea de comandos: `folio run`, `folio libro`."""

from __future__ import annotations

import json
import logging
from datetime import date

import typer

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
    desde: str = typer.Option(None, help="Etapa desde la que ejecutar: ingesta | seleccion | guion | hechos. Por defecto, ingesta; con --dev, guion"),
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
    if desde not in ("ingesta", "seleccion", "guion", "hechos"):
        raise typer.BadParameter("--desde debe ser ingesta, seleccion, guion o hechos")
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
):
    """Render de las piezas del día a PNG (1080×1350) en informes/<fecha>/render/."""
    _logging(False)
    from folio.modelos import Pieza
    from folio.render import renderizar
    from pydantic import TypeAdapter

    cfg = config.cargar()
    fecha = fecha or config.ultima_fecha_con_seleccion(cfg) or date.today().isoformat()
    ruta = cfg.dir_informes / fecha / "informe.json"
    if not ruta.exists():
        typer.echo(f"No existe {ruta}: ejecuta antes folio run", err=True)
        raise typer.Exit(1)
    piezas = TypeAdapter(list[Pieza]).validate_python(json.loads(ruta.read_text(encoding="utf-8"))["piezas"])
    piezas = [p for p in piezas if p.guion and (pieza is None or p.id == pieza)]
    archivos, avisos = renderizar(cfg, piezas, cfg.dir_informes / fecha / "render")
    for a in avisos:
        typer.echo(f"Aviso: {a}")
    typer.echo(f"{len(archivos)} diapositivas en {cfg.dir_informes / fecha / 'render'}")


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
    ruta_md, ruta_clave = generar(cfg, fecha, lambda hid: pipeline._textos(historias[hid]), reutilizar=reutilizar_llm)
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
