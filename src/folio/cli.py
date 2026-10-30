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
        typer.echo("Falta ANTHROPIC_API_KEY (o FOLIO_ANTHROPIC_API_KEY) en .env (o usa --sin-llm para probar la ingesta).", err=True)
        raise typer.Exit(1)
    pipeline = Pipeline(cfg, fecha, llm=LLM(cfg, reutilizar=reutilizar_llm), dev=dev, solo_pieza=solo_pieza)
    inf, (ruta_json, ruta_md) = pipeline.ejecutar(desde=desde, sin_llm=sin_llm)
    buenas = sum(p.estado == "propuesta" for p in inf.piezas)
    typer.echo(f"\nPiezas propuestas: {buenas}/{len(inf.piezas)} · coste estimado {inf.coste_total_usd:.2f} $")
    typer.echo(f"Informe: {ruta_md}\nDatos:   {ruta_json}")


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
