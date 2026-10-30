import { Suspense } from "react";
import { VistaEvaluacion } from "./VistaEvaluacion";

export default function PaginaEvaluacion() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaEvaluacion />
    </Suspense>
  );
}
