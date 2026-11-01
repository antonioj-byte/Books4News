"use client";

import { useState } from "react";
import { api, type Nota } from "@/lib/api";

// Una nota sobre la diapositiva que se ve (2/11): para el director de arte o para el guionista. No cambia la pieza
// (para eso, el chat): la lee la Memoria, que sabe qué recurso llevaba la diapositiva.
export function NotasDiapositiva({ eid, pid, n, notas, onCambio }: {
  eid: number; pid: string; n: number; notas: Nota[]; onCambio: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [destino, setDestino] = useState<"director_arte" | "guionista">("director_arte");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deEsta = notas.filter((x) => x.tipo === "diapositiva" && x.diapositiva === n);

  const guardar = async () => {
    if (texto.trim().length < 2) return;
    setEnviando(true); setError(null);
    try { await api.anadirNota(eid, pid, destino, n, texto.trim()); setTexto(""); setAbierto(false); onCambio(); }
    catch (e) { setError(e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo guardar"); }
    finally { setEnviando(false); }
  };

  return (
    <div className="flex w-full max-w-[440px] flex-col gap-2 text-[13px]">
      {deEsta.map((x) => (
        <div key={x.id} className="flex items-start justify-between gap-2 rounded-[10px] border border-borde bg-panel px-3 py-2">
          <span><span className="dato">{x.destino === "guionista" ? "Copy" : "Arte"} · </span>{x.texto}</span>
          <button onClick={() => api.borrarNota(eid, pid, x.id).then(onCambio)} aria-label="Borrar la nota" className="text-tinta-suave hover:text-carmesi">✕</button>
        </div>
      ))}
      {abierto ? (
        <div className="flex flex-col gap-2 rounded-[10px] border border-borde bg-panel p-3">
          <textarea id={`nota-${pid}-${n}`} value={texto} onChange={(e) => setTexto(e.target.value)} rows={3}
                    placeholder="Qué falla o qué funciona en esta diapositiva"
                    className="resize-none rounded-[8px] border border-borde bg-papel p-2 outline-none focus:border-tinta" />
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="A quién va la nota">
            {([["director_arte", "Arte"], ["guionista", "Copy"]] as const).map(([v, t]) => (
              <button key={v} aria-pressed={destino === v} onClick={() => setDestino(v)}
                      className={`rounded-full border px-3 py-1 ${destino === v ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-papel hover:border-tinta"}`}>{t}</button>
            ))}
            <span className="dato ml-auto">No cambia la pieza: es para la Memoria</span>
          </div>
          <div className="flex gap-2">
            <button onClick={guardar} disabled={enviando || texto.trim().length < 2} className="boton">{enviando ? "Guardando…" : "Guardar nota"}</button>
            <button onClick={() => setAbierto(false)} disabled={enviando} className="boton-suave">Cancelar</button>
          </div>
          {error && <p className="text-carmesi">{error}</p>}
        </div>
      ) : (
        <button onClick={() => setAbierto(true)} className="self-center text-tinta-suave underline-offset-2 hover:text-tinta hover:underline">
          + Comentar esta diapositiva (arte o copy)
        </button>
      )}
    </div>
  );
}
