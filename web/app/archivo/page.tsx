import { Suspense } from "react";
import { VistaArchivo } from "./VistaArchivo";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function Pagina() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaArchivo />
    </Suspense>
  );
}
