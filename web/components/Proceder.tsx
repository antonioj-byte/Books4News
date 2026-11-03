"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { PASOS_PIEZA, Trabajando } from "@/components/Trabajando";

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
    let enganchada = false;
    try {
      await api.desarrollar(eid, pid);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      // Si ya se está escribiendo (se recargó la página a medias), se engancha a ese trabajo en vez de dar error
      if (msg.startsWith("409") && msg.includes("ya se está escribiendo")) enganchada = true;
      else {
        setError(msg.startsWith("409") ? msg.replace(/^\d+ \S+: /, "") + "." : "No se pudo lanzar.");
        return;
      }
    }
    setEtapa(enganchada ? "Siguiendo el trabajo en marcha…" : "Empezando…");
    let avisada = false;
    let fallos = 0;
    const vigilar = async () => {
      // Cada pieza tiene su proceso (2/11): se sigue el suyo, no la ejecución del día
      let estado;
      try {
        estado = await api.desarrollo(eid, pid);
        fallos = 0;
      } catch {
        // Un fallo de red o un reinicio de la API no corta el seguimiento en silencio (revisión general, 2/11)
        if (++fallos < 6) { setTimeout(vigilar, 5000); return; }
        setEtapa(null);
        setError("Se perdió el seguimiento de la pieza. Recarga la página para ver cómo acabó.");
        return;
      }
      // En cuanto la pieza está en la mesa con sus PNG se enseña; los vídeos siguen pintándose detrás (2/11)
      if (estado.en_marcha && estado.etapa?.startsWith("La pieza ya está en la mesa")) {
        if (!avisada) { avisada = true; setEtapa(null); onHecho(); }
        setTimeout(vigilar, 6000);
        return;
      }
      if (estado.en_marcha) {
        setEtapa(estado.etapa ?? "Trabajando…");
        setTimeout(vigilar, 4000);
        return;
      }
      setEtapa(null);
      // Un trabajo cortado por un despliegue llega como código -1 con su motivo
      if (estado.codigo !== 0 && !avisada) setError(estado.ultimas_lineas.at(-1) ?? "No se pudo escribir la pieza.");
      onHecho();
    };
    setTimeout(vigilar, 3000);
  };

  return (
    <span className="flex flex-col items-start gap-1">
      {etapa ? <Trabajando etapa={etapa} pasos={PASOS_PIEZA} /> : (
        <button onClick={lanzar} className="boton">{`${texto} →`}</button>
      )}
      {error && <span className="text-[13px] text-carmesi">{error}</span>}
    </span>
  );
}
