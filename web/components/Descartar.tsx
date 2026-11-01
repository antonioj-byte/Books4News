"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// Descartar con su motivo (2/11): un toque en una etiqueta y, si se quiere, una línea. Va al jefe de cultura a través
// de la Memoria; descartar sin decir nada también vale.
export function Descartar({ eid, pid, onHecho, compacto = false }: { eid: number; pid: string; onHecho: () => void; compacto?: boolean }) {
  const [abierto, setAbierto] = useState(false);
  const [motivos, setMotivos] = useState<string[]>([]);
  const [marcados, setMarcados] = useState<string[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (abierto && !motivos.length) api.motivosDescarte().then(setMotivos).catch(() => setMotivos([])); }, [abierto, motivos.length]);

  const parar = (e: React.MouseEvent) => { e.preventDefault(); e.stopPropagation(); };
  const enviar = async (e: React.MouseEvent) => {
    parar(e); setEnviando(true); setError(null);
    try { await api.descartar(eid, pid, marcados, texto.trim()); setAbierto(false); onHecho(); }
    catch (err) { setError(err instanceof Error ? err.message.replace(/^\d+ \S+: /, "") : "No se pudo descartar"); }
    finally { setEnviando(false); }
  };

  if (!abierto) {
    return <button onClick={(e) => { parar(e); setAbierto(true); }} className={compacto ? "dato self-start underline-offset-2 hover:text-carmesi hover:underline" : "boton-suave"}>Descartar</button>;
  }
  return (
    <div onClick={parar} className="flex flex-col gap-2 rounded-[10px] border border-dashed border-carmesi p-3 text-[13px]">
      <span className="flex justify-between gap-2 font-semibold">¿Por qué no?<span className="dato font-normal">al jefe de cultura</span></span>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Motivos del descarte">
        {motivos.map((m) => (
          <button key={m} aria-pressed={marcados.includes(m)}
                  onClick={(e) => { parar(e); setMarcados((x) => x.includes(m) ? x.filter((y) => y !== m) : [...x, m]); }}
                  className={`rounded-full border px-3 py-1 ${marcados.includes(m) ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-panel hover:border-tinta"}`}>
            {m}
          </button>
        ))}
      </div>
      <input id={`descarte-${pid}`} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Una línea más (opcional)"
             className="rounded-[8px] border border-borde bg-papel px-2 py-1.5 outline-none focus:border-tinta" />
      <div className="flex flex-wrap gap-2">
        <button onClick={enviar} disabled={enviando} className="boton">{enviando ? "Descartando…" : "Descartar"}</button>
        <button onClick={(e) => { parar(e); setAbierto(false); }} disabled={enviando} className="boton-suave">Cancelar</button>
      </div>
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}
