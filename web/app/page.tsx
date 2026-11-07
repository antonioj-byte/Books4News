import { Suspense } from "react";
import { Portada } from "./Portada";
import { EsqueletoPagina } from "@/components/Esqueleto";

// La portada de Folio (7/11): el panel general; «Hoy» lleva a la mesa del último día
export default function Inicio() {
  return (
    <Suspense fallback={<EsqueletoPagina />}>
      <Portada />
    </Suspense>
  );
}
