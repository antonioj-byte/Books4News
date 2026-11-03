"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PASOS_CINCO, Trabajando } from "@/components/Trabajando";

// «Cinco del libro» a mano (3/11): solo esa pieza, sobre las noticias que ya leyó la ejecución del día, sin rehacer la
// mesa. Lanza `folio cinco` en un proceso aparte y lo sigue como «Proceder»; al acabar, recarga la mesa.
export function CincoDelLibro({ fecha, onHecho }: { fecha: string; onHecho: () => void }) {
  const [etapa, setEtapa] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const vigilar = () => {
    let fallos = 0;
    const paso = async () => {
      let e;
      try { e = await api.estadoCinco(); fallos = 0; } catch {
        if (++fallos < 6) { setTimeout(paso, 5000); return; }
        setEtapa(null); setError("Se perdió el seguimiento. Recarga la página para ver cómo acabó."); return;
      }
      if (e.en_marcha) { setEtapa(e.etapa ?? "Trabajando…"); setTimeout(paso, 4000); return; }
      setEtapa(null);
      if (e.codigo !== 0) setError(e.ultimas_lineas.at(-1) ?? "No se pudo escribir «Cinco del libro».");
      onHecho();
    };
    setTimeout(paso, 3000);
  };

  // Si ya se está escribiendo (se recargó la página), se engancha
  useEffect(() => {
    api.estadoCinco().then((e) => { if (e.en_marcha) { setEtapa(e.etapa ?? "Trabajando…"); vigilar(); } }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lanzar = async () => {
    setError(null);
    try { await api.lanzarCinco(fecha); } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^\d+ \S+: /, "") : "No se pudo lanzar."); return;
    }
    setEtapa("Empezando…");
    vigilar();
  };

  return (
    <div className="mt-10 flex flex-col items-start gap-1.5 rounded-[12px] border border-borde bg-panel p-5">
      <div className="antetitulo">Cinco del libro</div>
      <p className="text-[14px] text-tinta-suave">Las cinco noticias del mundo del libro de hoy, cada una con su ilustración. Se hace sobre las noticias que ya leyó la madrugada, sin rehacer la mesa (unos 5 minutos).</p>
      {etapa ? <Trabajando etapa={etapa} pasos={PASOS_CINCO} /> : (
        <button className="boton" onClick={lanzar}>Escribir «Cinco del libro» →</button>
      )}
      {error && <span className="text-[13px] text-carmesi">{error}</span>}
    </div>
  );
}
