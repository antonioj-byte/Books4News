"use client";

import { useState } from "react";
import { api, type Nota } from "@/lib/api";

// Una nota sobre la diapositiva que se ve (2/11): para el director de arte o para el guionista. Queda para la Memoria
// (que sabe qué recurso llevaba la diapositiva) y, si se marca «Aplicar ahora» (2/11, a petición del usuario:
// «necesito poder editar imagen si es necesario; que vaya a la memoria y se apliquen los cambios»), el editor del chat
// la ejecuta en ese momento: texto, imagen, composición… Cada cambio es una versión nueva, como en el chat.
export function NotasDiapositiva({ eid, pid, n, notas, onCambio, onAplicada }: {
  eid: number; pid: string; n: number; notas: Nota[]; onCambio: () => void; onAplicada?: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [destino, setDestino] = useState<"director_arte" | "guionista">("director_arte");
  const [enviando, setEnviando] = useState<"" | "guardando" | "aplicando">("");
  const [aplicar, setAplicar] = useState(true);
  const [respuesta, setRespuesta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const deEsta = notas.filter((x) => x.tipo === "diapositiva" && x.diapositiva === n);

  const guardar = async () => {
    const t = texto.trim();
    if (t.length < 2) return;
    setEnviando("guardando"); setError(null); setRespuesta(null);
    try {
      await api.anadirNota(eid, pid, destino, n, t);
      onCambio();
      if (aplicar) {
        setEnviando("aplicando");
        const r = await api.enviarChat(eid, pid, `Nota sobre la diapositiva ${n} (${destino === "guionista" ? "copy" : "arte"}): ${t}`);
        setRespuesta(r.respuesta);
        onAplicada?.();
      }
      setTexto(""); setAbierto(false);
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo guardar");
    } finally { setEnviando(""); }
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
            <label className="ml-auto flex items-center gap-1.5">
              <input id={`aplicar-${pid}-${n}`} type="checkbox" checked={aplicar} onChange={(e) => setAplicar(e.target.checked)} />
              Aplicar ahora
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={guardar} disabled={!!enviando || texto.trim().length < 2} className="boton">
              {enviando === "aplicando" ? "Aplicando…" : enviando ? "Guardando…" : aplicar ? "Guardar y aplicar" : "Guardar nota"}
            </button>
            <button onClick={() => setAbierto(false)} disabled={!!enviando} className="boton-suave">Cancelar</button>
          </div>
          <span className="dato">{aplicar ? "Queda para la Memoria y el editor la aplica ahora (versión nueva)" : "Solo para la Memoria: no cambia la pieza"}</span>
          {enviando === "aplicando" && <span className="dato">El editor está aplicando la nota · hasta un minuto</span>}
          {error && <p className="text-carmesi">{error}</p>}
        </div>
      ) : (
        <button onClick={() => setAbierto(true)} className="self-center text-tinta-suave underline-offset-2 hover:text-tinta hover:underline">
          + Comentar esta diapositiva (arte o copy)
        </button>
      )}
      {respuesta && <p className="rounded-[10px] bg-papel-hondo px-3 py-2"><span className="dato">Editor · </span>{respuesta}</p>}
    </div>
  );
}
