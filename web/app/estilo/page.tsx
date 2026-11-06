import { Suspense } from "react";
import { VistaEstilo } from "./VistaEstilo";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function Pagina() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaEstilo />
    </Suspense>
  );
}
