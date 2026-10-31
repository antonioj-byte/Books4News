"use client";

import { useState } from "react";
import { api } from "@/lib/api";

// «Proceder»: escribe una propuesta pendiente de la mesa (guion, hechos, arte, PNG y vídeo). Tarda unos
// minutos; mientras, enseña la etapa en curso y, al terminar, avisa con `onHecho` para recargar.
export function Proceder({ eid, pid, onHecho, texto = "Proceder" }: {
  eid: number; pid: string; onHecho: () => void; texto?: string;
}) {
  const [etapa, setEtapa] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lanzar = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setError(null);
    try {
      await api.desarrollar(eid, pid);
    } catch (err) {
      setError(err instanceof Error && err.message.includes("409") ? "Hay otra ejecución en marcha: prueba cuando termine." : "No se pudo lanzar.");
      return;
    }
    setEtapa("Empezando…");
    const vigilar = async () => {
      const estado = await api.ejecucionEnMarcha().catch(() => null);
      if (estado?.en_marcha) {
        setEtapa(estado.etapa ?? "Trabajando…");
        setTimeout(vigilar, 4000);
        return;
      }
      setEtapa(null);
      if (estado && estado.codigo !== 0) setError(estado.ultimas_lineas.at(-1) ?? "No se pudo escribir la pieza.");
      onHecho();
    };
    setTimeout(vigilar, 3000);
  };

  return (
    <span className="flex flex-col items-start gap-1">
      <button onClick={lanzar} disabled={etapa !== null} className="boton">
        {etapa ? "Escribiendo…" : `${texto} →`}
      </button>
      {etapa && <span className="dato">{etapa} · unos minutos</span>}
      {error && <span className="text-[13px] text-carmesi">{error}</span>}
    </span>
  );
}
