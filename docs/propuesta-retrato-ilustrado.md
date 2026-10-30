# Retrato ilustrado con Magnific: prueba y propuesta

> Superada el 31/10: el estilo editorial no se adoptó. Los retratos generados usan los estilos de
> `docs/estilo-retratos.md` y se implementaron en `folio.imagenes.retrato_generado`.

Prueba del 30/10. Objetivo: convertir una foto real de un autor en un retrato ilustrado de estilo
editorial, para las piezas sin retrato libre o con más carácter. **Solo propuesta: nada integrado.**

## Prueba

- **Foto de partida**: Philip Roth por Bernard Gotfryd, Library of Congress («No known restrictions
  on publication»), `tile.loc.gov/…/gtfy/03200/03254v.jpg`, 696×1024 (la mayor publicada; la `.tif`
  da 404).
- **Envío de la foto**: en base64. Por URL falla porque tile.loc.gov responde 403 al servidor de
  Magnific; la tarea acaba en `FAILED` a los 5 s.
- **API**: los tres endpoints son asíncronos. El `POST` devuelve `task_id` y el `GET …/{task_id}` se
  consulta hasta `COMPLETED` o `FAILED`; también admiten `webhook_url`. El resultado es una URL
  firmada y temporal del CDN, que hay que descargar enseguida.

| Endpoint | Petición | Imagen de entrada | Precio documentado |
|---|---|---|---|
| Seedream 4.5 Edit, `POST /v1/ai/text-to-image/seedream-v4-5-edit` | `prompt`, `reference_images` (1–5), `aspect_ratio`, `seed` | URL o base64 | No consta en la documentación de la API |
| Flux Kontext Pro, `POST /v1/ai/text-to-image/flux-kontext-pro` | `prompt`, `input_image`, `aspect_ratio` (con `social_post_4_5`), `guidance`, `steps`, `seed`, `output_format` | URL; con *data URI* también funcionó | No consta en la documentación de la API |
| Style Transfer, `POST /v1/ai/image-style-transfer` | `image` + `reference_image` (imagen de estilo, obligatoria), `prompt`, `style_strength`, `structure_strength`, `is_portrait`… | URL o base64 | 0,10 € por operación |

Style Transfer no se probó: necesita una imagen de estilo, y no tenemos ninguna libre que no sea
copiar a un ilustrador concreto.

| Variante | Modelo | Tiempo | Resultado |
|---|---|---|---|
| v1 | Seedream 4.5 Edit, tinta y aguada, fondo papel | 27,8 s | Parecido muy fiel, 1774×2364. Sobria. |
| v2 | Flux Kontext Pro, mismo prompt | 14,4 s | Peor parecido (cara más redonda y mayor). Sale a 944×1104, por debajo de los 1080 px del lienzo, y deja una marca como de firma en la solapa. Descartada. |
| v3 | Seedream 4.5 Edit, planos de color y fondo liso | 19,3 s | Buen parecido y la que más se parece a una portada. **La mejor**: se pintó en «sangre» y «neon». |

**Coste**: la API no lo devuelve en la respuesta. La tabla de créditos de magnific.com responde 403 y
la Analytics API también («User does not belong to any team», solo planes Business o Enterprise).
Hay que mirarlo en el panel de la cuenta: 4 tareas (la fallida incluida) entre las 21:50 y las 21:54
UTC del 30/10.

## Propuesta de integración (`folio.imagenes.ilustrado`)

**Cuándo se usa.** Solo sin retrato libre, no siempre. La regla de la casa es que la licencia se lee
de la fuente y que las caras son reales. La ilustración añade un coste, una espera y un riesgo de
parecido, y en las piezas graves no aporta. Orden: retrato de Commons (como ahora) → si no hay, o si
el director de arte lo pide expresamente (`retrato: "ilustrado"` en la propuesta, desactivado por
defecto), ilustración a partir de una foto de partida libre.

**Foto de partida.** La ilustración nunca se genera sin una foto: siempre parte de una con la
licencia comprobada. Se pueden usar fotos que hoy no valen para la portada (resolución baja, de menos
de 1000 px, porque Seedream devuelve 1774×2364) y, si se decide, CC BY-SA, con la obra derivada
publicada con esa licencia. Si no hay foto, no hay ilustración y la portada pasa a tipográfica.

**Configuración** (`config/pipeline.yaml`, dentro de `arte`, añadiendo los campos al modelo de
`ConfigPipeline`):

```yaml
arte:
  retrato_ilustrado:
    activo: false                 # interruptor general
    cuando: sin_retrato           # sin_retrato | siempre
    proveedor: magnific
    endpoint: seedream-v4-5-edit  # el de la prueba; kontext como alternativa
    aspecto: traditional_3_4
    prompt: prompts/retrato_ilustrado.md   # el estilo, en un .md (regla 4)
    espera_max_s: 120
    max_por_dia: 3
    coste_max_dia_eur: 1.0
```

La clave se lee de `MAGNIFIC_API_KEY` (y va en `.env.example`, sin valor).

**Si falla.** La etapa nunca se para. Ante un `FAILED`, un tiempo agotado, un 5xx o un parecido
dudoso, la pieza sigue sin ilustración: retrato libre si lo hay, y si no, portada tipográfica. Se deja
un aviso en la pieza. Con 401, 403 o 429 no se reintenta: se desactiva para el resto de la ejecución
y se avisa en el informe. Con 503 se hace un único reintento, porque la documentación lo
recomienda. Los mensajes de error se limpian de claves antes de guardarse (regla 7).

**Revisión humana.** Un retrato generado puede no parecerse. La pieza entra en `revision_humana`
(«retrato ilustrado: comprobar el parecido») y no se publica sin ojos humanos.

**Crédito en el pie** (en la imagen no aparece, como hasta ahora):

> Retrato: ilustración generada con IA (Magnific) a partir de una foto de Bernard Gotfryd, Library of
> Congress.

Licencia de la foto si es CC BY o CC BY-SA, con la mención «obra derivada». Se guarda en
`<pieza>-retrato.json` con `fuente: "Magnific"`, la foto de origen y el `task_id`, por trazabilidad
(regla 5).

**Coste por pieza.** Una llamada (unos 20–30 s) más la descarga. El precio unitario de Seedream y
de Kontext hay que confirmarlo en el panel antes de activar nada; Style Transfer cuesta 0,10 €. El
informe suma el coste por pieza y por día, como con los modelos de texto. Hay un tope diario
(`coste_max_dia_eur`) y la caché por foto y prompt (`data/cache/ilustrados/<hash>.jpg`) hace que
relanzar el día no vuelva a pagar.

**Tests con respuestas simuladas** (sin red ni gasto, `httpx.MockTransport`):

- `POST` → `CREATED`; `GET` → `IN_PROGRESS` → `COMPLETED` con URL: descarga y fija
  `<pieza>-retrato.jpg` y su `.json` con el crédito.
- `FAILED` con `error`: sin ilustración, con aviso y la portada en el siguiente recurso.
- Tiempo agotado: lo mismo, sin colgarse (reloj simulado).
- 403 y 429: no reintenta, desactiva para la ejecución y avisa.
- 503: un solo reintento.
- La clave no aparece en avisos, informes ni excepciones.
- Caché: la segunda vez no hay petición.
- `activo: false` o `cuando: sin_retrato` con retrato libre: no hay petición.
- Sin foto de partida: no hay petición (nunca se genera una cara desde cero).
- Configuración: una clave desconocida en `retrato_ilustrado` es un error.
