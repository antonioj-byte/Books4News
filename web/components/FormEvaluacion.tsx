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
    <div className="flex flex-col gap-4 text-[13.5px]">
      {CRITERIOS.map((c) => (
        <div key={c.clave}>
          <div className="flex items-baseline justify-between">
            <span className="font-semibold">{c.texto}</span>
            <span className="dato">{c.ayuda}</span>
          </div>
          <div className="mt-1.5 grid grid-cols-5 gap-1.5">
            {[1, 2, 3, 4, 5].map((v) => (
              <button key={v} onClick={() => cambiar({ [c.clave]: ev[c.clave] === v ? null : v })}
                      aria-pressed={ev[c.clave] === v}
                      className={`h-9 rounded-full border font-titular text-[16px] font-semibold transition ${ev[c.clave] === v ? "border-tinta bg-tinta text-papel" : "border-borde bg-panel hover:border-tinta"}`}>
                {v}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div>
        <span className="font-semibold">¿La publicarías?</span>
        <div className="mt-1.5 grid grid-cols-2 gap-1.5">
          {[{ v: true, t: "Sí" }, { v: false, t: "No" }].map((o) => (
            <button key={o.t} onClick={() => cambiar({ publicaria: ev.publicaria === o.v ? null : o.v })}
                    aria-pressed={ev.publicaria === o.v}
                    className={`h-9 rounded-full border font-semibold transition ${ev.publicaria === o.v ? (o.v ? "border-verde bg-verde text-papel" : "border-carmesi bg-carmesi text-papel") : "border-borde bg-panel hover:border-tinta"}`}>
              {o.t}
            </button>
          ))}
        </div>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="font-semibold">Comentario</span>
        <textarea value={ev.comentario} onChange={(e) => cambiar({ comentario: e.target.value })} rows={4}
                  placeholder="Lo que te chirría, lo que te ha gustado…"
                  className="rounded-[14px] border border-borde bg-panel p-3 text-[14px] outline-none focus:border-tinta" />
      </label>
      <button onClick={guardar} disabled={estado === "guardando"} className="boton justify-center">
        {estado === "guardando" ? "Guardando…" : estado === "guardada" ? "Guardada ✓" : "Guardar evaluación →"}
      </button>
      {estado === "error" && <p className="text-carmesi">No se pudo guardar. ¿Está la API en marcha?</p>}
    </div>
  );
}
