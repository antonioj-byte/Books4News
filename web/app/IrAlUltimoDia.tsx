"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LanzarEjecucion } from "@/components/LanzarEjecucion";
import { Portadas } from "@/components/Portadas";
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
  if (!vacio) return <p className="dato p-6">{mensaje}</p>;
  return (
    <div className="mx-auto grid max-w-5xl items-center gap-12 px-6 py-16 md:grid-cols-[1fr_auto]">
      <div>
        <div className="antetitulo">Te chivamos dos —</div>
        <h1 className="titular mt-3 text-[56px]">¿Qué leemos hoy? <em>Te lo chivamos.</em></h1>
        <p className="mt-5 max-w-lg text-[17px] leading-relaxed">
          Aún no hay ninguna ejecución. Lánzala y en unos minutos tienes las piezas del día:{" "}
          <span className="subrayado">una noticia, un libro</span> y una idea que no tenías.
        </p>
        <div className="mt-7"><LanzarEjecucion alTerminar={ir} /></div>
      </div>
      <Portadas />
    </div>
  );
}
