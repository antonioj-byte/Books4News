import type { Metadata } from "next";
import Link from "next/link";
import { Isotipo } from "@/components/Isotipo";
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
      <body className="flex min-h-full flex-col">
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-borde px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-3">
            <Isotipo />
            <span className="titular text-[22px]">Folio</span>
            <span className="antetitulo hidden sm:inline">Mesa de edición</span>
          </Link>
          <nav className="-mx-2 flex flex-wrap gap-x-0.5 text-sm sm:mx-0 sm:gap-1">
            <Link href="/" className="whitespace-nowrap rounded-full px-2 py-1.5 hover:bg-papel-hondo sm:px-3">Hoy</Link>
            <Link href="/fondo" className="whitespace-nowrap rounded-full px-2 py-1.5 hover:bg-papel-hondo sm:px-3">Fondo</Link>
            <Link href="/como-vamos" className="whitespace-nowrap rounded-full px-2 py-1.5 hover:bg-papel-hondo sm:px-3">Cómo vamos</Link>
          </nav>
        </header>
        <main className="flex-1">{children}</main>
        <Avisos />
      </body>
    </html>
  );
}
