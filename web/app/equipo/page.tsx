import { Suspense } from "react";
import { VistaEquipo } from "./VistaEquipo";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function Pagina() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaEquipo />
    </Suspense>
  );
}
