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
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/diseno/:path*", destination: `${API}/diseno/:path*` },
    ];
  },
};

export default nextConfig;
