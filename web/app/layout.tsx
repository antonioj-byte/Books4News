import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Folio · mesa de edición",
  description: "Herramienta local para leer, editar y evaluar las piezas de Folio.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className="h-full antialiased">
      <head>
        {/* Fuentes y tokens del design system: los sirve la API desde diseno/, la única fuente. */}
        {/* eslint-disable-next-line @next/next/no-css-tags */}
        <link rel="stylesheet" href="/diseno/fuentes/fuentes.css" />
        {/* eslint-disable-next-line @next/next/no-css-tags */}
        <link rel="stylesheet" href="/api/diseno/tokens.css" />
      </head>
      <body className="min-h-full flex flex-col">
        <header className="flex items-end justify-between border-b-[3px] border-tinta px-6 pt-4 pb-2">
          <Link href="/" className="font-texto text-[28px] italic leading-none">
            Folio<span className="text-acento">.</span>{" "}
            <span className="rotulo align-middle not-italic">mesa de edición</span>
          </Link>
          <nav className="flex gap-6 text-sm">
            <Link href="/" className="hover:text-acento">Portada del día</Link>
            <Link href="/evaluacion" className="hover:text-acento">Evaluación</Link>
          </nav>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
