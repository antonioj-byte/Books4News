"use client";

import { useEffect, useRef, useState } from "react";
import { api, type MensajeChat } from "@/lib/api";

// Chat de edición: se pide un cambio con palabras y el editor (Opus) devuelve la pieza revisada, que
// tiene que pasar las reglas del guion. Cada cambio es una versión nueva; `onCambio` recarga la pieza.
export function ChatEdicion({ eid, pid, onCambio }: { eid: number; pid: string; onCambio: () => void }) {
  const [mensajes, setMensajes] = useState<MensajeChat[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const final = useRef<HTMLDivElement>(null);

  useEffect(() => { api.chat(eid, pid).then(setMensajes).catch(() => setMensajes([])); }, [eid, pid]);
  useEffect(() => { final.current?.scrollIntoView({ block: "nearest" }); }, [mensajes, enviando]);

  const enviar = async () => {
    const m = texto.trim();
    if (!m || enviando) return;
    setEnviando(true); setError(null); setTexto("");
    setMensajes((x) => [...x, { n: x.length + 1, rol: "usuario", texto: m, version_n: null, creado_en: "" }]);
    try {
      const r = await api.enviarChat(eid, pid, m);
      setMensajes(await api.chat(eid, pid));
      if (r.version) onCambio();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo enviar");
      setTexto(m);
      setMensajes((x) => x.slice(0, -1));      // el mensaje no llegó a guardarse
    } finally { setEnviando(false); }
  };

  return (
    <div className="flex flex-col gap-2.5 text-[13.5px]">
      <div className="flex max-h-[340px] flex-col gap-2 overflow-y-auto">
        {mensajes.length === 0 && (
          <p className="text-tinta-suave">Pide un cambio: «el titular más corto», «menos técnico el cierre», «otra idea en la 4»…</p>
        )}
        {mensajes.map((m) => (
          <div key={m.n} className={`max-w-[92%] rounded-[12px] px-3 py-2 leading-snug ${m.rol === "usuario" ? "self-end bg-tinta text-papel" : "self-start border border-borde bg-panel"}`}>
            {m.texto}
            {m.version_n && <span className="dato mt-1 block text-carmesi">→ versión {m.version_n}</span>}
          </div>
        ))}
        {enviando && <p className="dato self-start">El editor está trabajando…</p>}
        <div ref={final} />
      </div>
      <div className="flex gap-2">
        <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} disabled={enviando}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
                  placeholder="Escribe al editor… (Intro para enviar)"
                  className="min-w-0 flex-1 resize-none rounded-[12px] border border-borde bg-panel p-2.5 text-[13.5px] outline-none focus:border-tinta" />
        <button onClick={enviar} disabled={enviando || !texto.trim()} className="boton self-end">→</button>
      </div>
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}
