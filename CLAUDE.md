# Folio Lateral

Sistema que genera cada día piezas de Instagram para **Folio**, un medio sobre libros e ideas. Lee la actualidad a través de los libros: toma las historias del día más conversacionales y propone, para cada una, un libro que permita una lectura lateral. El resultado es un microensayo en carrusel firmado por Folio.

Repositorio: `antonioj-byte/Books4News`. Idioma de trabajo, del código y de las piezas: español.

## Flujo

1. **Ingesta** (cada madrugada): RSS de grandes medios de cualquier sección → normalización → resumen y clasificación con un modelo barato → embeddings → agrupación por evento. Relevancia = número de medios distintos que cubren la historia.
2. **Selección**: el agente «jefe de cultura» (`prompts/jefe_cultura.md`) elige 3 historias + 2 de reserva, las más conversacionales y con más potencial de lectura lateral, y propone libros candidatos (título, título original, idioma original y autor).
3. **Verificación de libros**: cada libro se comprueba contra APIs bibliográficas reales (Open Library, Google Books) antes de usarlo. La ficha indica si hay edición española o no.
4. **Guion**: el agente «guionista» (`prompts/guionista.md`) escribe un microensayo de 5 diapositivas por defecto (hasta 7, justificando las extra) en JSON estructurado: portada con la noticia → actualidad → libro → idea nueva → cierre protagonizado por el libro. Firma: Folio.
5. **Comprobación de hechos**: un modelo barato (`prompts/comprobador_hechos.md`) coteja cada cifra, fecha, nombre y hecho de la noticia en el guion con los textos fuente. Lo que no se sostiene se marca en el informe como «hecho no verificado».
6. **Dirección de arte**: el agente «director de arte» (`prompts/director_arte.md` y `director_arte_eleccion.md`, Haiku) decide tono, foto o grabado, búsquedas y cifra destacada; el código busca imágenes libres de uso, el modelo elige una viendo una hoja de contactos y el código la fija junto con las cubiertas de los libros.
7. **Render** (Fase 2): plantillas HTML con el design system de Folio → PNG de 1080×1350.
8. **Web** (Fase 3): panel con las piezas del día y su estado (`propuesta`, `en_edicion`, `aprobada`, `publicada`), previsualización del carrusel y chat de edición.

## Fases

- **Fase 1 (en evaluación)**: pipeline en texto, de la ingesta al guion verificado. Un comando, salida en un informe diario (JSON + markdown). Se evalúa la calidad una o dos semanas, con la prueba A/B del guionista en esos mismos días.
- **Fase 2 (hecha)**: render con el design system «Revista», imágenes libres y cubiertas.
- **Fase 3 (en curso, versión mínima)**: web para evaluar (carrusel + puntuación, comparación A/B ciega), con SQLite. Desde el 30/10 se despliega en Railway para la evaluación (ver «Despliegue»), protegida con contraseña y sin publicación. Base de datos definitiva, autenticación de verdad y chat de edición se deciden después de la evaluación.
- **Fase 4**: publicación programada y métricas.

No adelantar trabajo de fases posteriores salvo que se pida. Sí dejar el esquema de datos preparado para ellas (estados de la pieza, ids estables).

## Decisiones tomadas

