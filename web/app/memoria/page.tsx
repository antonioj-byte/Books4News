import { Suspense } from "react";
import { VistaMemoria } from "./VistaMemoria";

export default function PaginaMemoria() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaMemoria />
    </Suspense>
  );
}
