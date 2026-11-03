"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { VistaEvaluacion } from "@/app/evaluacion/VistaEvaluacion";
import { VistaGasto } from "@/app/gasto/VistaGasto";
import { VistaMemoria } from "@/app/memoria/VistaMemoria";

const PESTANAS = [
  { clave: "evaluacion", texto: "Evaluación" },
  { clave: "memoria", texto: "Memoria" },
  { clave: "gasto", texto: "Gasto" },
] as const;

// «Cómo vamos» (3/11, «se está volviendo demasiado compleja la web»): evaluación, memoria y gasto, que se miran de vez
// en cuando y no cada día, en una sola página con tres pestañas en vez de tres entradas del menú.
export function VistaComoVamos() {
  const router = useRouter();
  const busqueda = useSearchParams();
  const actual = PESTANAS.find((p) => p.clave === busqueda.get("ver"))?.clave ?? "evaluacion";
  return (
    <div>
      <nav className="mx-auto flex max-w-5xl gap-1.5 px-4 pt-6 sm:px-6" aria-label="Cómo vamos">
        {PESTANAS.map((p) => (
          <button key={p.clave} aria-pressed={actual === p.clave} onClick={() => router.replace(`/como-vamos?ver=${p.clave}`)}
                  className={`rounded-full px-4 py-1.5 text-sm ${actual === p.clave ? "bg-tinta text-papel" : "bg-papel-hondo hover:bg-borde"}`}>
            {p.texto}
          </button>
        ))}
      </nav>
      {actual === "evaluacion" && <VistaEvaluacion />}
      {actual === "memoria" && <VistaMemoria />}
      {actual === "gasto" && <VistaGasto />}
    </div>
  );
}
