import type { Metadata } from "next";
import { Suspense } from "react";
import { MenuLateral } from "@/components/MenuLateral";
import "./globals.css";
import { Avisos } from "@/components/Avisos";

export const metadata: Metadata = {
  title: "Folio · Mesa de edición",
  description: "Leer, evaluar y editar las piezas del día.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className="h-full antialiased">
      <head>
        {/* Fuentes de la marca (public/fuentes, OFL): se sirven desde aquí, sin depender de la red */}
        {/* eslint-disable-next-line @next/next/no-css-tags */}
        <link rel="stylesheet" href="/fuentes/fuentes.css" />
      </head>
      <body className="flex min-h-full flex-col lg:flex-row">
        {/* El menú lee la ruta para marcar la sección: dentro de Suspense para no bloquear el prerender */}
        <Suspense fallback={<aside className="shrink-0 border-b border-borde bg-panel lg:h-screen lg:w-[210px] lg:border-b-0 lg:border-r" />}>
          <MenuLateral />
        </Suspense>
        <main className="min-w-0 flex-1">{children}</main>
        <Avisos />
      </body>
    </html>
  );
}
