"use client";

import { useState } from "react";
import { api, type Evaluacion } from "@/lib/api";

const CRITERIOS: { clave: "seleccion" | "libro" | "idea" | "voz"; texto: string; ayuda: string }[] = [
  { clave: "seleccion", texto: "Selección", ayuda: "¿Era la historia?" },
  { clave: "libro", texto: "Libro", ayuda: "¿Es el libro para leerla?" },
  { clave: "idea", texto: "Idea nueva", ayuda: "¿Aporta algo que no tenía?" },
  { clave: "voz", texto: "Voz", ayuda: "¿Suena a Folio?" },
];

const VACIA: Evaluacion = { seleccion: null, libro: null, idea: null, voz: null, publicaria: null, comentario: "" };

// Formulario de evaluación: se guarda en la base de datos y en el bloque de informe.md.
// Quien lo usa le da una `key` por pieza, para que cambiar de pieza lo reinicie.
export function FormEvaluacion({ eid, pid, inicial, onGuardada }: {
  eid: number; pid: string; inicial: Evaluacion | null; onGuardada?: () => void;
}) {
  const [ev, setEv] = useState<Evaluacion>(inicial ?? VACIA);
  const [estado, setEstado] = useState<"" | "guardando" | "guardada" | "error">(inicial ? "guardada" : "");

  const cambiar = (c: Partial<Evaluacion>) => { setEv((x) => ({ ...x, ...c })); setEstado(""); };
  const guardar = async () => {
    setEstado("guardando");
    try { await api.guardarEvaluacion(eid, pid, ev); setEstado("guardada"); onGuardada?.(); }
    catch { setEstado("error"); }
  };

  // Compacta: cada criterio en una línea (nombre y cinco botones pequeños; la pregunta, al pasar por encima)
  return (
    <div className="flex flex-col gap-2 text-[13px]">
      {CRITERIOS.map((c) => (
        <div key={c.clave} className="flex items-center justify-between gap-2" title={c.ayuda}>
          <span className="font-semibold">{c.texto}</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((v) => (
              <button key={v} onClick={() => cambiar({ [c.clave]: ev[c.clave] === v ? null : v })}
                      aria-pressed={ev[c.clave] === v} aria-label={`${c.texto}: ${v}`}
                      className={`h-7 w-7 rounded-full border font-titular text-[13px] font-semibold transition ${ev[c.clave] === v ? "border-tinta bg-tinta text-papel" : "border-borde bg-panel hover:border-tinta"}`}>
                {v}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">¿La publicarías?</span>
        <div className="flex gap-1">
          {[{ v: true, t: "Sí" }, { v: false, t: "No" }].map((o) => (
            <button key={o.t} onClick={() => cambiar({ publicaria: ev.publicaria === o.v ? null : o.v })}
                    aria-pressed={ev.publicaria === o.v}
                    className={`h-7 w-[46px] rounded-full border text-[13px] font-semibold transition ${ev.publicaria === o.v ? (o.v ? "border-verde bg-verde text-papel" : "border-carmesi bg-carmesi text-papel") : "border-borde bg-panel hover:border-tinta"}`}>
              {o.t}
            </button>
          ))}
        </div>
      </div>
      <textarea value={ev.comentario} onChange={(e) => cambiar({ comentario: e.target.value })} rows={2}
                aria-label="Comentario" placeholder="Comentario: lo que chirría, lo que gusta…"
                className="resize-none rounded-[12px] border border-borde bg-panel p-2.5 text-[13px] outline-none focus:border-tinta" />
      <button onClick={guardar} disabled={estado === "guardando"} className="boton justify-center py-1.5">
        {estado === "guardando" ? "Guardando…" : estado === "guardada" ? "Guardada ✓" : "Guardar evaluación →"}
      </button>
      {estado === "error" && <p className="text-carmesi">No se pudo guardar. ¿Está la API en marcha?</p>}
    </div>
  );
}
