"use client";

import { useEffect, useState } from "react";
import { Diapositiva } from "./Diapositiva";

// Carrusel de la pieza: diapositiva grande, flechas (también con el teclado) y miniaturas.
export function Carrusel({ total, url, ancho, inicial = 1 }: {
  total: number; url: (n: number) => string; ancho: number; inicial?: number;
}) {
  const [n, setN] = useState(inicial);
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, [contenteditable]")) return;
      if (e.key === "ArrowRight") setN((x) => Math.min(total, x + 1));
      if (e.key === "ArrowLeft") setN((x) => Math.max(1, x - 1));
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [total]);
  const actual = Math.min(n, total);
  const boton = "h-9 w-9 rounded-full border border-tinta text-lg leading-none disabled:opacity-25 hover:bg-tinta hover:text-papel";
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex items-center gap-3">
        <button className={boton} disabled={actual <= 1} onClick={() => setN(actual - 1)} aria-label="Anterior">‹</button>
        <Diapositiva src={url(actual)} ancho={ancho} titulo={`Diapositiva ${actual}`} />
        <button className={boton} disabled={actual >= total} onClick={() => setN(actual + 1)} aria-label="Siguiente">›</button>
      </div>
      <div className="flex gap-2">
        {Array.from({ length: total }, (_, i) => i + 1).map((k) => (
          <button key={k} onClick={() => setN(k)} aria-label={`Ir a la diapositiva ${k}`}
                  className={`outline-offset-2 ${k === actual ? "outline-2 outline-acento" : "opacity-70 hover:opacity-100"}`}>
            <Diapositiva src={url(k)} ancho={64} titulo={`Miniatura ${k}`} />
          </button>
        ))}
      </div>
    </div>
  );
}
