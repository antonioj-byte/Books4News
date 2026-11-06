"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BandejaTrabajos } from "@/components/BandejaTrabajos";
import { Isotipo } from "@/components/Isotipo";

// Menú lateral de la agencia (3/11, a petición del usuario: «tipo modelos SaaS clásico»). Arriba, la cuenta (hoy solo
// Folio; mañana, otras marcas); debajo, el trabajo (Hoy, Archivo, Fondo), la agencia (Equipo, Marca) y Cómo vamos.
// En la ficha de una pieza se encoge a iconos para dejar sitio al carrusel y al chat. En el móvil va arriba, en fila.
const GRUPOS: { titulo: string | null; items: { href: string; texto: string; icono: string; activa: (p: string) => boolean }[] }[] = [
  { titulo: "Trabajo", items: [
    { href: "/", texto: "Hoy", icono: "◉", activa: (p) => p === "/" || p.startsWith("/dia") || p.startsWith("/pieza") },
    { href: "/archivo", texto: "Archivo", icono: "▤", activa: (p) => p.startsWith("/archivo") },
    { href: "/fondo", texto: "Fondo", icono: "◫", activa: (p) => p.startsWith("/fondo") },
  ] },
  { titulo: "Agencia", items: [
    { href: "/equipo", texto: "Equipo", icono: "◎", activa: (p) => p.startsWith("/equipo") },
    { href: "/marca", texto: "Marca", icono: "◆", activa: (p) => p.startsWith("/marca") },
    { href: "/estilo", texto: "Libro de estilo", icono: "¶", activa: (p) => p.startsWith("/estilo") },
  ] },
  { titulo: null, items: [
    { href: "/como-vamos", texto: "Cómo vamos", icono: "↗", activa: (p) => p.startsWith("/como-vamos") || p.startsWith("/memoria") || p.startsWith("/gasto") || p.startsWith("/evaluacion") },
  ] },
];

export function MenuLateral() {
  const ruta = usePathname() ?? "/";
  const estrecho = ruta.startsWith("/pieza");
  return (
    <aside className={`group/menu flex shrink-0 flex-row flex-wrap items-center gap-2 border-b border-borde bg-panel px-3 py-2 lg:sticky lg:top-0 lg:h-screen lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-3 lg:border-b-0 lg:border-r lg:py-4 ${estrecho ? "lg:w-[60px] lg:px-2 lg:hover:w-[210px]" : "lg:w-[210px]"} transition-[width] duration-150`}>
      <Link href="/" className="flex items-center gap-2.5 px-1" title="Folio · Mesa de edición">
        <Isotipo tamano={28} />
        <span className={`flex flex-col leading-none ${estrecho ? "lg:hidden lg:group-hover/menu:flex" : ""}`}>
          {/* La cuenta: hoy solo hay una marca */}
          <span className="titular text-[20px]">Folio</span>
          <span className="antetitulo mt-1 hidden text-[9.5px] lg:inline">Mesa de edición</span>
        </span>
      </Link>
      <BandejaTrabajos estrecho={estrecho} />
      <nav className="flex flex-row flex-wrap gap-0.5 text-[14px] lg:flex-col" aria-label="Secciones">
        {GRUPOS.map((g, i) => (
          <div key={i} className="contents lg:flex lg:flex-col lg:gap-0.5">
            {g.titulo
              ? <span className={`dato hidden px-2.5 pb-0.5 pt-3 uppercase tracking-[0.16em] lg:block ${estrecho ? "lg:hidden lg:group-hover/menu:block" : ""}`}>{g.titulo}</span>
              : <span className="mx-2 my-2 hidden border-t border-borde lg:block" />}
            {g.items.map((it) => {
              const on = it.activa(ruta);
              return (
                <Link key={it.href} href={it.href} title={it.texto} aria-current={on ? "page" : undefined}
                      className={`flex items-center gap-2.5 whitespace-nowrap rounded-[10px] px-2.5 py-1.5 hover:bg-papel-hondo ${on ? "bg-papel-hondo font-semibold" : ""}`}>
                  <span aria-hidden className={`hidden w-4 text-center text-[13px] lg:inline ${on ? "text-carmesi" : "text-tinta-suave"}`}>{it.icono}</span>
                  <span className={estrecho ? "lg:hidden lg:group-hover/menu:inline" : ""}>{it.texto}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