- **Modelos**: `claude-opus-5-5` para selección, guion y chat de edición. `claude-haiku-5-5` para resumir y clasificar en la ingesta y para la comprobación de hechos. Los ids de modelo se leen de la configuración, nunca se escriben a fuego en el código. **El guionista sigue en Opus 5.5** salvo que una prueba A/B con las mismas historias demuestre que otro modelo escribe igual de bien: la calidad del texto no se negocia.
- **Libros sin edición española**: se aceptan. La ficha lo indica (`edicion_es: si/no/desconocido`).
- **Relevancia**: la señal principal es el número de medios distintos que cubren el evento, no el número de artículos.
- **Salida estructurada**: los agentes devuelven JSON validado contra un esquema (structured outputs del SDK). Si no valida, la pieza se marca como fallida, no se arregla a mano en el código. Única excepción, mecánica y anotada en los avisos de la pieza: la numeración de las diapositivas y la firma de Folio que falte al final del cierre se corrigen en código, sin volver a llamar al modelo. Cada intento rechazado deja en los avisos las reglas que incumplió.
- **Coste**: caché de prompts en la parte fija de cada prompt (instrucciones y esquema de salida), que comparten los guiones, las comprobaciones de hechos y los resúmenes. El informe separa en cada llamada la entrada no cacheada, la escritura y la lectura de caché. Los textos de cada historia se congelan en `data/cache/<fecha>/textos/` la primera vez que se descargan: relanzar el mismo día usa los mismos (para descargarlos de nuevo, borrar el archivo). El guionista sigue en Opus 5.5 `high` mientras no haya una prueba A/B.
- **Citas literales** (revisado el 31/10): como mucho una por guion, del libro, en español, de 4 a 30 palabras, y solo si aparece letra por letra (salvo mayúsculas, tildes y signos) en el texto de un libro del mismo autor según la búsqueda de texto completo de Google Books (`folio.libros.citas`). Google Books solo indexa el texto de una parte de los libros, sobre todo los de dominio público: de los modernos suele devolver la sinopsis, y sus citas no se pueden verificar, así que se rechazan y el guionista parafrasea en el reintento. El código rechaza cualquier otro texto entre comillas. Cada cita verificada se guarda en la pieza con el volumen y el fragmento. Siguiente paso posible: las primeras páginas que publican las editoriales.
- **Informes diarios**: solo en local (`informes/`, fuera de git). En la Fase 3 pasarán a la base de datos de la web.
- **Ejecución**: en la Fase 1, manual con `uv run folio run`, sin cron, o con el botón «Lanzar ejecución del día» de la web (`POST /api/ejecuciones/lanzar`, un `folio run` en un proceso aparte, uno a la vez). Se evalúa la calidad una o dos semanas antes de automatizar; el cron de la Fase 4 llamará a ese mismo endpoint.
- **Despliegue (decidido el 30/10, adelantado para la evaluación)**: Railway, dos servicios. «api» (`api/Dockerfile`, contexto la raíz): API + pipeline + Chromium, volumen en `/datos` (`FOLIO_DATOS`: base de datos, cachés, modelo de embeddings e informes), sin dominio público, escucha en `::` para la red privada. «web» (`web/Dockerfile`, contexto `web/`): Next standalone, único servicio público, reenvía `/api` y `/diseno` a la API por la red privada (`FOLIO_API`, fijado en el build). Contraseña compartida `FOLIO_CLAVE_WEB` (autenticación básica en `web/proxy.ts`; sin la variable, en local, no se pide). Pipeline y API en el mismo servicio porque Railway no comparte volúmenes. Los embeddings siguen en local (e5, 2,2 GB en el volumen, ~4 GB de RAM); Voyage se valora después de la evaluación porque obligaría a recalibrar los umbrales. Pasos en `docs/despliegue-railway.md`.
- **Embeddings**: `intfloat/multilingual-e5-large` en local (fastembed). **Al desplegar, valorar Voyage AI** por el peso del modelo (2,2 GB en disco y unos 2 minutos de CPU por ejecución).
- **Textos para el guionista**: entre 3 y 5 artículos del grupo, uno por medio, elegidos por similitud con el centro del grupo y con el hecho principal («de qué se habla», según el jefe), con un pequeño extra para el acceso abierto (`seleccion_textos` en `config/pipeline.yaml`). En los grupos grandes, el primero de cada medio traía artículos laterales y provocaba falsos «hechos no verificados». De los medios con muro solo se usa titular y entradilla.
- **Render (Fase 2)**: el aspecto vive en `diseno/tokens.yaml` (colores, fuentes, tamaños, márgenes, rótulos, logotipo), que se convierte en variables CSS, y en las plantillas de `diseno/plantillas/`, que solo usan esas variables: un test lo comprueba. PNG de 1080×1350 con Playwright; las mismas plantillas sirven para la vista previa de la web (las imágenes y cubiertas se sirven en `/api/medios/`). En la imagen firma el logotipo: la firma «Folio» del texto del cierre no se repite.
- **Design system «Wired × Alighieria» (31/10)**: cruce del Instagram de Wired con el brandbook v2 de Alighieria (las propuestas anteriores, «Wired» puro, «Revista» humanista, «Suplemento», «Lomo» y el provisional, siguen en `diseno/propuestas/` y se renderizan con `folio render --direccion`). De Wired: foto a sangre en blanco y negro con grano, titular grande y apretado, antetítulo de tema, composiciones de portada y predominio del oscuro. De Alighieria: papel `#F6F3EE`, tinta `#1C1618`/`#120E0F` (nunca negro puro), pluma `#D40549` y marcador `#FFF500`; Alexandria 700 (−0,05em) con un remate en EB Garamond cursiva; Open Sans para el texto; el antetítulo en píldora; el amarillo solo como subrayado de marcador (en el remate sobre foto y en la cifra), nunca como fondo de bloque; borde de papel rasgado entre claro y oscuro; tarjetas de papel rosado en el cierre; muro de vocabulario del oficio en la portada sin imagen. En noticias graves, sin marcador. Portada en cuatro composiciones que elige el director de arte sin repetir en el día: «sangre», «banda» (con borde rasgado), «caja» (tarjeta sobre la foto) y «neon» (la foto a dos tintas, negro y el color de la pieza); sin imagen, tipográfica. **Color de la pieza** (31/10, a petición del usuario, más Wired que el brandbook): el director de arte elige un acento por pieza, pluma o marcador, alternando en el día, que tiñe la foto en «neon», llena la página de la idea, hace de bloque detrás de la cubierta y colorea el antetítulo y la cifra. Rompe dos reglas del brandbook (marcador como fondo y foto en color): se quita sacando «neon» de `arte.portadas` y anulando el acento. Las piezas graves van sin acento. El antetítulo (1–3 palabras) y el remate (el final literal del titular, 2–6 palabras) los propone el director de arte y el código los valida. Sin cabecera, logotipo, fecha, paginación ni créditos en las diapositivas: el crédito va en el pie de la publicación. La ilustración vectorial dibujada por el modelo se probó y se desactivó: parece clip-art.
- **Imágenes libres de uso** (`folio.imagenes.libres`): Europeana (y Wikimedia Commons, que limita mucho a las IP compartidas). Solo dominio público, CC0 y CC BY con crédito; nunca CC BY-SA (la imagen se recorta y vira), NC, ND, sin licencia o con restricciones. La licencia se lee de la API, nunca se supone. Lado mayor de 1000 px como mínimo; de IIIF se pide la versión de 1600 px. La imagen no ilustra el suceso, abre una asociación; con víctimas, nada de personas reconocibles ni cifra destacada. Dos piezas del mismo día no repiten imagen. `folio imagen buscar|fijar` permite elegirla a mano.
- **Cubiertas** (`folio.imagenes.cubiertas`): se usan las reales (para las editoriales es publicidad). Primero la de la edición española por su ISBN, en Google Books y Open Library; se descartan la imagen «no disponible», las genéricas y las de menos de 400 px, y entonces se dibuja una tipográfica. Caché en `data/cache/cubiertas/`.
- **Director de arte**: Haiku 5.5, dos llamadas por pieza (propuesta y elección con hoja de contactos), unos 0,002 $ por pieza. Si elige portada de ilustración (desactivada; solo en la propuesta humanista), el **ilustrador** (`prompts/ilustrador.md`, Opus 5.5, unos 0,06 $ por pieza) dibuja en SVG una metáfora visual con la paleta cerrada; el SVG se reconstruye con una lista cerrada de elementos y atributos (`folio.imagenes.ilustracion.sanear`: sin texto, imágenes, estilos, scripts ni enlaces) y, si no es válido tras un reintento, la portada pasa al círculo. La cifra destacada tiene que estar literalmente en la diapositiva de actualidad y su rótulo no puede añadir palabras: el código lo comprueba. Sin imagen válida, la pieza sale sin foto; la etapa nunca la para.
- **Prueba A/B del guionista**: `folio ab` reescribe las piezas del día con las variantes de `ab` en `config/pipeline.yaml` (mismos libros, mismos textos congelados; el control es el guion de producción). `ab.md` es ciego y `ab_clave.json` no se abre hasta evaluar. Regla: una variante sustituye al control solo si no se publicarían menos piezas y la media de idea y voz no baja más de 0,25 puntos (`folio ab-resultados`).
- **Ejecuciones de prueba**: `--dev` (modelo barato en todo, informe en `informes/<fecha>-dev/`) y `--solo-pieza N` no registran el día en el historial ni sobrescriben las etapas guardadas. `--reutilizar-llm` sirve de `data/cache/llm/` las peticiones idénticas sin coste.
- **Selección**: el jefe de cultura recibe las 20–25 primeras historias por número de medios.
- **Edición española**: tres valores, `si` / `no` / `desconocido`. Solo se afirma `no` cuando Open Library y Google Books se han consultado sin errores, las dos encuentran la obra y ninguna tiene la edición española (el silencio de Google Books no prueba nada: sus búsquedas fallan de forma errática).
- **Agencias**: Reuters, AP y EFE no tienen RSS público; se usan Europa Press, BBC, DW, Al Jazeera y France 24.
- **Enfoque de las piezas** (se publican en una sección de libros; revisado el 31/10): desde la portada se sabe que la pieza va de un libro. La portada tiene titular (máximo 12 palabras; la noticia, su tensión o el gancho del libro) y subtítulo (10–22 palabras) que trae el libro o a su autor: qué vio, explicó o anticipó («Perrow lo explicó en 1984…»); «lo predijo» solo si es verdad del libro, y sin citas literales. La validación exige el libro o el autor en el titular o el subtítulo. Hay como mucho una diapositiva de actualidad; el libro tiene su diapositiva en la 2 o la 3 y protagoniza el cierre, que es una recomendación de verdad (título, autor, por qué leerlo ahora y ficha española si está verificada). El pie puede empezar por la noticia, pero nombra el libro. Títulos en cursiva y, si hay edición española, con el título español. Entre 25 y 30 palabras por diapositiva.
- **Línea editorial** (31/10): humanista, tecnooptimista, progresista y favorable a la iniciativa privada. Está en `prompts/jefe_cultura.md` y `prompts/guionista.md`: orienta qué se elige y el ángulo, nunca los hechos; sin partidismo ni ataques a personas o partidos, reconociendo el buen argumento contrario.
- **Selección: temas rompehielos** (31/10): el jefe de cultura prioriza las noticias de las que apetece hablar y opinar (sorpresa, curiosidad, vida diaria, dilemas) y propone para cada una el gancho del libro en una línea, que el guionista usa en la portada. Las noticias dolorosas (sucesos con víctimas, catástrofes, atentados) no están vetadas, pero no son la primera opción: nunca en caliente (menos de 3 días desde la primera publicación, que el jefe recibe en la lista), solo cuando la conversación ya va del dolor al debate, y como mucho una al día. Pendiente: que el código marque los días que una historia lleva en la agenda (la ingesta solo lee el RSS del día, así que la fecha más antigua del grupo no siempre es la del suceso).
- **Carril editorial** (31/10): Folio lee también los medios del mundo del libro de publishing-monitor (`config/fuentes_editoriales.yaml`, 121 feeds RSS importados de su `medios.csv` con `folio fuentes-editoriales`; ventana de 72 horas). Se agrupan aparte, con un umbral más estricto (0,88) y sin fusión, y entran aunque los cubra un solo medio. Se resumen las 24 primeras (por medios, medios tier 1 y fecha) y pasan al jefe de cultura las 12 primeras que tratan de libros (el resumen marca `sobre_libros`: los medios generalistas de cultura también publican cine, música o política), en una lista separada: son contexto para enmarcar el día y dar libros y autores; puede elegir una si es buena, sin obligación.
- **Caras** (31/10): el retrato del autor del libro principal va en la portada y, en círculo, junto a la cubierta. Se busca en Wikidata (SPARQL, P18) y la licencia se comprueba en Commons como el resto de imágenes (`folio.imagenes.retratos`). Casi todos los retratos de Commons son CC BY-SA: se aceptan (decidido el 31/10, `arte.retratos_cc_by_sa: true`) y la portada se publica con esa licencia, con el crédito en el pie. Sin retrato: ilustración tipo The New Yorker con un proveedor de imágenes (decidido probarlo; pendiente de elegir proveedor y clave).
- **Retratos generados** (31/10): el retrato libre del autor puede pasarse a uno de los cuatro estilos de la casa, low-poly, vóxel, dithering de 1 bit o render de videojuego de los 2000 (`folio.imagenes.retrato_generado`, Magnific Seedream 4.5 Edit; prueba de diez estilos en `docs/estilo-retratos.md`). Siempre se parte de la foto con la licencia comprobada, nunca de cero; el resultado hereda autor y licencia como obra derivada, con «generado con IA (Magnific)» en el crédito del pie, y la pieza pasa a revisión humana para comprobar el parecido. El original queda en `<pieza>-retrato-original.*`. Los estilos se alternan en el día (`arte.retrato_generado`, desactivado por defecto; `max_por_dia`), los prompts están en `prompts/retrato_generado.md` y el dithering se fuerza a 1 bit en código. Si falla, la pieza se queda con la foto; con 401/403/429 se desactiva el resto de la ejecución y con 503 se reintenta una vez. Caché por foto, estilo y prompt en `data/cache/retratos_generados/`. Con `--dev` no se genera. Clave en `MAGNIFIC_API_KEY`. El coste por imagen no lo da la API: hay que mirarlo en el panel de Magnific.
- **Investigaciones y procesos judiciales abiertos**: ni el jefe de cultura ni el guionista atribuyen culpas ni anticipan conclusiones.
- **Libros por pieza** (31/10, a petición del usuario): uno o tres, **nunca dos**. Lo normal es uno; tres solo si hay tres verificados y los tres aportan. Está en `prompts/guionista.md` y `prompts/jefe_cultura.md`, y la regla `_uno_o_tres_libros` de `guion.REGLAS` rechaza el guion con dos.
- **Libros**: el jefe propone al menos uno con edición española (salvo que no haya buena opción) y libros que merezcan recomendarse por sí mismos, no como pretexto.
- **Traducción**: solo se dice algo sobre la traducción si la edición española es `no` verificado («todavía sin traducir»), y aun así la pieza va siempre a revisión humana. Si es `desconocido`, no se dice nada.
- **Datos de edición**: la ficha usa siempre los verificados. Si el guionista dio otra editorial, traductor o año, la pieza se marca «revisar edición» y el informe muestra los dos valores: no se sobrescribe en silencio. La primera edición es la más antigua en la lengua original (el idioma lo propone el jefe y solo sirve de filtro); si Open Library devuelve la ficha de una traducción, se busca la obra original. Open Library pone a los traductores como coautores: se separan.
- **Agrupación**: umbral 0,84 (coseno medio) y una segunda pasada que fusiona grupos con centroides por encima de 0,94 (`umbral_fusion`). Con 0,88 todo el día acaba en un grupo.
- **Número de medios**: no se refuerza su peso en el prompt del jefe de cultura por ahora; se observa con más días.
- **Evaluación humana**: cada pieza del informe acaba con una plantilla para puntuar del 1 al 5 selección, libro, idea nueva y voz, decir si se publicaría y comentar. Si se relanza el mismo día con evaluaciones rellenadas, el informe anterior se guarda como `informe.evaluado-HHMMSS.md`.
- **Web (Fase 3, versión mínima)**: herramienta local de evaluación y edición, sin autenticación, despliegue ni publicación (plan en `docs/plan-fase-3.md`). `api/` (FastAPI, paquete `folio_api` del workspace de uv) sobre `src/folio/almacen.py` y `web/` (Next.js 16 + TypeScript + Tailwind 4, tipos generados desde el OpenAPI). La base de datos es `data/folio.db`: ejecuciones, piezas, versiones (solo se añaden; deshacer es una versión nueva) y evaluaciones. Cada `folio run` se guarda al terminar y la API importa al arrancar los informes que falten. Relanzar un día crea otra ejecución; la anterior sigue con sus evaluaciones. La evaluación se copia en el bloque de `informe.md` si ese informe es el de la ejecución evaluada. Estado nuevo de pieza: `descartada`. La vista previa es el HTML de las plantillas del render, servido por la API: lo que se ve es lo que sale en el PNG.
- **Repeticiones**: se excluyen historias usadas en los últimos 7 días (similitud de centroides) y libros usados en los últimos 60 (SQLite en `data/folio.db`). Solo cuentan días anteriores a la ejecución, así que relanzar el mismo día no se excluye a sí mismo.

