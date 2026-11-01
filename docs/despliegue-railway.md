# Despliegue en Railway (evaluación de la Fase 1)

Dos servicios en el proyecto «folio», desde el repositorio `antonioj-byte/Books4News`, rama `fase-3-web`.

| | «api» | «web» |
|---|---|---|
| Root directory | (vacío: la raíz) | `web` |
| Builder | Dockerfile, `api/Dockerfile` | Dockerfile, `Dockerfile` |
| Dominio público | **No** | Sí, puerto 3000 |
| Volumen | `/datos` | — |
| Memoria | ≥ 4 GB (embeddings) | la mínima |

Variables:

| Servicio | Variable | Valor |
|---|---|---|
| api | `ANTHROPIC_API_KEY` | la clave (secreta) |
| api | `GOOGLE_BOOKS_API_KEY` | la clave (secreta) |
| api | `OPENLIBRARY_CONTACT` | email de contacto |
| api | `FOLIO_DATOS` | `/datos` |
| api | `PORT` | `8000` |
| api | `MAGNIFIC_API_KEY` | la clave de Magnific (secreta). Opcional: retratos generados (`arte.retrato_generado`) |
| api | `FOLIO_EJECUCION_DIARIA` | opcional: `04:45` para tener la mesa del día a las 5:30 (pipeline y render, hora de Madrid) |
| api | `INSTAGRAM_TOKEN` | opcional: token de la cuenta de Instagram de Folio (secreto; caduca a los 60 días). Ver `docs/instagram.md` |
| api | `INSTAGRAM_USER_ID` | opcional: id de la cuenta de Instagram (si falta, se pide a la API) |
| api | `FOLIO_LECTURA_CADA` | minutos entre lecturas de los RSS (p. ej. `120`); sin ella, no se lee durante el día |
| api | `FOLIO_URL_PUBLICA` | para publicar: la URL pública del servicio «web» |
| api | `FOLIO_CLAVE_ENLACES` | para publicar: clave larga y aleatoria con que se firman los enlaces (secreta) |
| api | `EUROPEANA_API_KEY` | la clave de Europeana (secreta). Opcional: sin ella se usa la clave pública de demostración |
| web | `FOLIO_API` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` |
| web | `FOLIO_CLAVE_WEB` | la contraseña de la web (secreta) |
| web | `PORT` | `3000` |

`FOLIO_API` se usa al construir la web (los rewrites quedan fijados en el build): si cambia, hay que
volver a desplegar «web». `FOLIO_CLAVE_WEB` se lee al arrancar.

Actualizar: desde el 2/11 los dos servicios tienen el **autodespliegue encendido** sobre la rama
`fase-3-web` (lo activó el usuario al dejar de usar Instinct): cada push a esa rama se despliega solo en
unos minutos, así que solo se sube a `fase-3-web` cuando el usuario dice «mergea». Para desplegar a mano
(o repetir un despliegue): en cada servicio, «Deploy» del último commit, o «Redeploy».
Las variables nuevas se añaden en el servicio y Railway pide desplegar para aplicarlas. Desde el 31/10,
cada ejecución lee también unos 1.100 artículos del carril editorial: un par de minutos más de
embeddings, con la misma memoria.

Primer uso: entrar en la URL pública con la contraseña (cualquier usuario) y pulsar «Lanzar ejecución
del día». La primera vez descarga el modelo de embeddings (2,2 GB) al volumen: tarda más.

Comprobado antes del primer despliegue (30/10): instalación limpia de la API con las mismas órdenes de
`uv` que la imagen, API con `FOLIO_DATOS` y `PORT`, build standalone de la web, contraseña (401 sin
ella, 200 con ella en páginas, `/api` y `/diseno`) y vista en el navegador. No se pudo probar aquí la
construcción de las imágenes (sin acceso a los registros desde los contenedores) ni la escucha en IPv6
(este entorno no tiene IPv6).
