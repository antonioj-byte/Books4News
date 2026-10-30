"use client";

// Una diapositiva tal como sale en el PNG: el HTML de la plantilla (servido por la API) en un
// iframe de 1080×1350 escalado al ancho pedido.
const ANCHO = 1080;
const ALTO = 1350;

export function Diapositiva({ src, ancho, titulo }: { src: string; ancho: number; titulo: string }) {
  const escala = ancho / ANCHO;
  return (
    <div className="relative overflow-hidden rounded-[6px] bg-papel shadow-[var(--sombra-libro)]"
         style={{ width: ancho, height: ALTO * escala }}>
      <iframe
        src={src}
        title={titulo}
        width={ANCHO}
        height={ALTO}
        className="pointer-events-none absolute left-0 top-0 origin-top-left border-0"
        style={{ transform: `scale(${escala})` }}
      />
    </div>
  );
}
