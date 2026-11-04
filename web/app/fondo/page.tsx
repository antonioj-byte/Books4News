import { Suspense } from "react";
import { VistaFondo } from "./VistaFondo";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaFondo() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaFondo />
    </Suspense>
  );
}
