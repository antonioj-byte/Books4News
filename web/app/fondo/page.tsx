import { Suspense } from "react";
import { VistaFondo } from "./VistaFondo";

export default function PaginaFondo() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaFondo />
    </Suspense>
  );
}
