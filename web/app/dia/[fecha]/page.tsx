import { Suspense } from "react";
import { VistaDia } from "./VistaDia";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaDia() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaDia />
    </Suspense>
  );
}
