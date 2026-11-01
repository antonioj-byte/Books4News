import { Suspense } from "react";
import { VistaGasto } from "./VistaGasto";

export default function PaginaGasto() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaGasto />
    </Suspense>
  );
}
