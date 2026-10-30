import type { Metadata } from "next";
import Link from "next/link";
import { Isotipo } from "@/components/Isotipo";
import "./globals.css";

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
      <body className="flex min-h-full flex-col">
        <header className="flex items-center justify-between border-b border-borde px-6 py-3">
          <Link href="/" className="flex items-center gap-3">
            <Isotipo />
            <span className="titular text-[22px]">Folio</span>
            <span className="antetitulo hidden sm:inline">Mesa de edición</span>
          </Link>
          <nav className="flex gap-1 text-sm">
            <Link href="/" className="rounded-full px-3 py-1.5 hover:bg-papel-hondo">Portada del día</Link>
            <Link href="/evaluacion" className="rounded-full px-3 py-1.5 hover:bg-papel-hondo">Evaluación</Link>
          </nav>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
