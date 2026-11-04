"use client";

import { useEffect, useState } from "react";

// Atajos de teclado de la ficha de la pieza (4/11, usabilidad, fase 3). No actúan mientras se escribe en un campo.
// «?» abre la ayuda; las flechas ya pasan las diapositivas (Carrusel).
export type Atajo = { tecla: string; texto: string; hacer?: () => void };

function escribiendo(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function Atajos({ atajos }: { atajos: Atajo[] }) {
  const [ayuda, setAyuda] = useState(false);
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || escribiendo(e)) return;
      if (e.key === "?") { e.preventDefault(); setAyuda((x) => !x); return; }
      if (e.key === "Escape") { setAyuda(false); return; }
      const a = atajos.find((x) => x.hacer && x.tecla.toLowerCase() === e.key.toLowerCase());
      if (a) { e.preventDefault(); a.hacer!(); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [atajos]);

  return (
    <>
      <button onClick={() => setAyuda(true)} className="hidden items-center gap-1.5 text-[12.5px] text-tinta-suave hover:text-tinta lg:inline-flex" title="Atajos de teclado">
        <kbd className="rounded-[5px] border border-borde bg-papel px-1.5 font-mono text-[11px]">?</kbd>Atajos
      </button>
      {ayuda && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-tinta/40 p-4" onClick={() => setAyuda(false)}>
          <div role="dialog" aria-label="Atajos de teclado" onClick={(e) => e.stopPropagation()}
               className="w-full max-w-[360px] rounded-[14px] border border-borde bg-panel p-5 shadow-xl">
            <div className="mb-3 flex items-baseline justify-between"><b className="titular text-[22px]">Atajos</b>
              <button className="text-tinta-suave hover:text-tinta" onClick={() => setAyuda(false)} aria-label="Cerrar">✕</button></div>
            <ul className="flex flex-col gap-2 text-[14px]">
              {[...atajos, { tecla: "← →", texto: "Diapositiva anterior y siguiente" }, { tecla: "?", texto: "Abrir y cerrar esta ayuda" }].map((a) => (
                <li key={a.tecla} className="flex items-center justify-between gap-3">
                  <span className={a.hacer === undefined && a.tecla !== "← →" && a.tecla !== "?" ? "text-tinta-suave" : ""}>{a.texto}</span>
                  <kbd className="rounded-[6px] border border-borde bg-papel px-2 py-0.5 font-mono text-[12px]">{a.tecla}</kbd>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
