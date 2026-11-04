import type { NextConfig } from "next";

// La API (FastAPI, `uv run folio web`) sirve los datos, el HTML de las diapositivas y el design
// system. Se reenvía desde aquí para que el navegador solo hable con un origen.
const API = process.env.FOLIO_API ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Servidor autónomo para la imagen Docker (Railway)
  output: "standalone",
  // Solo local: se abre como http://localhost:3000 o http://127.0.0.1:3000.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  cacheComponents: true,
  experimental: {
    // El proxy de /api corta por defecto a los 30 s: un turno del chat con Opus, programar en Buffer o la
    // descarga del .zip tardan más, y la web devolvía un 500 («socket hang up», 2/11) mientras la api terminaba
    proxyTimeout: 300_000,
  },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // La portada y las mesas no se guardan en caché del navegador (4/11: «la caché me lleva al domingo 1 de noviembre»)
  async headers() {
    return ["/", "/dia/:path*"].map((source) => ({ source, headers: [{ key: "Cache-Control", value: "no-store" }] }));
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/diseno/:path*", destination: `${API}/diseno/:path*` },
    ];
  },
};

export default nextConfig;