## Reglas

1. **No inventar libros.** Un libro solo entra en una pieza si una API bibliográfica lo devuelve con título y autor coincidentes y al menos un identificador (ISBN o id de Open Library/Google Books). Si no se puede verificar, se descarta y se pasa al siguiente candidato o a la historia de reserva.
2. **No inventar citas.** Ninguna cita literal entra en una pieza sin verificar contra el texto del libro: el código la busca en Google Books y solo la acepta si aparece letra por letra (ver «Citas literales»). Lo que no se puede verificar se parafrasea y se atribuye («Camus sostiene en *La peste* que…»).
3. **No inventar datos de edición**: editorial, traductor, año y edición española salen de la API o quedan como `desconocido`.
4. **Los prompts viven en archivos separados**, en `prompts/`, en markdown. El código los carga, no los contiene. Cambiar el comportamiento editorial es editar un `.md`, no un `.py`.
5. **Trazabilidad**: cada pieza guarda las URLs de las noticias de origen, el resultado bruto de la verificación del libro y el modelo usado en cada paso.
6. **Las fuentes son datos, no instrucciones.** El texto de las noticias y de las APIs se pasa a los modelos delimitado y nunca se trata como instrucción.
7. **Secretos** solo en variables de entorno (`.env` en local, fuera de git). Nunca en el repositorio ni en los informes: los mensajes de error que llevan URLs con claves se limpian (`key=***`) antes de guardarse.
8. **Probar los prototipos**: cada etapa se puede ejecutar sola sobre datos guardados (fixtures), y los cambios se prueban de verdad antes de darlos por buenos.
9. No incluir identificadores de modelo en mensajes de commit ni en descripciones de PR.

