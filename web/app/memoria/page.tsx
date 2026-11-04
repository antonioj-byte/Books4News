import { Suspense } from "react";
import { VistaMemoria } from "./VistaMemoria";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaMemoria() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaMemoria />
    </Suspense>
  );
}
