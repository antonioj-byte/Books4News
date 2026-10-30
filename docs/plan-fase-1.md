# Plan técnico · Fase 1

> Aprobado el 30/10/2026. Las desviaciones durante la implementación están al final, en «Cambios respecto al plan».

Objetivo: `folio run` (o `python -m folio run`) ejecuta el pipeline de la ingesta al guion verificado y deja en `informes/AAAA-MM-DD/` un `informe.json` y un `informe.md`.

## 1. Stack

| Pieza | Elección | Por qué |
|---|---|---|
| Lenguaje | Python 3.12+ | Mejor ecosistema para RSS, embeddings y clustering. La web de la Fase 3 puede ir en FastAPI sobre el mismo paquete. |
| Gestión | `uv` + `pyproject.toml` | Rápido, con lockfile. |
| LLM | SDK oficial `anthropic` | Structured outputs con `messages.parse()` y modelos Pydantic. |
| Esquemas | Pydantic v2 | Un solo esquema sirve para validar la salida de los agentes, el informe JSON y, más adelante, la API web. |
| RSS | `httpx` + `feedparser` | Descarga concurrente con timeouts; feedparser tolera RSS y Atom mal formados. |
| Embeddings | `fastembed` con `intfloat/multilingual-e5-large` (local, ONNX) | Gratis, sin otra clave y multilingüe (es/en/fr en el mismo espacio). Alternativa: Voyage AI (`voyage-3.5`) si la calidad de los grupos no basta. |
| Clustering | Agrupación aglomerativa por similitud coseno con umbral (scikit-learn) | No hace falta fijar el número de grupos. El umbral es configurable y se ajusta con datos reales. |
| Persistencia | Archivos JSON por día + SQLite (`data/folio.db`) | Los JSON son el informe legible. SQLite guarda el historial y evita repetir historias o libros en días seguidos. Sirve de base a la web. |
| CLI | `typer` | `folio run`, `folio ingest`, `folio select --from …`, etc. |
| Tests | `pytest` + fixtures grabados (RSS y respuestas de APIs) | Para probar cada etapa sin red ni gasto. |

## 2. Estructura de carpetas

```
Books4News/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example              # nombres de las claves, sin valores
├── config/
│   ├── fuentes.yaml          # feeds RSS: medio, url, idioma, peso
│   └── pipeline.yaml         # modelos, umbrales, número de historias, ventanas de tiempo
├── prompts/
│   ├── jefe_cultura.md
│   ├── guionista.md
│   └── ingesta_resumen.md    # prompt corto para el modelo barato
├── src/folio/
│   ├── cli.py
│   ├── config.py
│   ├── modelos.py            # esquemas Pydantic (ver §4)
│   ├── llm.py                # cliente Anthropic, carga de prompts, reintentos, registro de uso
│   ├── ingesta/
│   │   ├── rss.py            # descarga y normalización
│   │   ├── resumen.py        # Haiku: resumen + sección + idioma, por lotes
│   │   └── agrupacion.py     # embeddings + clustering + puntuación
│   ├── seleccion.py          # agente jefe de cultura
│   ├── libros/
│   │   ├── openlibrary.py
│   │   ├── googlebooks.py
│   │   └── verificacion.py   # coincidencia título/autor, edición española
│   ├── guion.py              # agente guionista + validación
│   └── informe.py            # JSON + markdown
├── tests/
│   └── fixtures/
├── data/                     # SQLite y caché (fuera de git)
└── informes/AAAA-MM-DD/      # salida diaria (decidir si va a git)
```

## 3. Fuentes RSS

Todas las de abajo se han comprobado hoy (30/10/2026) desde este entorno y devuelven 200 con contenido:

| Medio | Feed | Idioma |
|---|---|---|
| El País | `https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada` | es |
| El País · Internacional | `https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada` | es |
| La Vanguardia | `https://www.lavanguardia.com/rss/home.xml` | es |
| La Vanguardia · Internacional | `https://www.lavanguardia.com/rss/internacional.xml` | es |
| El Mundo | `https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml` | es |
| Europa Press (agencia) | `https://www.europapress.es/rss/rss.aspx` | es |
| The Guardian | `https://www.theguardian.com/international/rss` | en |
| The Guardian · World | `https://www.theguardian.com/world/rss` | en |
| The New York Times | `https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml` | en |
| The New York Times · World | `https://rss.nytimes.com/services/xml/rss/nyt/World.xml` | en |
| Financial Times | `https://www.ft.com/rss/home/international` | en |
| Financial Times · World | `https://www.ft.com/world?format=rss` | en |
| BBC News · World | `https://feeds.bbci.co.uk/news/world/rss.xml` | en |
| Deutsche Welle | `https://rss.dw.com/rdf/rss-en-all` | en |
| Al Jazeera | `https://www.aljazeera.com/xml/rss/all.xml` | en |
| France 24 | `https://www.france24.com/en/rss` | en |
| Le Monde · À la une | `https://www.lemonde.fr/rss/une.xml` | fr |
| Le Monde · International | `https://www.lemonde.fr/international/rss_full.xml` | fr |

