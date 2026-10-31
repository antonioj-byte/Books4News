# Publicar en Instagram y ejecución diaria

## Ejecución diaria (contenido listo a primera hora)

La API lanza sola, cada día, el pipeline y después el render (PNG de cada diapositiva y portada en
vídeo) de la primera propuesta de la mesa. Para que a las 5:30 esté la mesa, en el servicio «api» de Railway:

```
FOLIO_EJECUCION_DIARIA=04:45      # hora de Madrid (FOLIO_ZONA, por defecto Europe/Madrid): mesa lista a las 5:30
```

Una vez al día. Si a esa hora hay otra ejecución en marcha, espera a que acabe. Si la API arranca más
tarde (un despliegue), recupera la del día solo hasta dos horas después; pasado ese margen, espera a
mañana. `GET /api/ejecuciones/programada` dice si está activa y cuándo toca. Cuesta lo mismo que
lanzarla a mano (~1 $ por día).

## Programar con Buffer (lo más sencillo)

Buffer conecta el Instagram de Folio sin crear una app en Meta y programa a una hora. El plan gratis basta
(3 canales y 10 publicaciones en cola por canal). La cuenta de Instagram tiene que ser profesional.

1. En buffer.com, conecta el Instagram de Folio y crea una clave de la API (developers.buffer.com).
2. Variables del servicio «api» (nunca en el repo): `BUFFER_API_KEY` y, si hay más de un canal de
   Instagram en la cuenta, `BUFFER_CHANNEL_ID`. Hacen falta también `FOLIO_URL_PUBLICA` y
   `FOLIO_CLAVE_ENLACES` (abajo): Buffer descarga los archivos de ahí.
3. Comprobar (solo lectura): `uv run folio buffer comprobar` lista la organización, los canales y el de
   Instagram que se usará.
4. Programar una pieza **aprobada**:

   ```bash
   uv run folio buffer programar 2026-10-31-1 --a "09:30"                         # prepara y enseña; no programa
   uv run folio buffer programar 2026-10-31-1 --a "09:30" --confirmar --borrador  # a los borradores de Buffer (prueba)
   uv run folio buffer programar 2026-10-31-1 --a "2026-11-02 09:30" --confirmar  # programada
   ```

   Sin `--a`, va a la cola de Buffer. La hora es la de Madrid (`FOLIO_ZONA`).

Buffer descarga los archivos **al publicar**, no al programar: se copian a
`informes/<fecha>/publicar/<pieza>-buffer/` y sus enlaces firmados valen hasta tres días después de la
hora (treinta con la cola). No borres esa carpeta hasta que salga. Ante 401, 403 o 429 se para sin
reintentar.

## Conectar la cuenta de Instagram de Folio (API de Meta, sin intermediarios)

Se usa la API de Instagram con login de Instagram: no hace falta página de Facebook ni intermediarios.

1. **Cuenta profesional.** En la app de Instagram, la cuenta de Folio tiene que ser de empresa o de
   creador (Configuración → Tipo de cuenta y herramientas).
2. **App de Meta.** En developers.facebook.com, crea una app con el caso de uso de la API de Instagram y,
   en «Configuración de la API con inicio de sesión de Instagram», añade la cuenta de Folio y genera un
   token. Permisos: `instagram_business_basic` e `instagram_business_content_publish`. Para publicar en
   una cuenta propia que tiene un rol en la app debería bastar el modo de desarrollo; si Meta pide la
   revisión de la app, se pide entonces.
3. **Variables del servicio «api»** (nunca en el repo):

   ```
   INSTAGRAM_TOKEN=            # el token de la app (caduca a los 60 días: hay que generar otro)
   INSTAGRAM_USER_ID=          # opcional: si falta, se pide a la API
   FOLIO_URL_PUBLICA=          # la URL pública del servicio «web», p. ej. https://folio-web.up.railway.app
   FOLIO_CLAVE_ENLACES=        # clave larga y aleatoria: python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Y desplegar también «web»: deja pasar sin contraseña solo `/api/publico/`, los archivos que Instagram
   descarga, y la API solo los sirve con una firma válida que caduca en una hora.

4. **Comprobar** (solo lectura): `uv run folio instagram comprobar` dice la cuenta conectada y cuántas
   publicaciones lleva en 24 h. Un error con el código 190 es un token caducado.

## Publicar una pieza

Solo se publican piezas **aprobadas** en la web, en su versión actual (con las ediciones):

```bash
uv run folio instagram publicar 2026-10-31-1              # prepara y enseña el pie; no publica
uv run folio instagram publicar 2026-10-31-1 --confirmar  # publica el carrusel
```

El carrusel lleva la portada en vídeo (si tiene imagen) y el resto de diapositivas en JPEG; el pie es el
del guion con los créditos de las imágenes debajo. Los archivos quedan en
`informes/<fecha>/publicar/<pieza>/`. Al publicar, la pieza pasa a «publicada».

Instagram no programa publicaciones: se publican en el momento. Programarlas a una hora (y un botón en la
web) es el paso siguiente. Ante un 403, un 429 o el límite de publicaciones, se para sin reintentar.
