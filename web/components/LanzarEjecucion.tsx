"use client";

import { useEffect, useState } from "react";
import { api, type EstadoEjecucion } from "@/lib/api";
import { fraseDeFallo, mensajeError } from "@/lib/errores";
import { mirarTrabajos } from "@/lib/trabajos";
import { FalloTrabajo, Trabajando } from "@/components/Trabajando";

// «Lanzar la ejecución del día»: corre el pipeline completo en el servidor (~1 $) y enseña su progreso con la tarjeta
// de trabajo (reloj real y lo que suele tardar). Cuesta dinero, así que se confirma en la página (4/11, usabilidad:
// antes era un `confirm()` del navegador). Al terminar avisa para recargar la portada.
export function LanzarEjecucion({ alTerminar }: { alTerminar: () => void }) {
  const [estado, setEstado] = useState<EstadoEjecucion | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let vivo = true;
    let anterior = false;
    const mirar = () => api.ejecucionEnMarcha().then((e) => {
      if (!vivo) return;
      if (anterior && !e.en_marcha) alTerminar();
      anterior = e.en_marcha;
      setEstado(e);
    }).catch(() => {});
    mirar();
    const t = setInterval(mirar, 5000);
    return () => { vivo = false; clearInterval(t); };
  }, [alTerminar]);

  const lanzar = async () => {
    setError(""); setConfirmando(false);
    try { setEstado(await api.lanzarEjecucion()); mirarTrabajos(); }
    catch (e) { setError(mensajeError(e, "No se pudo lanzar.")); }
  };
  const minutos = Math.round((estado?.tipico_s ?? 300) / 60);

  return (
    <div className="flex flex-col items-start gap-2 text-sm">
      {estado?.en_marcha ? (
        <Trabajando etapa={estado.etapa ?? "Arrancando…"} rotulo="Ejecución del día" inicio={estado.inicio} tipico={estado.tipico_s} />
      ) : confirmando ? (
        <div className="flex flex-col items-start gap-2 rounded-[12px] border border-borde bg-panel p-3" role="group" aria-label="Confirmar">
          <p>Se lanza el pipeline completo del día: unos {minutos} minutos y alrededor de 1 $. Rehace la mesa de hoy.</p>
          <div className="flex gap-2">
            <button onClick={lanzar} className="boton">Sí, lanzarla</button>
            <button onClick={() => setConfirmando(false)} className="boton-suave">Cancelar</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setConfirmando(true)} className="boton">
          Lanzar la ejecución del día →<span className="boton__coste">~{minutos} min · ~1 $</span>
        </button>
      )}
      {!estado?.en_marcha && estado?.codigo != null && estado.codigo !== 0 && (
        <FalloTrabajo fallo={{ ...fraseDeFallo(estado.ultimas_lineas, "La última ejecución falló."),
                               titulo: `La última ejecución falló${estado.etapa ? ` en «${estado.etapa}»` : ""}: ${fraseDeFallo(estado.ultimas_lineas, "").titulo || "mira los detalles."}` }} />
      )}
      {error && <span className="text-carmesi" role="alert">{error}</span>}
    </div>
  );
}
