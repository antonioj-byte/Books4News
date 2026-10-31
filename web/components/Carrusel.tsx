"use client";

import { useEffect, useState } from "react";
import { Diapositiva, VideoPortada } from "./Diapositiva";

// Carrusel de la pieza: diapositiva grande, flechas (también con el teclado) y miniaturas. Si hay
// vídeo de portada, la diapositiva 1 grande es el vídeo (la miniatura sigue siendo la imagen).
export function Carrusel({ total, url, ancho, inicial = 1, video }: {
  total: number; url: (n: number) => string; ancho: number; inicial?: number; video?: string | null;
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
  const boton = "h-11 w-11 rounded-full bg-tinta text-xl leading-none text-papel shadow-[var(--sombra-boton)] disabled:opacity-20 disabled:shadow-none hover:bg-noche";
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex items-center gap-3">
        <button className={boton} disabled={actual <= 1} onClick={() => setN(actual - 1)} aria-label="Anterior">‹</button>
        {actual === 1 && video
          ? <VideoPortada src={video} ancho={ancho} />
          : <Diapositiva src={url(actual)} ancho={ancho} titulo={`Diapositiva ${actual}`} />}
        <button className={boton} disabled={actual >= total} onClick={() => setN(actual + 1)} aria-label="Siguiente">›</button>
      </div>
      <div className="mt-2 flex gap-2.5">
        {Array.from({ length: total }, (_, i) => i + 1).map((k) => (
          <button key={k} onClick={() => setN(k)} aria-label={`Ir a la diapositiva ${k}`}
                  className={`rounded-[6px] outline-offset-2 ${k === actual ? "outline-2 outline-carmesi" : "opacity-60 hover:opacity-100"}`}>
            <Diapositiva src={url(k)} ancho={64} titulo={`Miniatura ${k}`} />
          </button>
        ))}
      </div>
    </div>
  );
}
