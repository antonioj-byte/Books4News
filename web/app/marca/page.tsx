import { Suspense } from "react";
import { VistaMarca } from "./VistaMarca";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function Pagina() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaMarca />
    </Suspense>
  );
}
