"use client";

import { useEffect, useRef, useState } from "react";
import { api, type MensajeChat } from "@/lib/api";
import { MaterialesChat } from "@/components/MaterialesChat";

// Chat de edición: se pide un cambio con palabras y el editor (Opus) devuelve la pieza revisada, que
// tiene que pasar las reglas del guion. Cada cambio es una versión nueva; `onCambio` recarga la pieza.
export function ChatEdicion({ eid, pid, onCambio }: { eid: number; pid: string; onCambio: () => void }) {
  const [mensajes, setMensajes] = useState<MensajeChat[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [segundos, setSegundos] = useState(0);
  const final = useRef<HTMLDivElement>(null);

  useEffect(() => { api.chat(eid, pid).then(setMensajes).catch(() => setMensajes([])); }, [eid, pid]);
  useEffect(() => { final.current?.scrollIntoView({ block: "nearest" }); }, [mensajes, enviando]);
  // Un turno con Opus tarda; el contador deja claro que sigue trabajando (2/11: «parece que se queda bugueado»)
  useEffect(() => {
    if (!enviando) return;
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => { clearInterval(t); setSegundos(0); };
  }, [enviando]);

  const enviar = async (propio?: string) => {
    const m = (propio ?? texto).trim();
    if (!m || enviando) return;
    setEnviando(true); setError(null); setTexto("");
    setMensajes((x) => [...x, { n: x.length + 1, rol: "usuario", texto: m, version_n: null, creado_en: "", opciones: [] }]);
    try {
      const r = await api.enviarChat(eid, pid, m);
      setMensajes(await api.chat(eid, pid));
      if (r.version) onCambio();
    } catch (e) {
      // Si se cortó la conexión pero la api terminó, la respuesta está guardada: se enseña en vez del error
      const guardados = await api.chat(eid, pid).catch(() => null);
      const ultimo = guardados?.at(-1), penultimo = guardados?.at(-2);
      if (ultimo?.rol === "editor" && penultimo?.rol === "usuario" && penultimo.texto === m) {
        setMensajes(guardados!);
        if (ultimo.version_n) onCambio();
      } else {
        setError(e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo enviar");
        setTexto(m);
        setMensajes((x) => x.slice(0, -1));    // el mensaje no llegó a guardarse
      }
    } finally { setEnviando(false); }
  };

  return (
    <div className="flex flex-col gap-2.5 text-[13.5px]">
      <div className="flex max-h-[340px] flex-col gap-2 overflow-y-auto">
        {mensajes.length === 0 && (
          <p className="text-tinta-suave">Pide un cambio: «el titular más corto», «menos técnico el cierre», «otra idea en la 4»…</p>
        )}
        {mensajes.map((m, i) => (
          <div key={m.n} className={`flex max-w-[92%] flex-col gap-1.5 ${m.rol === "usuario" ? "self-end" : "self-start"}`}>
            <div className={`rounded-[12px] px-3 py-2 leading-snug ${m.rol === "usuario" ? "bg-tinta text-papel" : "border border-borde bg-panel"}`}>
              {m.texto}
              {m.version_n && <span className="dato mt-1 block text-carmesi">→ versión {m.version_n}</span>}
            </div>
            {/* Las opciones del editor, como botones: solo las del último mensaje, y no mientras trabaja */}
            {m.rol === "editor" && i === mensajes.length - 1 && !enviando && m.opciones.length > 0 && (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Respuestas rápidas">
                {m.opciones.map((o) => (
                  <button key={o} onClick={() => enviar(o)}
                          className="rounded-full border border-carmesi px-3 py-1 text-left text-[12.5px] text-carmesi hover:bg-carmesi hover:text-papel">
                    {o}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {enviando && <p className="dato self-start">El editor está trabajando… {segundos} s{segundos > 45 ? " · los cambios de imagen tardan un par de minutos" : ""}</p>}
        <div ref={final} />
      </div>
      <div className="flex gap-2">
        <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} disabled={enviando}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
                  placeholder="Escribe al editor… (Intro para enviar)"
                  className="min-w-0 flex-1 resize-none rounded-[12px] border border-borde bg-panel p-2.5 text-[13.5px] outline-none focus:border-tinta" />
        <button onClick={() => enviar()} disabled={enviando || !texto.trim()} className="boton self-end">→</button>
      </div>
      {error && <p className="text-carmesi">{error}</p>}
      <MaterialesChat eid={eid} pid={pid} />
    </div>
  );
}
