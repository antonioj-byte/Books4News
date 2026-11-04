import { Suspense } from "react";
import { VistaGasto } from "./VistaGasto";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaGasto() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaGasto />
    </Suspense>
  );
}
