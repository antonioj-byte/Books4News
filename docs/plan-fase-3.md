# Plan técnico · Fase 3 (web mínima, en local)

> Aprobado el 30/10/2026. Objetivo: la herramienta de evaluación de las dos semanas de prueba de la
> Fase 1. Solo local: sin autenticación, sin despliegue y sin publicación. Base de datos definitiva,
> autenticación y despliegue se deciden después de la evaluación.

## Estructura

- `src/folio/almacen.py`: base de datos de la web, en `data/folio.db` (la misma del historial). La usan
  el pipeline, que guarda cada ejecución al terminar, y la API.
- `api/` (`folio_api`, miembro del workspace de uv): FastAPI. `uv run folio web` la arranca en :8000.
- `web/`: Next.js 16 (App Router) + TypeScript + Tailwind 4. `npm run dev` en :3000; reenvía `/api` y
  `/diseno` a la API. Tipos generados desde el OpenAPI (`npm run tipos`, con la API en marcha).
- `diseno/`: tokens y plantillas. La vista previa de la web y el PNG salen del mismo HTML.

## Base de datos

| Tabla | Contenido |
|---|---|
| `ejecuciones` | Una por `folio run`: fecha, hora de generación (única), coste, informe sin las piezas |
| `piezas` | `(ejecucion_id, pieza_id)`: estado y versión actual |
| `versiones` | Copia completa de la pieza por versión; origen `pipeline`, `manual`, `chat`, `reserva` o `deshacer`. Solo se añaden |
| `evaluaciones` | Por pieza: versión evaluada, selección, libro, idea, voz (1–5), publicaría, comentario |
| `chat_mensajes` | (paso 5) Conversación del chat por pieza |

## Endpoints

Ver `/docs` de la API. Pasos 0–3: días, portada del día, detalle de pieza (con los hechos no verificados
ligados a su frase), HTML de cada diapositiva, tokens CSS, estado, evaluación y resumen de evaluaciones.

## Herramientas del chat (paso 5)

`reescribir_diapositiva`, `anadir_diapositiva`, `quitar_diapositiva`, `reescribir_guion` (tono o varias
diapositivas), `cambiar_libro` (siempre por el verificador), `sustituir_por_reserva` (pide confirmación:
escribe un guion nuevo) y `reescribir_pie`. El modelo escribe el texto en la llamada; el servidor valida
con las reglas del guion y, si no pasan, devuelve los errores para que corrija en el mismo turno. Cada
cambio válido es una versión y lanza la comprobación de hechos en segundo plano.

## Decisiones

1. Las ediciones manuales que rompen una regla del guion se guardan con el aviso visible; las del chat
   tienen que pasar las reglas.
2. Cada ejecución es independiente: relanzar un día no pisa la anterior ni sus evaluaciones.
3. La evaluación vive en la base de datos y se copia en el bloque de `informe.md` cuando ese informe es el
   de la ejecución evaluada.
4. Chat con esfuerzo `medium` (configurable).
5. La web usa los tokens del design system.

## Orden

0–1 base de datos y API · 2 portada del día y vista de pieza · 3 evaluación · 4 edición directa · 5 chat
· 6 versiones · 7 A/B ciego · 8 exportar.
