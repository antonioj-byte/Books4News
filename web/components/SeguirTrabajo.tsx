"use client";

import { api, type EstadoTrabajo } from "@/lib/api";
import { useTrabajo } from "@/lib/useTrabajo";
import { FalloTrabajo, type Paso, Trabajando } from "@/components/Trabajando";

// Seguir un trabajo aparte por su clave (4/11, usabilidad: «nada atado a la página»). Lo usan los temas, las réplicas
// al jefe y lo que se lleva del fondo a la mesa: se engancha al montar si está en marcha (también después de recargar o
// de volver a la mesa), enseña la tarjeta de trabajo y, al acabar, entrega el resultado.
export function SeguirTrabajo({ clave, pasos, rotulo, onHecho, siFalla }: {
  clave: string; pasos?: Paso[]; rotulo: string; siFalla?: string;
  onHecho: (resultado: Record<string, unknown> | null, estado: EstadoTrabajo) => void;
}) {
  const t = useTrabajo({
    consultar: () => api.trabajo(clave).catch((e) => {
      if (e instanceof Error && e.message.startsWith("404")) return null;
      throw e;
    }),
    lanzar: async () => {},
    onHecho: (e) => onHecho((e as EstadoTrabajo).resultado ?? null, e as EstadoTrabajo),
    siFalla,
  });
  if (t.enMarcha) return <Trabajando etapa={t.estado?.etapa ?? "Empezando…"} pasos={pasos} rotulo={rotulo} inicio={t.estado?.inicio} tipico={t.estado?.tipico_s} />;
  if (t.error) return <FalloTrabajo fallo={t.error} />;
  return null;
}
