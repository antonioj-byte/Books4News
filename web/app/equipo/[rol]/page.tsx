import { Suspense } from "react";
import { VistaRol } from "./VistaRol";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function Pagina() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaRol />
    </Suspense>
  );
}