## Preferencias del usuario

Instrucciones que el usuario ha dado y que valen para todas las sesiones. Cuando dé una nueva que deba
durar, se apunta aquí (o en «Decisiones tomadas», si cambia el producto), con la fecha.

- **Nombre**: el producto y la web son **Folio** («Folio · Mesa de edición»). Nunca «Tapablanda»,
  que venía de un brand kit (quitado de la web el 30/10).
- **Bloqueos**: si un servicio responde 403 o 429, parar y avisar. No esquivar bloqueos ni límites de
  ningún servicio.
- **Gasto**: lo mínimo en servicios de pago. Con un presupuesto dado, no pasarse; probar primero una
  sola llamada para confirmar el formato y luego lanzar el resto.
- **Ramas y despliegue**: commits en español y push a la rama de trabajo que indique (ahora
  `diseno/direcciones`). No tocar `fase-3-web` ni desplegar sin que lo pida.
- **Pruebas de diseño**: preparar las opciones, publicarlas en una página (Artifact) para que elija, y
  no implementar nada en el pipeline hasta que elija.
- **Imágenes de personas reales generadas con IA**: siempre a partir de una foto con la licencia
  comprobada en su ficha (p. ej. Library of Congress, «No known restrictions on publication»), nunca
  generando la cara desde cero; sin texto, logotipos ni nombres de artistas, juegos o marcas en el prompt.

