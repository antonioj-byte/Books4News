import { Suspense } from "react";
import { VistaDia } from "./VistaDia";

export default function PaginaDia() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaDia />
    </Suspense>
  );
}
