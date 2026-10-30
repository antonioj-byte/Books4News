# Web (Next.js). Contexto de build: web/. Railway: servicio «web», root directory «web», dominio público.
# FOLIO_API (dirección privada de la API) se necesita al construir: los rewrites quedan fijados en el build.
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-bookworm-slim AS build
WORKDIR /app
ARG FOLIO_API=http://127.0.0.1:8000
ENV FOLIO_API=$FOLIO_API NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules node_modules
COPY . .
RUN npm run build

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static .next/static
COPY --from=build /app/public public
EXPOSE 3000
# FOLIO_CLAVE_WEB se lee al arrancar (proxy.ts): la contraseña no queda en la imagen
CMD ["node", "server.js"]
