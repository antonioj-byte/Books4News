import type { ReactNode } from "react";

// Una sola forma para todo lo que está por elegir en «Hoy» (7/11, a petición del usuario: «muy feo… homologuemos
// esto»): propuestas del día, breves del radar, encargos de la redacción y «Cinco del libro». Arriba, las etiquetas;
// el titular; una línea de por qué; lo de debajo (el libro, los enlaces, la conversación); y las acciones a la derecha.
export function TarjetaPorElegir({ etiquetas, titulo, linea, children, acciones }: {
  etiquetas: ReactNode; titulo: ReactNode; linea?: ReactNode; children?: ReactNode; acciones?: ReactNode;
}) {
  return (
    <article className="panel grid gap-x-5 gap-y-2 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">{etiquetas}</div>
        <div className="titular text-[21px] leading-snug">{titulo}</div>
        {linea && <p className="max-w-[70ch] font-titular text-[15.5px] italic leading-snug text-tinta-suave" style={{ fontWeight: 400 }}>{linea}</p>}
        {children}
      </div>
      {acciones && <div className="flex flex-col items-stretch gap-1.5 sm:w-[190px]">{acciones}</div>}
    </article>
  );
}
