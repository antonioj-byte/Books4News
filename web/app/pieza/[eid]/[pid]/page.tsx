import { Suspense } from "react";
import { VistaPieza } from "./VistaPieza";

export default function PaginaPieza() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <VistaPieza />
    </Suspense>
  );
}