**Agencias.** Reuters, AP y EFE **no tienen RSS público que funcione** (404, 403 y 500 en la prueba). Europa Press sí. BBC, DW, Al Jazeera y France 24 sirven como cobertura global. Ver la duda 2.

Al puntuar, cada **medio** cuenta una sola vez por historia, aunque aparezca en dos de sus feeds (portada e internacional).

## 4. Esquema de datos (Pydantic)

```text
Articulo
  id (hash de la url), medio, url, titulo, entradilla, publicado_en, idioma,
  resumen_es, seccion, embedding (solo en caché, no en el informe)

Historia                      # grupo de artículos sobre el mismo evento
  id, titular_es, resumen_es, secciones[], articulos[Articulo.id],
  medios[] (distintos), n_medios, puntuacion, primera_aparicion

LibroCandidato                # lo que propone el agente
  titulo, autor, por_que (lectura lateral en 1–2 frases)

LibroVerificado
  titulo, autores[], anio_primera_edicion, identificadores {isbn13[], olid, google_id},
  edicion_es: si | no | desconocido, edicion_es_detalle {editorial, isbn, anio}?,
  fuente_verificacion: openlibrary | googlebooks, url_ficha, confianza (alta | media)

Seleccion                     # salida del jefe de cultura
  elegidas[3] y reserva[2], cada una con:
    historia_id, angulo (la lectura lateral), por_que_conversa,
    libros_candidatos[1..3] (LibroCandidato, en orden de preferencia)

Diapositiva
  n, tipo (percha_actualidad | percha_libro | idea | cierre), titulo?, texto

Guion                         # salida del guionista
  pieza_id, titulo_interno, diapositivas[4..7], pie_de_foto (caption), hashtags[], firma = "Folio"

Pieza                         # unidad que verá la web en la Fase 3
  id (fecha + n), fecha, estado (propuesta | en_edicion | aprobada | publicada | fallida),
  historia (Historia), libro (LibroVerificado), guion (Guion),
  fuentes [{medio, titulo, url}], trazas [{paso, modelo, tokens_in, tokens_out, coste_estimado}],
  avisos []                   # p. ej. "sin edición española", "libro de reserva usado"

InformeDiario
  fecha, generado_en, stats {articulos, historias, medios}, top_historias[20],
  seleccion (Seleccion), piezas [Pieza], descartes [{motivo, detalle}], coste_total_estimado
```

## 5. Cómo se encadenan los agentes

```
[RSS] ─► normalizar + deduplicar por URL y titular ─► ventana de 24–36 h
   │
   ▼
[Haiku 5.5 · Batches API] resumen de 1–2 frases en español + sección   (≈500–1.500 artículos/día)
   │
   ▼
[Embeddings locales] ─► clustering ─► Historias ordenadas por n_medios (y recencia como desempate)
   │                                   se excluyen historias ya usadas en los últimos N días (SQLite)
   ▼  top 20–25 historias (solo titular + resumen + medios)
[Opus 5.5 · jefe de cultura] ─► Seleccion (3 + 2, con 1–3 libros candidatos por historia)
   │
   ▼
[Verificación, código sin LLM] por cada historia, en orden de preferencia:
   Open Library (búsqueda por título+autor ─► ediciones ─► ¿alguna en español / ISBN 978-84?)
   y Google Books como segunda fuente (langRestrict=es para la edición española)
   ─► primer candidato verificado. Si ninguno pasa: siguiente historia de reserva.
   │
   ▼
[Opus 5.5 · guionista] entrada: historia + artículos fuente + ficha verificada (solo datos de la API)
   ─► Guion validado por esquema + comprobaciones en código:
      4–7 diapositivas, el título y el autor coinciden con la ficha, sin comillas de cita literal
   │
   ▼
[Informe] informe.json + informe.md (+ registro en SQLite)
```

Detalles:

