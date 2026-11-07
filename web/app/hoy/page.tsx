import { Suspense } from "react";
import { IrAlUltimoDia } from "../IrAlUltimoDia";
import { EsqueletoPagina } from "@/components/Esqueleto";

// «Hoy» en el menú (7/11): la mesa del último día (antes era la página de inicio)
export default function Hoy() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <IrAlUltimoDia />
    </Suspense>
  );
}
