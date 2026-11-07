# Alighieria · vídeos conceptuales (beta)

Un libro entra y sale un vídeo vertical de 30–60 s construido sobre un concepto conversacional del libro. Herramienta
aparte de Folio: vive en `videos/`, tiene su propio entorno (`uv`) y no importa ni toca nada del resto del repositorio.
Diseño en `docs/videos/diseno.html`.

## Estado

- Hecho: 1 Libro (EPUB, PDF, TXT por capítulos y páginas) → 2 Conceptos (12 candidatos, pasaje literal comprobado,
  crítico independiente que deja 5, juez del gancho que lo reescribe si saca menos de 8) → 3 Guion (planos con
  reglas en código, chat, edición directa, aprobación y bloqueo).
- Siguiente: voz con tiempos (ElevenLabs), biblia de estilo e imágenes (Magnific), montaje (FFmpeg) y revisión por plano.

## Cómo se usa

```bash
cd videos
uv sync
cp .env.example .env            # y rellenar ANTHROPIC_API_KEY
uv run videos web               # asistente en http://127.0.0.1:8100
uv run videos ingesta libro.epub --titulo "…" --autor "…"
uv run videos conceptos <proyecto> [--indicaciones "más polémicos"]
uv run videos guion <proyecto> <concepto>
uv run pytest                   # tests sin red ni gasto
```

## Piezas

- `src/videos/libro.py`: ingesta y comprobación de citas literales (salvo mayúsculas, tildes y signos).
- `src/videos/conceptos.py`, `guion.py`: los pasos 2 y 3. Reglas del guion en `guion.validar`.
- `src/videos/llm.py`: Claude con salida estructurada, caché de prompts de 1 h para el libro y caché local por
  huella. Todas las llamadas que llevan el libro usan el mismo esquema (`SalidaLibroLLM`): el esquema forma parte del
  prefijo cacheado, y con uno por paso cada paso volvía a escribir la caché del libro entero.
- `prompts/*.md`: un prompt por archivo, con `<!-- version: N -->` en la primera línea; cada resultado guarda la
  versión que lo produjo.
- `src/videos/trabajos.py`: cola de trabajos en hilos con un archivo por trabajo (`data/trabajos/`).
- `data/proyectos/<id>/proyecto.json`: un JSON por vídeo con el estado de cada etapa.
- `web/`: el asistente, sin dependencias.

## Medido el 7/11 (texto de prueba de ~24.000 tokens, *El coloquio de los perros*)

Conceptos: 1 min 38 s, 0,48 $ (0,44 $ con la escritura de la caché del libro y 11.700 tokens de salida). Guion: 42 s,
0,10 $ leyendo el libro de la caché; cada turno de chat, ~0,07 $.
