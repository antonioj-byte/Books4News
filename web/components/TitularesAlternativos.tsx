"use client";

import { useState } from "react";
import { api } from "@/lib/api";

// Cinco titulares alternativos de portada (2/11, regla aceptada en la Memoria: la redacción los pedía al chat en cada
// pieza). Se elige uno con un clic: sustituye el titular de la diapositiva 1 y deja el subtítulo como está.
export function TitularesAlternativos({ eid, pid, titulares, subtitulo, actual, onCambio }: {
  eid: number; pid: string; titulares: string[]; subtitulo: string | null | undefined; actual: string; onCambio: () => void;
}) {
  const [usando, setUsando] = useState<string | null>(null);
  const [error, setError] = useState("");
  if (!titulares.length) return null;
  const usar = async (t: string) => {
    setUsando(t);
    setError("");
    try {
      await api.editarDiapositiva(eid, pid, 1, t, subtitulo ?? null);
      onCambio();
    } catch (e) {
      setError(String(e));
    } finally {
      setUsando(null);
    }
  };
  return (
    <div className="flex w-full max-w-[440px] flex-col gap-1.5 text-[13px]">
      <span className="dato">Titulares alternativos</span>
      {titulares.map((t) => (
        <div key={t} className="flex items-center justify-between gap-2 rounded-[10px] border border-borde bg-panel px-3 py-2">
          <span>{t}</span>
          {t === actual
            ? <span className="dato whitespace-nowrap">en uso</span>
            : <button className="boton-suave whitespace-nowrap" disabled={!!usando} onClick={() => usar(t)}>{usando === t ? "…" : "Usar"}</button>}
        </div>
      ))}
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}
