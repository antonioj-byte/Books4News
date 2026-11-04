import { Suspense } from "react";
import { VistaEvaluacion } from "./VistaEvaluacion";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaEvaluacion() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaEvaluacion />
    </Suspense>
  );
}
