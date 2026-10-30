import { Suspense } from "react";
import { IrAlUltimoDia } from "./IrAlUltimoDia";

export default function Inicio() {
  return (
    <Suspense fallback={<p className="p-6">Cargando…</p>}>
      <IrAlUltimoDia />
    </Suspense>
  );
}
