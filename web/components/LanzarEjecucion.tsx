"use client";

import { useEffect, useState } from "react";
import { api, type EstadoEjecucion } from "@/lib/api";

function minutos(inicio: string): string {
  const s = Math.max(0, Math.round((Date.now() - new Date(inicio).getTime()) / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

// Botón «Lanzar ejecución del día»: corre el pipeline completo en el servidor (~1 $) y muestra
// su progreso. Al terminar avisa para recargar la portada.
export function LanzarEjecucion({ alTerminar }: { alTerminar: () => void }) {
  const [estado, setEstado] = useState<EstadoEjecucion | null>(null);
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
    if (!confirm("Se lanza el pipeline completo del día: unos 5 minutos y alrededor de 1 $. ¿Seguimos?")) return;
    setError("");
    try { setEstado(await api.lanzarEjecucion()); }
    catch (e) { setError(String(e).includes("409") ? "Ya hay una ejecución en marcha." : "No se pudo lanzar."); }
  };

  return (
    <div className="flex flex-col items-start gap-2 text-sm">
      <button onClick={lanzar} disabled={estado?.en_marcha} className="boton">
        {estado?.en_marcha ? "Ejecución en marcha…" : "Lanzar la ejecución del día →"}
      </button>
      {estado?.en_marcha && (
        <span className="dato flex items-center gap-2">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-carmesi" />
          {estado.etapa ?? "Arrancando…"}
          {estado.inicio && <> · {minutos(estado.inicio)}</>}
        </span>
      )}
      {!estado?.en_marcha && estado?.codigo != null && estado.codigo !== 0 && (
        <details className="max-w-[560px] rounded-[14px] border border-carmesi/40 bg-panel px-3 py-2 text-[12px]">
          <summary className="cursor-pointer text-carmesi">
            La última ejecución falló{estado.etapa ? ` en «${estado.etapa}»` : ""} (código {estado.codigo})
          </summary>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-tinta-suave">{estado.ultimas_lineas.join("\n")}</pre>
        </details>
      )}
      {error && <span className="text-carmesi">{error}</span>}
    </div>
  );
}
