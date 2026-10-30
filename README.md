# Folio Lateral

Genera cada día piezas de Instagram para **Folio**: toma las historias más comentadas de la actualidad y las lee a través de un libro verificado.

Fase 1 (actual): pipeline en texto, de la ingesta al guion verificado, con salida en `informes/<fecha>/informe.{json,md}`.

```bash
uv sync
cp .env.example .env      # ANTHROPIC_API_KEY, GOOGLE_BOOKS_API_KEY, OPENLIBRARY_CONTACT
uv run folio run
```

Más detalle en [CLAUDE.md](CLAUDE.md) y [docs/plan-fase-1.md](docs/plan-fase-1.md).