## Cómo se trabaja

```bash
uv sync                                  # dependencias
cp .env.example .env                     # y rellenar las claves (ANTHROPIC_API_KEY o, si el entorno
                                         # no la deja pasar, FOLIO_ANTHROPIC_API_KEY)
uv run folio run                         # pipeline completo del día
uv run folio run --sin-llm               # solo ingesta y agrupación (gratis)
uv run folio run --desde seleccion       # reutiliza la ingesta guardada en data/cache/<fecha>/
uv run folio run --desde guion           # reutiliza también la selección
uv run folio run --desde hechos          # repite la comprobación de hechos y la dirección de arte
uv run folio run --desde arte            # solo repite la dirección de arte (imágenes, cifra, cubiertas)
uv run folio run --dev                   # depurar: modelo barato, sin tocar historial ni etapas (~0,02 $)
uv run folio run --solo-pieza 2          # regenera una sola pieza, en informes/<fecha>/solo-pieza-2/
uv run folio run --reutilizar-llm        # peticiones idénticas desde la caché local (0 $)
uv run folio render                      # PNG 1080×1350 en informes/<fecha>/render/
uv run folio render --direccion todas    # las propuestas de diseno/propuestas/, en render/<propuesta>/
uv run folio imagen buscar "printing press"           # imágenes libres, con la licencia comprobada
uv run folio imagen fijar 2026-10-30-1 europeana:/…   # fija una a mano para la pieza
uv run folio retrato generar 2026-10-30-1 --estilo voxel   # retrato generado (low_poly, voxel, dithering, render_2000)
uv run folio ab                          # prueba A/B ciega del guion (informes/<fecha>/ab/)
uv run folio ab-resultados               # agrega las evaluaciones A/B y aplica la regla
uv run folio libro "La peste" "Albert Camus"   # verificar un libro suelto
uv run folio web --recargar              # API de la web en http://127.0.0.1:8000 (docs en /docs)
cd web && npm install && npm run dev     # web en http://localhost:3000 (con la API en marcha)
cd web && npm run tipos                  # regenera los tipos TypeScript desde el OpenAPI
uv run folio importar                    # carga en la base de datos los informes de informes/
uv run pytest                            # tests (sin red ni gasto)
```

