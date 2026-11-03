import { Suspense } from "react";
import { VistaRol } from "./VistaRol";

export default function Pagina() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaRol />
    </Suspense>
  );
}
