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

  return (
    <div className="flex flex-col gap-3 text-[13px]">
      {CRITERIOS.map((c) => (
        <div key={c.clave}>
          <div className="flex items-baseline justify-between">
            <span className="font-semibold">{c.texto}</span>
            <span className="text-[11px] text-tinta-suave">{c.ayuda}</span>
          </div>
          <div className="mt-1 grid grid-cols-5 gap-1">
            {[1, 2, 3, 4, 5].map((v) => (
              <button key={v} onClick={() => cambiar({ [c.clave]: ev[c.clave] === v ? null : v })}
                      className={`h-8 rounded-sm border border-tinta font-texto text-[15px] ${ev[c.clave] === v ? "bg-tinta text-papel" : "hover:bg-[#e6e0d4]"}`}>
                {v}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div>
        <span className="font-semibold">¿La publicarías?</span>
        <div className="mt-1 grid grid-cols-2 gap-1">
          {[{ v: true, t: "Sí" }, { v: false, t: "No" }].map((o) => (
            <button key={o.t} onClick={() => cambiar({ publicaria: ev.publicaria === o.v ? null : o.v })}
                    className={`h-8 rounded-sm border border-tinta ${ev.publicaria === o.v ? (o.v ? "bg-[#3d5a33] text-papel border-[#3d5a33]" : "bg-acento text-papel border-acento") : "hover:bg-[#e6e0d4]"}`}>
              {o.t}
            </button>
          ))}
        </div>
      </div>
      <label className="flex flex-col gap-1">
        <span className="font-semibold">Comentario</span>
        <textarea value={ev.comentario} onChange={(e) => cambiar({ comentario: e.target.value })} rows={4}
                  className="rounded-sm border border-tinta bg-[#faf8f3] p-2 font-texto text-[14px]" />
      </label>
      <button onClick={guardar} disabled={estado === "guardando"}
              className="h-9 rounded-sm bg-tinta font-semibold text-papel hover:bg-acento disabled:opacity-50">
        {estado === "guardando" ? "Guardando…" : estado === "guardada" ? "Guardada ✓" : "Guardar evaluación"}
      </button>
      {estado === "error" && <p className="text-acento">No se pudo guardar. ¿Está la API en marcha?</p>}
    </div>
  );
}
