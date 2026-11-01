# Rondas de la voz del guionista

Rondas para mejorar cómo escribe el guionista de Folio (2/11, a petición del usuario). La voz de referencia es la de
la newsletter (folioeditorial.substack.com), resumida en `prompts/voz_folio.md`.

## Método

- **Banco**: las piezas de `data/cache/2026-11-02/piezas.json`, montadas con `uv run folio banco`
  (`config/banco_voz.yaml`) a partir de temas reales con el pipeline de producción: una lectura lateral, un «Tres
  libros» de perfil y un libro recomendado. Mismos libros verificados y mismos textos congelados en todas las rondas.
- **Un cambio por ronda**, como variante en `ab.variantes` de `config/pipeline.yaml` (los prompts que cambia viven en
  `prompts/ab/` y se indican en `prompts:`). Primero una pieza (`folio ab --ronda rN --pieza <id>`) para ver que el
  formato sale; después la ronda (`folio ab --ronda rN`).
- **Juez a ciegas**: `folio ab-juez informes/2026-11-02/ab-rN` (Sonnet 5.5, distinto del Opus que escribe,
  `prompts/juez_voz.md`): idea nueva y voz de 1 a 5, ¿se publicaría?, con la mejor y la peor frase copiadas del texto
  (se comprueba que estén). No ve qué variante es cada letra; la clave se abre después.
- **Regla**: la variante gana si no empeora los hechos no verificados ni las piezas publicables y sube la media de idea
  y voz al menos 0,25. Si gana, pasa a producción y sus guiones sustituyen a los del control en el banco.
- **Límites**: como mucho 4 rondas por sesión y 6 $ en total (de las trazas: escritura, hechos y juez); se para si dos
  rondas seguidas no ganan.

Nota: las variantes de la A/B se escriben sin el verificador de citas del libro (Google Books), así que no pueden
llevar una cita literal del libro; las de la crítica y la prensa sí.

## Banco

(se rellena al montarlo)
