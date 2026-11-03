import { Suspense } from "react";
import { VistaMarca } from "./VistaMarca";

export default function Pagina() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaMarca />
    </Suspense>
  );
}
