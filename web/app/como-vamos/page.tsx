import { Suspense } from "react";
import { VistaComoVamos } from "./VistaComoVamos";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaComoVamos() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaComoVamos />
    </Suspense>
  );
}