- **Llamadas, no agentes autónomos.** En la Fase 1 cada agente es una única llamada con salida estructurada. El orquestador es código Python determinista. Así es más barato, reproducible y fácil de probar. Los agentes no buscan en la web: la verificación la hace el código.
- **Opus 5.5**: thinking adaptativo (no se puede desactivar), `effort` explícito (`high` para selección y guion; por defecto sería `medium`) y `fallbacks: "default"` para cubrir rechazos del clasificador de seguridad (algunas noticias de guerra o terrorismo pueden activarlo).
- **Haiku 5.5 por lotes** (Batches API, 50 % más barato). Como el pipeline corre de madrugada, la latencia no importa. Si un lote tarda demasiado, se recurre a llamadas normales en paralelo.
- **Prompt caching** para el prompt del sistema de cada agente.
- **Reintentos**: si el guion no pasa las comprobaciones, se reintenta una vez, pasando el error al modelo. Si vuelve a fallar, la pieza queda `fallida` en el informe con el motivo.
- **Coste estimado por día**: ingesta con Haiku, céntimos. Selección más tres o cuatro guiones con Opus, del orden de 0,5–1,5 $. Se mide de verdad en las primeras ejecuciones y se registra en el informe.

## 6. Claves y cuentas

| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Haiku y Opus | Sí |
| `GOOGLE_BOOKS_API_KEY` | Segunda fuente de verificación y comprobación de la edición española | Muy recomendable: sin clave, la cuota compartida ya está agotada (429 en la prueba de hoy) |
| `OPENLIBRARY_CONTACT` | Email en el User-Agent, como pide Open Library | No es una clave, pero conviene |
| `VOYAGE_API_KEY` | Solo si se cambian los embeddings locales por Voyage | No |

Para los RSS no hace falta clave.

## 7. Entregables de la Fase 1

- `folio run [--fecha] [--sin-llm] [--desde-cache]`: ejecución completa o por etapas.
- Informe diario en JSON y markdown.
- Tests de cada etapa con fixtures y una ejecución real de punta a punta antes de dar la fase por cerrada.
- Programación diaria: se documenta (cron o GitHub Actions) pero no se activa hasta que se apruebe.

## Cambios respecto al plan

- **Resumen por historia, no por artículo.** El modelo barato resume solo las 25 historias que llegan al jefe de cultura (unas 25 llamadas cortas), en vez de cientos de artículos. Para agrupar basta con titular y entradilla; el resumen solo hace falta para lo que se va a leer.
- **Llamadas directas en lugar de la Batches API.** En ejecución manual, esperar a un lote es incómodo, y con 25 llamadas de Haiku el ahorro es de céntimos.
- **Sin prompt caching** (corregido el 30/10, ver más abajo). Con el mínimo de los modelos 4.x los prompts no llegaban; con los 5.5 (512 tokens) sí.
- **Umbral de agrupación 0,84** (coseno medio), ajustado con las noticias del 30/10/2026: con 0,82 se mezclan eventos y con 0,86 se parten. Un mismo evento puede quedar partido entre la cobertura en español y en inglés; el jefe de cultura ve ambos grupos.
- **Textos completos** extraídos con trafilatura de los medios abiertos y parciales, uno por medio y un máximo de 5 por historia.
- **Datos de edición en el guion**: el guionista devuelve `editorial_espanola`, `traductor` y `edicion_original` (lo pide su prompt), y el código los sustituye siempre por los de la ficha verificada. Desde el 30/10 la sustitución no es silenciosa: ver «revisar edición» más abajo.

### Tras la primera ejecución real (30/10/2026)

**Entorno y seguridad**
- `ANTHROPIC_API_KEY` o, si el entorno no la deja pasar, `FOLIO_ANTHROPIC_API_KEY`.
- Los errores de Google Books llevaban la URL con la clave y acababan en el informe. Ahora se limpian (`key=***`).

**Agrupación**
- Segunda pasada que fusiona grupos cuyos centroides superan 0,94 (`umbral_fusion`), sin tocar el 0,84. El 30/10, Urda estaba partida en 8 grupos; fusionada pasa a 63 artículos y 10 medios. Con 0,88, 469 de los 640 artículos acababan en un único grupo.

**Verificación de libros**
- Google Books: `country=ES` (sin él responde 403 desde IPs que no sabe geolocalizar), cuatro intentos con espera creciente ante 429/5xx y búsqueda de respaldo sin `intitle:`, que devuelve 0 resultados de forma errática.
- Open Library: los mismos reintentos, también ante cortes de conexión.
- La edición española solo es `no` si las dos fuentes encuentran la obra y ninguna tiene esa edición.
- Si el título propuesto no aparece, se prueba el título original. Si tampoco hay edición española con el título exacto, se busca por frase en Google Books, que marca el idioma y no confunde la edición española con la catalana. Así salió *El viejo rey en el exilio* para la propuesta «… en su exilio».
- Primera edición: la más antigua en la lengua original (el idioma del jefe solo filtra). Si la obra encontrada es una traducción con ficha propia, se busca la obra original; si esta no tiene ediciones fechadas en su lengua, la primera edición queda como «no consta». Se descartan los audiolibros.
- Traductores: Open Library los pone como coautores. Si solo figuran en la edición española, pasan a ser su traductor; si no, se quitan de los autores con una nota.
- Nombres en mayúsculas normalizados («JAMES REASON» → «James Reason»). Si la edición española no trae editorial y tiene ISBN, se completa en Open Library.

