"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { mensajeError } from "@/lib/errores";

// Descargar el carrusel (.zip): la API lo pinta en el momento y tarda hasta un minuto. Antes era un enlace sin ninguna
// señal y se acababa pulsando varias veces (4/11, usabilidad); ahora se ve que se está preparando y, si falla, por qué.
export function DescargarZip({ eid, pid }: { eid: number; pid: string }) {
  const [fase, setFase] = useState<"" | "preparando" | "hecho">("");
  const [error, setError] = useState("");
  const descargar = async () => {
    if (fase === "preparando") return;
    setFase("preparando"); setError("");
    try {
      const r = await fetch(api.urlDescarga(eid, pid), { cache: "no-store" });
      if (!r.ok) {
        let detalle = "";
        try { detalle = (await r.json()).detail ?? ""; } catch { /* sin JSON */ }
        throw new Error(`${r.status} descarga: ${detalle}`);
      }
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = `${pid}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      setFase("hecho"); setTimeout(() => setFase(""), 2500);
    } catch (e) {
      setFase(""); setError(mensajeError(e, "No se pudo preparar el .zip."));
    }
  };
  return (
    <span className="flex flex-col items-start gap-1">
      <button onClick={descargar} aria-busy={fase === "preparando" || undefined} className="text-left hover:underline">
        {fase === "preparando" ? <span className="inline-flex items-center gap-2"><span className="girando" aria-hidden />Preparando el .zip (hasta un minuto)…</span>
          : fase === "hecho" ? "✓ Descargado"
          : <>Descargar el carrusel (.zip) <span className="dato">· hasta un minuto</span></>}
      </button>
      {error && <span className="text-carmesi" role="alert">{error}</span>}
    </span>
  );
}
