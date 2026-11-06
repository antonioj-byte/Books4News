"use client";

import { useRef } from "react";
import { api } from "@/lib/api";
import { useTrabajo } from "@/lib/useTrabajo";
import { FalloTrabajo, PASOS_PIEZA, Trabajando } from "@/components/Trabajando";

// «Proceder»: escribe una propuesta pendiente de la mesa (guion, hechos, arte, PNG y vídeo). Tarda unos minutos;
// mientras, la tarjeta de trabajo con el paso en curso, el reloj real y lo que suele tardar. Si se recarga la página a
// mitad, se engancha al trabajo en marcha (4/11, usabilidad: antes volvía a salir el botón como si nada).
export function Proceder({ eid, pid, onHecho, texto = "Proceder" }: {
  eid: number; pid: string; onHecho: () => void; texto?: string;
}) {
  const avisada = useRef(false);
  const t = useTrabajo({
    consultar: () => api.desarrollo(eid, pid).catch((e) => {
      if (e instanceof Error && e.message.startsWith("404")) return null;      // nunca se lanzó
      throw e;
    }),
    lanzar: () => { avisada.current = false; return api.desarrollar(eid, pid); },
    // En cuanto la pieza está en la mesa con sus PNG se enseña; los vídeos siguen pintándose detrás (2/11)
    onProgreso: (e) => {
      if (!avisada.current && e.etapa?.startsWith("La pieza ya está en la mesa")) { avisada.current = true; onHecho(); }
    },
    onHecho: () => { if (!avisada.current) onHecho(); },
    siFalla: "No se pudo escribir la pieza.",
    clave: pid,
  });
  const pintandoVideos = t.estado?.etapa?.startsWith("La pieza ya está en la mesa");

  return (
    <span className="flex flex-col items-start gap-2" onClick={(e) => e.stopPropagation()}>
      {t.enMarcha && !pintandoVideos ? (
        <Trabajando etapa={t.estado?.etapa ?? "Trabajando…"} pasos={PASOS_PIEZA} inicio={t.estado?.inicio} tipico={t.estado?.tipico_s} onCancelar={t.cancelar} />
      ) : t.enMarcha ? (
        <span className="dato">En la mesa · pintando los vídeos<span className="puntos-vivos" aria-hidden /></span>
      ) : (
        <button onClick={(e) => { e.preventDefault(); t.lanzar(); }} className="boton">
          {`${texto} →`}<span className="boton__coste">~{Math.round((t.estado?.tipico_s ?? 150) / 60)} min</span>
        </button>
      )}
      {t.error && !t.enMarcha && <FalloTrabajo fallo={t.error} />}
    </span>
  );
}
