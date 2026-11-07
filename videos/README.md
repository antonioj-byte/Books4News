# Alighieria · vídeos conceptuales (beta)

Un libro entra y sale un vídeo vertical de 30–60 s construido sobre un concepto conversacional del libro. Herramienta
aparte de Folio: vive en `videos/`, tiene su propio entorno (`uv`) y no importa ni toca nada del resto del repositorio.
Diseño en `docs/videos/diseno.html`.

## Estado

Hecho de punta a punta (8/8 pasos), con modo simulado para Magnific y ElevenLabs:
1. **Fuente**: libro (EPUB, PDF por su índice, TXT), artículo, ensayo, texto pegado o nota de voz (transcrita con
   ElevenLabs Scribe; las citas se refieren por minuto).
2. **Conceptos**: candidatos según lo que da de sí la fuente (12 en un libro, 6–8 en un artículo), pasaje literal
   comprobado, crítico independiente que deja hasta 5, juez del gancho que lo reescribe si saca menos de 8.
3. **Guion**: planos con reglas en código, chat, edición directa, aprobación y bloqueo.
4. **Estilo**: tres predefinidos (`estilos.json`) con muestras reales, o uno propio escrito por Claude.
5. **Voz**: ElevenLabs con tiempos por carácter (fuente de verdad del montaje); voz al azar estable por proyecto.
6. **Imágenes**: escena por plano (Claude), 2 variantes con Flux 2 Pro, revisor de letras falsas, clips de Kling O1
   en los planos clave (como mucho `VIDEOS_MAX_CLIPS`, 2). La consulta de Kling O1 va por `/kling-o1/{id}`.
7. **Montaje**: FFmpeg, Ken Burns, subtítulos palabra a palabra (ASS), texto en pantalla y cita con referencia en
   zonas seguras, tarjeta final, música de ElevenLabs con ducking. MP4 1080×1920 y .srt.
8. **Revisión**: rehacer la imagen, el texto en pantalla o la voz de un plano sin rehacer lo demás.

## Cómo se usa

```bash
cd videos
uv sync
cp .env.example .env            # y rellenar ANTHROPIC_API_KEY
uv run videos web               # asistente en http://127.0.0.1:8100
uv run videos ingesta libro.epub --titulo "…" --autor "…" [--tipo articulo|ensayo|texto|nota_de_voz]
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

## Medido el 7/11 con *antimarkfisher.pdf* (40 págs., ~25.000 tokens)

Conceptos: 2 min 15 s, 0,70 $. Guion: 34 s, 0,08 $ (libro de la caché). Un capítulo como artículo suelto: 1 min 26 s,
0,36 $, 4 conceptos. Imagen Flux 2 Pro: 15 s. Clip Kling O1 Standard (5 s, 720×1276, 24 fps): unos minutos; el
precio no lo da la API (mirar el panel). Montaje de 62 s en simulado: menos de 1 min.
