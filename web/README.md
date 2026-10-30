# Folio · mesa de edición (web local)

Herramienta local para leer, evaluar y editar las piezas de Folio (Fase 3, versión mínima).

```bash
uv run folio web --recargar   # desde la raíz del repositorio: API en http://127.0.0.1:8000
npm install
npm run dev                   # http://localhost:3000
npm run tipos                 # regenera lib/tipos.ts desde el OpenAPI (con la API en marcha)
```

`/api` y `/diseno` se reenvían a la API (`next.config.ts`). Las diapositivas son el HTML de
`diseno/plantillas/`, el mismo que genera los PNG.
