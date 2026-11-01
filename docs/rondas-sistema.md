# Rondas de mejora del sistema

Bucle de mejora pedido por el usuario: una mejora por ronda, rotando las áreas (a) velocidad, (b) coste,
(c) fiabilidad, (d) seguridad, (e) dirección de arte y render, (f) web. Para a las 5 rondas o cuando una ronda
no encuentra nada que valga la pena. Los cambios visibles de diseño o producto no se implementan: se preparan
las opciones en un Artifact para que el usuario elija.

| Ronda | Área | Mejora | Tipo | Probado | Coste |
|---|---|---|---|---|---|
| 1 | (a) velocidad | Hechos y arte a la vez en «Proceder» | interna, hecha | sí (test + llamada real a Haiku) | 0,0016 $ |
| 2 | (b) coste | Caché de la conversación en las correcciones del guionista y en el chat | interna, hecha | sí (tests + llamadas reales a Opus y Haiku) | ~0,08 $ |
| 3 | (c) fiabilidad | La lectura periódica y la ejecución del día ya no se pisan; `lecturas.json` atómico | interna, hecha | sí (tests + lectura real de los RSS + carrera medida) | 0 $ |

Gasto acumulado del bucle: **~0,08 $** (tope: 3 $).

---

## Ronda 1 · (a) Velocidad y paralelización

**Limitación del entorno**: en esta sesión no hay `data/` ni `informes/` (están fuera de git, en el volumen de
Railway), así que no hay líneas `TIEMPO:` ni trazas reales que leer. La revisión se hizo sobre el código y se
midió con una llamada real.

**Qué encontré**

- `Pipeline.desarrollar` (`src/folio/pipeline.py`, «Proceder» en la web) hacía, una detrás de otra:
  textos → guion → `comprobar_hechos([pieza])` → `dirigir_arte(…)`. La comprobación de hechos (Haiku) solo
  escribe `pieza.hechos`, y la dirección de arte no la lee (en `arte.py` y `imagenes/` no hay ninguna
  referencia a `pieza.hechos`; solo el docstring dice «después de la comprobación de hechos»). Eran dos
  esperas independientes en serie.
- Medido de verdad: una comprobación de hechos con Haiku sobre un guion corto de prueba (`tests/datos.py`)
  tarda **11,9 s** (traza `hechos:prueba-ronda1`, 0,0016 $). Con los 3–5 textos de una pieza real, más.
  La dirección de arte tarda bastante más (director, búsquedas de Europeana, hoja de contactos, a veces Flux
  o Magnific), así que en paralelo la comprobación queda tapada entera.
- Otros candidatos vistos y descartados para esta ronda:
  - `_cubiertas_de` en la mesa de madrugada busca las cubiertas en serie (unas 12 búsquedas). Se ganaría
    tiempo de madrugada, pero nadie lo espera (la mesa está lista a las 5:30) y toca la caché de cubiertas
    desde varios hilos: más riesgo, menos impacto.
  - `dirigir_arte` va pieza a pieza a propósito (no repetir imagen ni composición): no se toca.
  - Los textos del guion van en serie porque el modelo de embeddings no se comparte entre hilos: no se toca.

**Por qué esta**: es lo que el usuario espera con el botón delante («me tiltea lo lento que es»), el cambio
es de diez líneas y no altera ningún resultado, solo el orden en el tiempo.

**Qué se hizo** (arreglo interno)

- `desarrollar` lanza `comprobar_hechos(..., anunciar=False)` en un hilo y dirige el arte en el principal;
  espera a los dos antes de devolver la pieza (y propaga cualquier excepción inesperada como antes).
- `anunciar=False`: la comprobación no escribe líneas `ETAPA:` en «Proceder» (si no, la web enseñaría
  «Comprobando hechos (1 de 1)» mientras el arte sigue). Las etapas de la madrugada no cambian.
- Los dos hilos filtran y añaden avisos en `pieza.avisos`: ahora bajo un cerrojo (`Pipeline._avisos_pieza`)
  para que un filtrado no pise al otro.
- Los textos ya están congelados cuando se comprueba (los guardó `_textos`), así que el hilo de los hechos
  no carga el modelo de embeddings.

**Antes / después**

- Test `test_proceder_comprueba_hechos_a_la_vez_que_el_arte` (hechos y arte simulados de 0,5 s cada uno,
  los dos fallando): con el código anterior tarda **1,02 s** y falla; con el nuevo, ~0,5 s y pasa, con los
  avisos de los dos fallos en la pieza.
- En producción: «Proceder» debería tardar lo que tarde la comprobación de hechos menos (≥ 12 s por pieza).
  **No se ha medido en Railway**: hay que mirar las líneas `TIEMPO:` de `data/desarrollos/<pieza>.log` del
  próximo «Proceder» (desaparece la etapa «Comprobando hechos» y «Dirección de arte» no debería crecer).

