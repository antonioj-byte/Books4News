import { Suspense } from "react";
import { VistaArchivo } from "./VistaArchivo";

export default function Pagina() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaArchivo />
    </Suspense>
  );
}
