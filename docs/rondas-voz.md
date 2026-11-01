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

Montado el 1/11 con `folio banco` (1,71 $, de ellos 0,14 $ de un primer intento en que el jefe se cortó por
`max_tokens`; arreglado en `temas.proponer`). Los tres guiones de producción, aceptados al segundo intento.

| Pieza | Formato | Tema real | Libros verificados |
|---|---|---|---|
| 2026-11-02-1 | lateral | Karl Bushby cruza el puente del Humber tras 28 años caminando (BBC) | *No te veré morir*, Antonio Muñoz Molina |
| 2026-11-02-2 | balda (perfil) | Houellebecq en el festival Ja! de Bilbao (El País respondió 403 y se descartó sin reintentar; noticias buscadas en la web) | *Ampliación del campo de batalla*, *Las partículas elementales*, *Sumisión* |
| 2026-11-02-3 | recomendado | Catálogo de las independientes: Impedimenta | *Los adversarios*, Michael Crummey |

## Rondas

### Ronda 1 · la voz de Folio en el guionista — GANA

**Diagnóstico** (guiones de producción del banco):
1. «Karl Bushby vuelve a casa tras 28 años caminando» (portada de la lateral): titular-resumen de la noticia, sin
   invento ni tesis.
2. «Michel Houellebecq, el novelista francés más traducido de los últimos treinta años, pasó por el festival Ja! de
   Bilbao» (actualidad del perfil): entra por el dato de agencia, no por una escena.
3. «Una novela breve, intensa y llena de vida, que te recomendamos leer esta semana» (pie de la lateral): adjetivos de
   solapa y fórmula de nota de prensa.

**Hipótesis**: el guionista de producción no recibía la voz de Folio, solo una línea de «tono de columnista». Un
cambio: sustituir esa línea por `prompts/voz_folio.md` (variante `voz`).

**Prueba**: primero la lateral sola (formato correcto, 0,42 $), después el banco entero.

| Variante | Idea | Voz | Media | Publicables | Hechos no verif. | Intentos | Coste escritura |
|---|---|---|---|---|---|---|---|
| control (producción) | 2,00 | 2,00 | 2,00 | 0/3 | 13 | — | — |
| voz | 3,00 | 3,00 | 3,00 | 0/3 | 7 | 7 | 1,18 $ |

**Antes → después** (mismas piezas):
- «Karl Bushby vuelve a casa tras 28 años caminando» → «28 años caminando para volver a un recuerdo».
- «Ganó el Dublin Literary Award 2025…» como gancho del recomendado, con el titular «En una isla helada de Canadá, el
  odio entre hermanos se hereda» → «Prohibido animar a nadie en esta guerra de hermanos».
- «No es nihilismo: es una pregunta» (idea del perfil) → «Houellebecq no escribe almas, sino posiciones, y cada lector
  busca la suya en la tabla».

**Notas del juez** (Sonnet 5.5, a ciegas): la voz gana en las tres piezas por un punto. Lo que aún falla, según el
juez: arranques de agencia que sobreviven («El francés más traducido en treinta años pasó por el festival Ja!»),
rótulos de reseña («Tesis:», «Tres novelas, un solo movimiento»), un cierre de autoayuda («Léela antes de tu próxima
discusión familiar») y ninguna pieza que publicaría tal cual.

**Coste de la ronda**: 1,70 $ (guiones 1,60; hechos 0,04; juez 0,05; incluye la prueba de una pieza).

**Decisión**: gana (+1,00 en idea y voz; hechos no verificados 13 → 7; publicables iguales). Pasa a producción:
`guionista.md` incluye `voz_folio.md` (`[incluir voz_folio]`). Los guiones de la variante son el nuevo control del
banco (el anterior queda en `informes/2026-11-02/ab-r1/piezas_control_antes.json`).

### Ronda 2 · repaso de voz antes de devolver el guion — PIERDE

**Diagnóstico** (control: los guiones ganadores de la ronda 1):
1. «El francés más traducido en treinta años pasó por el festival Ja! de Bilbao» (perfil): sigue entrando por el dato
   de agencia.
2. «Tesis: el sexo libre funciona como el mercado…» y «Tres novelas, un solo movimiento: …» (perfil): rótulos de
   reseña escolar.
3. «Léela antes de tu próxima discusión familiar» (cierre del recomendado): remate de autoayuda.

**Hipótesis**: el guionista tiene la voz, pero su repaso final solo mira reglas mecánicas. Un cambio en
`guionista.md`: un repaso de voz antes de devolver el JSON (primera frase de cada diapositiva con algo que se ve, nada
de nota de prensa, solapa ni autoayuda, sin rótulos de reseña, una frase que se recuerde). `prompts/ab/guionista_r2.md`.

**Prueba**: primero el perfil solo (formato correcto, mismos hechos no verificados que el control: 3), luego el banco.

| Variante | Idea | Voz | Media | Publicables | Hechos no verif. | Intentos | Coste escritura |
|---|---|---|---|---|---|---|---|
| control (r1) | 3,33 | 2,67 | 3,00 | 1/3 | 9 | — | — |
| repaso-voz | 3,33 | 3,33 | 3,33 | 1/3 | 17 | 9 | 1,09 $ |

El juez volvió a dar al control la misma media que en la ronda 1 (3,00): la vara es estable.

**Antes → después**:
- «El francés más traducido en treinta años pasó por el festival Ja! de Bilbao» → «Basta encender un cigarro para que
  te llamen nihilista, recordó Michel Houellebecq en el festival Ja! de Bilbao» (en la prueba de una pieza).
- «Tres novelas, un solo movimiento: el mercado ocupa lo que creíamos a salvo» → «Houellebecq lleva treinta años de
  contable del progreso: apunta quién pierde con cada libertad ganada» (perfil publicable, 4/4).
- «Karl Bushby salió andando de Punta Arenas…» → «Karl Bushby empuja su carrito por el puente del Humber, entre la
  niebla».

**Notas del juez**: la voz sube en la lateral y el perfil (escena de entrada, una figura acuñada), pero el recomendado
baja (de 4/4 a 3/3: «la diapositiva de actualidad es un desfile de citas de prensa») y la lateral inventa un cierre que
contradice la noticia («Un hombre llega andando a casa de su madre»).

**Coste de la ronda**: 1,83 $ (guiones 1,72; hechos 0,05; juez 0,06; claridad 0,01).

**Decisión**: pierde. Sube la media 0,33, pero los hechos no verificados casi se duplican (9 → 17; en el perfil, de 3
a 10). Por qué: pedir que cada diapositiva empiece por «algo que se ve» empuja a fabricar escenas que los textos no
traen. Lección para la próxima: la escena tiene que salir de los textos recibidos; si no la hay, mejor el dato bien
contado que una escena inventada.