**Cómo se probó**: `uv run pytest` (353 en verde); el test nuevo falla con el código viejo; una llamada
real a Haiku para medir la comprobación.

**Coste**: 0,0016 $.

**Pendiente**: medir el ahorro real en Railway tras el próximo merge (lo decide el usuario); valorar las
cubiertas en paralelo en la mesa si los `TIEMPO:` de madrugada lo justifican.

---

## Ronda 2 · (b) Coste

**Qué encontré**

- `llm.con_cache` (`src/folio/llm.py`) pone el único punto de caché al final de la parte fija del prompt (hasta el
  primer marcador). Todo lo que va después —en el guionista, el formato, la noticia, los 3–5 textos de hasta
  6.000 caracteres y los libros— nunca se cachea.
- El guionista es una conversación: si el guion rompe una regla o el lector sin contexto señala algo,
  `guion.escribir` (`src/folio/guion.py`, bucle `while True`) añade el guion y la corrección y vuelve a llamar a
  Opus. Cada corrección pagaba otra vez, a 4 $/M, el primer mensaje entero. El 2/11 el guionista hizo 27 llamadas
  en un día (CLAUDE.md, «Correcciones del guion con esfuerzo medio»): muchas son correcciones.
- El chat de edición (`edicion.chat`, Opus) no usaba caché en absoluto: cada turno y cada reintento reenviaban las
  instrucciones, la pieza y la conversación a precio completo.
- Duda que había que despejar: la referencia de la API dice que cambiar `effort` entre llamadas invalida la caché
  de los mensajes, y las correcciones van a `medium` tras un primer guion a `high`. **Probado de verdad con Opus
  5.5** (3 llamadas, ~0,06 $): la corrección con el esfuerzo cambiado leyó de la caché los 8.938 tokens del primer
  turno. No hace falta la beta de esfuerzo por mensaje.

**Por qué esta**: es el mayor gasto del día (Opus, entradas largas, repetidas), el cambio no toca qué se envía, solo
qué se marca para la caché, y no cambia modelos ni esfuerzos.

**Qué se hizo** (mejora interna)

- `llm.cache_al_final(mensajes, hasta=None)`: devuelve una copia de la conversación con un punto de caché al final
  del mensaje `hasta` (por defecto, el penúltimo). Como se marca una copia en cada llamada, los puntos no se acumulan
  (dos por petición como mucho; el límite es cuatro).
- Guionista: `hasta=0`, el primer mensaje. Primero lo probé con el punto móvil (el guion anterior también en la
  caché): la corrección escribía 7.199 tokens a 1,25× que solo se aprovechan si hay una tercera llamada, que es
  rara. Con el primer mensaje fijo, la corrección lee lo caro y no escribe nada.
- Chat de edición: el penúltimo mensaje de cada turno (la conversación crece turno a turno; en el primero, el
  «Entendido» que sigue a las instrucciones y la pieza).

**Antes / después** (prompt real del guionista con tres textos de 6.000 caracteres y una corrección; Haiku para
abaratar la prueba, el mecanismo de caché es el mismo)

| | entrada sin caché | escritura | lectura |
|---|---|---|---|
| Corrección, antes | 15.132 | 0 | 5.543 (solo instrucciones) |
| Corrección, después | 5.258 (el guion anterior) | 0 | 14.346 |

Pasado a precios de Opus 5.5: la entrada de cada corrección baja de ~0,061 $ a ~0,024 $ (−0,037 $). Lo que cuesta:
el primer guion escribe la noticia y los textos en la caché a 1,25× (~+0,009 $ por guion). Compensa en cuanto más de
una de cada cuatro piezas necesita una corrección, y hoy la necesitan bastantes más.

**Cómo se probó**: tests nuevos en `tests/test_llm.py` (la copia, el punto en el sitio y el original intacto; el
guionista marca su primer turno); `uv run pytest`, 358 en verde; llamadas reales a Opus (esfuerzo y caché) y a
Haiku (antes y después con el prompt del guionista).

**Coste**: ~0,06 $ (Opus, prueba del esfuerzo) + ~0,02 $ (Haiku) ≈ 0,08 $.

**Pendiente**

- Ver el efecto en el panel de gasto (etapa `guion`) después del próximo merge: la lectura de caché de los
  `guion:<pieza>:2` debería pasar de unos 5.000 a unos 14.000 tokens.
- `--reutilizar-llm` (`data/cache/llm/`): la clave incluye los mensajes, así que las respuestas guardadas antes del
  cambio para el guionista y el chat no se reutilizan una vez (se vuelven a pedir).
- Otros candidatos de coste vistos: el chat no cachea sus instrucciones fijas entre turnos cuando la pieza cambia
  (`chat_edicion.md` va sin `con_cache`, ~1.700 tokens); el jefe de los temas y la selección con «completar»
  también son conversaciones. Menos gasto, para otra ronda.
