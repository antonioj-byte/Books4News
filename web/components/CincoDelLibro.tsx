"use client";

import { api } from "@/lib/api";
import { useTrabajo } from "@/lib/useTrabajo";
import { FalloTrabajo, PASOS_CINCO, Trabajando } from "@/components/Trabajando";

// «Cinco del libro» a mano (3/11): solo esa pieza, sobre las noticias que ya leyó la ejecución del día, sin rehacer la
// mesa. Lanza `folio cinco` en un proceso aparte y lo sigue con la tarjeta de trabajo; al acabar, recarga la mesa.
export function CincoDelLibro({ fecha, onHecho }: { fecha: string; onHecho: () => void }) {
  const t = useTrabajo({
    consultar: () => api.estadoCinco(),
    lanzar: () => api.lanzarCinco(fecha),
    onHecho: () => onHecho(),
    siFalla: "No se pudo escribir «Cinco del libro».",
  });
  return (
    <div className="mt-10 flex flex-col items-start gap-2 rounded-[12px] border border-borde bg-panel p-5">
      <div className="antetitulo">Cinco del libro</div>
      <p className="text-[14px] text-tinta-suave">Las cinco noticias del mundo del libro de hoy, cada una con su ilustración. Se hace sobre las noticias que ya leyó la madrugada, sin rehacer la mesa.</p>
      {t.enMarcha
        ? <Trabajando etapa={t.estado?.etapa ?? "Trabajando…"} pasos={PASOS_CINCO} inicio={t.estado?.inicio} tipico={t.estado?.tipico_s} />
        : <button className="boton" onClick={t.lanzar}>Escribir «Cinco del libro» →<span className="boton__coste">~{Math.round((t.estado?.tipico_s ?? 300) / 60)} min · ~0,20 $</span></button>}
      {t.error && !t.enMarcha && <FalloTrabajo fallo={t.error} reintentar={t.lanzar} />}
    </div>
  );
}
