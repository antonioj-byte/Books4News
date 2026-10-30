"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LanzarEjecucion } from "@/components/LanzarEjecucion";
import { api } from "@/lib/api";

export function IrAlUltimoDia() {
  const router = useRouter();
  const [mensaje, setMensaje] = useState("Cargando el último día…");
  const [vacio, setVacio] = useState(false);
  const ir = useCallback(() => {
    api.dias()
      .then((dias) => {
        if (dias.length) router.replace(`/dia/${dias[0].fecha}`);
        else { setVacio(true); setMensaje("Aún no hay ninguna ejecución. Lanza la del día para empezar."); }
      })
      .catch(() => setMensaje("No responde la API. Arráncala con `uv run folio web`."));
  }, [router]);
  useEffect(ir, [ir]);
  return (
    <div className="mx-auto flex max-w-xl flex-col items-start gap-4 px-6 py-10">
      <p className="text-tinta-suave">{mensaje}</p>
      {vacio && <LanzarEjecucion alTerminar={ir} />}
    </div>
  );
}
