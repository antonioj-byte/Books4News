import { Suspense } from "react";
import { VistaPieza } from "./VistaPieza";
import { EsqueletoPagina } from "@/components/Esqueleto";

export default function PaginaPieza() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <VistaPieza />
    </Suspense>
  );
}