- Código en `src/folio/`. Configuración en `config/` (`pipeline.yaml`: modelos, umbrales, límites; `fuentes.yaml`: feeds). Diseño en `diseno/` (`tokens.yaml`, `plantillas/`, `fuentes/`).
- `pipeline.yaml` se valida al cargar (`config.ConfigPipeline`): una clave nueva hay que añadirla también al modelo; una desconocida es un error.
- Etapas guardadas (artículos, historias, selección, piezas, textos congelados): `folio.etapas`. Bloques de evaluación en markdown (informe y A/B): `folio.evaluacion_md`. Emparejar un libro del guion con su ficha: solo con `guion.libro_verificado()`.
- Reglas del guion: `guion.REGLAS`, una función por regla. Su orden es el de los mensajes del prompt de reintento; `tests/fixtures/validar_mensajes.json` lo fija.
- API: una ruta por área en `api/folio_api/rutas/`; lo compartido en `dependencias.Contexto`. Web: `lib/useDatos.ts` para cargar datos de la API.
- Los prompts tienen marcadores (`[pegar lista]`, `[pegar]`, `[pegar o «propón tú»]`) que el código sustituye por los datos del día. Si se cambia un marcador en el `.md`, hay que cambiarlo en el código; la carga falla si falta.
- Los esquemas de salida de los agentes están en `src/folio/modelos.py` y deben reflejar lo que pide cada prompt.
- El plan de la Fase 1 está en `docs/plan-fase-1.md`.
