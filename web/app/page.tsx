import { Suspense } from "react";
import { IrAlUltimoDia } from "./IrAlUltimoDia";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function Inicio() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <IrAlUltimoDia />
    </Suspense>
  );
}
