"use client";

import { useEffect, useState } from "react";
import { api, type EstadoEjecucion } from "@/lib/api";

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
    if (!confirm("Se lanza el pipeline completo del día: unos 10 minutos y alrededor de 1 $. ¿Seguimos?")) return;
    setError("");
    try { setEstado(await api.lanzarEjecucion()); }
    catch (e) { setError(String(e).includes("409") ? "Ya hay una ejecución en marcha." : "No se pudo lanzar."); }
  };

  return (
    <div className="flex flex-col items-end gap-1 text-sm">
      <button onClick={lanzar} disabled={estado?.en_marcha}
              className="rounded-sm border border-tinta px-3 py-1 hover:bg-tinta hover:text-papel disabled:opacity-50">
        {estado?.en_marcha ? "Ejecución en marcha…" : "Lanzar ejecución del día"}
      </button>
      {estado?.en_marcha && estado.ultimas_lineas.length > 0 && (
        <span className="max-w-[420px] truncate text-[12px] text-tinta-suave">{estado.ultimas_lineas.at(-1)}</span>
      )}
      {!estado?.en_marcha && estado?.codigo != null && estado.codigo !== 0 && (
        <details className="max-w-[420px] text-[12px] text-acento">
          <summary>La última ejecución falló (código {estado.codigo})</summary>
          <pre className="whitespace-pre-wrap">{estado.ultimas_lineas.join("\n")}</pre>
        </details>
      )}
      {error && <span className="text-acento">{error}</span>}
    </div>
  );
}
