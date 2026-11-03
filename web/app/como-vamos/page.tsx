import { Suspense } from "react";
import { VistaComoVamos } from "./VistaComoVamos";

export default function PaginaComoVamos() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaComoVamos />
    </Suspense>
  );
}