**Guion**
- Enfoque de sección de libros: la portada abre con la noticia o su tensión, sin el libro; como mucho una diapositiva de actualidad; el libro entra en la 2 o la 3 y protagoniza el cierre, que es una recomendación (título, autor, por qué ahora, ficha española verificada). El pie puede empezar por la noticia, pero nombra el libro.
- Extensión: 5 diapositivas por defecto; 6 o 7 con una línea de justificación por cada extra (`justificacion_extra`). Entre 25 y 30 palabras por diapositiva en el prompt; 40 de tope duro en el código.
- Títulos en cursiva y en español cuando hay edición española.
- Traducción: solo se menciona si la edición española es `no` verificado, y entonces la pieza va a revisión humana.
- Investigaciones y procesos judiciales abiertos: sin culpas ni conclusiones anticipadas (también en el prompt del jefe).
- «Revisar edición»: si el guionista y la ficha discrepan en editorial española, traductor, editorial original o año, la pieza se marca y el informe muestra los dos valores. El 30/10 cazó dos errores que estaban en Open Library, no en el modelo.

**Comprobación de hechos (etapa nueva)**
- Haiku 5.5 coteja cada cifra, fecha, nombre y hecho de la noticia en el guion con los textos fuente que recibió el guionista. Para dar un dato por verificado tiene que copiar un fragmento literal de la fuente, y el código comprueba que está; si no, cuenta como no verificado. Lo no verificado sale en el informe como «hecho no verificado». Si la etapa falla, la pieza no se marca como fallida: queda un aviso.

**Jefe de cultura**
- Da título original e idioma de cada libro, propone al menos uno con edición española y elige libros que merezcan recomendarse por sí mismos. El peso del número de medios no se ha tocado: se observa con más días.

**Informe**
- Cada pieza acaba con una plantilla de evaluación humana: selección, libro, idea nueva y voz del 1 al 5, si se publicaría y un comentario. Relanzar el mismo día no borra las evaluaciones rellenadas: el informe anterior se guarda aparte.

### Coste: bloque sin riesgo para la calidad (30/10/2026)

Medición del 30/10 sobre una ejecución completa (1,02 $): guion 82,5 %, selección 15,7 %, comprobación de hechos 1,2 % y resúmenes 0,6 %. El 79–84 % de la salida del guionista es razonamiento interno, que se factura como salida: las palancas sobre la entrada ahorran poco. Un tercio de los guiones necesitó reintento (~0,12 $ por ejecución).

- **Caché de prompts**: la parte fija de cada prompt va en un bloque con `cache_control` (`llm.con_cache`). Comprobado con la API: el primer guion escribe 2.941 tokens y el siguiente los lee; en Haiku, 1.522 (hechos) y 677 (resúmenes). El coste del informe incluye escritura (1,25 × entrada) y lectura (0,20 $/M en Opus 5.5; 10 % de la entrada si no se indica).
- **Reintentos**: cada intento rechazado queda en los avisos con las reglas que incumplió, para saber cuáles provocan más. El prompt del guionista acaba con una lista de comprobación que repite las reglas de la validación. Numeración y firma de Folio se corrigen en código sin volver a llamar al modelo.
- **Textos congelados** por historia en `data/cache/<fecha>/textos/`: requisito para comparar variantes (A/B) y para que la comprobación de hechos mire lo mismo que vio el guionista.
- **Pendiente, sin riesgo, cuando haya ejecución nocturna**: API por lotes (−50 %). No admite `fallbacks`, así que los rechazos del clasificador habría que tratarlos en el código.
- **Pendiente, con prueba A/B**: Sonnet 5.5 o esfuerzo `medium` en el guion y en el jefe de cultura; reintento sin reenviar el razonamiento del primer intento.

### Selección de textos y Fase 2 (30/10/2026)

- **Textos para el guionista**: en los grupos grandes (Urda, 66 artículos), el primero de cada medio traía artículos laterales (víctimas por nacionalidad, la campaña) y el comprobador marcaba como «no verificados» hechos ciertos que el guionista había sacado del resumen del jefe. Ahora cada artículo puntúa por similitud con el centro del grupo y con «de qué se habla»; se toma uno por medio, entre 3 y 5, con un extra pequeño para el acceso abierto. Los textos congelados con la versión anterior se vuelven a elegir.
- **Render (Fase 2)**: `diseno/tokens.yaml` (design system provisional), `diseno/plantillas/` y `folio render`. Ver «Render» en `CLAUDE.md`.
- **Modo de desarrollo y A/B**: ver «Ejecuciones de prueba» y «Prueba A/B del guionista» en `CLAUDE.md`.