- **Aviso al cerrar la ronda 2**: tras rebasar, `tests/test_config.py::test_pipeline_yaml_tipado` falla con
  `KeyError: 'voz-estilo'`. Lo trae el commit `1942db5` («Ronda 1 de la voz», otra sesión que trabaja en la misma
  rama), que cambió las variantes de `ab` en `config/pipeline.yaml`; falla igual sin los cambios de esta ronda. No se
  ha tocado: es trabajo en curso de la otra sesión.

---

## Ronda 3 · (c) Fiabilidad

**Qué encontré**

- La lectura periódica (`folio leer`, cada 2 h, `programador.Lector`) es un proceso que el ejecutor no conoce: solo
  miraba al empezar si había una ejecución en marcha (`Lector.una_vuelta`), pero nada impedía lo contrario. Si la
  lectura empieza a las 4:44 y la diaria salta a las 4:45 (o alguien pulsa «Lanzar ejecución del día»), corren a la
  vez: la lectura descarga ~120 feeds, calcula embeddings, y algunos días lanza la nevera y la Memoria; tarda minutos.
- `lecturas.leer` reescribía `data/lecturas.json` con un `write_text` directo (`src/folio/ingesta/lecturas.py:51`), y
  `lecturas._cargar` devuelve `{}` si el JSON no se puede leer. La madrugada (`pipeline.ingesta` → `lecturas.juntar`)
  lo lee: a medio escribir, lo da por vacío **sin avisar** y pierde los artículos que ya salieron del RSS y la hora
  en que Folio vio cada uno (`visto_en`), que es lo que usa el jefe para no tratar en caliente una noticia dolorosa.
- Además, los dos procesos podían tener cargado a la vez el modelo de embeddings (2 GB cada uno).
- Medido con datos reales (1.351 artículos, 910 KB), un proceso reescribiendo y otro leyendo durante 3 s:
  **3.387 de 3.720 lecturas salían vacías** con el código anterior; **0 de 285** con la escritura atómica.
- Otros candidatos vistos: `Embedder.podar` (`agrupacion.py`) lee y reescribe la caché de embeddings fuera del
  cerrojo y puede borrar vectores recién calculados por otro proceso (solo cuesta recalcularlos: menos grave); si el
  `Popen` de un paso encadenado falla, `_Trabajo` se queda «vivo» para siempre (improbable).

**Por qué esta**: afecta a la ejecución que más importa (la de madrugada), el fallo es silencioso y toca una regla
editorial (los días en caliente); el arreglo es pequeño y no cambia nada cuando no hay choque.

**Qué se hizo** (arreglo interno)

- `Ejecutor.empezar_lectura` / `acabar_lectura`: la lectura pide turno bajo el mismo cerrojo que el pipeline; si hay
  una ejecución del día, se salta la vuelta (como antes) y, mientras lee, `Ejecutor.lanzar` no lanza el pipeline.
  «Proceder» no cambia (sigue pudiendo ir a la vez que la lectura).
- La programada ya reintentaba cada 30 s dentro de su ventana de dos horas: ahora espera a que acabe la lectura.
- `Ejecutor.motivo_ocupado`: el 409 de «Lanzar ejecución del día» dice el motivo real («Se están leyendo las noticias
  (lectura periódica); prueba en unos minutos», o que hay piezas escribiéndose); antes decía siempre «Ya hay una
  ejecución en marcha», también cuando lo que había era un «Proceder».
- `lecturas.leer` escribe en un temporal y lo renombra (atómico), como ya hacía la caché de embeddings.
- Si la lectura falla, el turno se suelta (`finally`).

**Cómo se probó**: tests nuevos en `tests/test_lecturas.py` (con el ejecutor real y procesos reales: la lectura no
arranca con una ejecución en marcha; con la lectura a medias no se lanza la diaria y el motivo es el correcto; una
lectura que falla no deja el turno cogido; la escritura no deja temporales). `uv run pytest`: 359 en verde y 1 rojo que
no es de esta ronda (ver abajo). Una lectura real de los RSS (`folio leer --solo-rss`, gratis): 1.351 artículos,
archivo íntegro. La carrera, medida antes y después con esos datos.

**Coste**: 0 $.

**Avisos**

- **403/429 en la lectura real**: dos feeds respondieron 403 o 429 desde este entorno, La Stampa Cultura y The
  Believer. El código los pausó 7 días (`data/feeds_pausados.json` de este contenedor; producción no se entera) y no
  se reintentó nada. No se han vuelto a lanzar lecturas de RSS en el bucle. Si también bloquean desde Railway, la
  pausa de allí lo dirá en los avisos de la ejecución.
- `tests/test_config.py::test_pipeline_yaml_tipado` sigue en rojo por el commit `1942db5` de la otra sesión
  (`voz-estilo`), como al cerrar la ronda 2.

**Pendiente**: no se ha probado en Railway con la API de verdad (hilo del lector y programada a la vez); lo cubren los
tests con el ejecutor real. Valorar `Embedder.podar` bajo el cerrojo en otra ronda de fiabilidad.
