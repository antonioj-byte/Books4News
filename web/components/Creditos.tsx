"use client";

import { useState } from "react";
import type { Credito } from "@/lib/api";

// Los créditos de una pieza (3/11, la agencia): quién trabajó en ella, qué hizo y cuánto costó, como en una agencia.
// En rojo, quien levantó la mano (un hecho sin verificar, un puente justo). Al pulsar, el coste de cada rol.
export function Creditos({ creditos }: { creditos: Credito[] }) {
  const [abierto, setAbierto] = useState(false);
  if (!creditos.length) return null;
  const usd = creditos.reduce((s, c) => s + c.coste_usd, 0);
  const eur = creditos.reduce((s, c) => s + c.coste_eur, 0);
  const coste = [usd ? `${usd.toFixed(2)} $` : "", eur ? `${eur.toFixed(2)} €` : ""].filter(Boolean).join(" · ");
  return (
    <div className="mb-4 flex flex-wrap items-center gap-1.5 text-[12.5px]" aria-label="Créditos de la pieza">
      <span className="dato uppercase tracking-[0.14em]">Hecha por</span>
      {creditos.map((c) => (
        <button key={c.rol} onClick={() => setAbierto((v) => !v)} title={c.llamadas ? `${c.llamadas} llamadas` : undefined}
                className="inline-flex items-center gap-1.5 rounded-full border border-borde bg-panel px-2.5 py-0.5 hover:border-tinta">
          <span aria-hidden className={`h-[7px] w-[7px] rounded-full ${c.alerta ? "bg-carmesi" : "bg-verde"}`} />
          <b className="font-semibold">{c.nombre}</b> · {c.que}
          {abierto && (c.coste_usd || c.coste_eur) ? <span className="dato">{c.coste_usd ? ` ${c.coste_usd.toFixed(3)} $` : ""}{c.coste_eur ? ` ${c.coste_eur.toFixed(2)} €` : ""}</span> : null}
        </button>
      ))}
      {coste && <span className="dato">{coste}</span>}
    </div>
  );
}
