import { Suspense } from "react";
import { VistaEquipo } from "./VistaEquipo";

export default function Pagina() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaEquipo />
    </Suspense>
  );
}
