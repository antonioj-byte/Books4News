import type { PiezaResumen } from "@/lib/api";

type Marcas = PiezaResumen["marcas"];

// Avisos de una pieza: carmesí lo grave (hechos sin comprobar, fallos), subrayador lo que hay que mirar.
export function Marcas({ marcas, avisoJefe }: { marcas: Marcas; avisoJefe?: boolean }) {
  const lista: { texto: string; grave: boolean }[] = [];
  if (marcas.error) lista.push({ texto: "Fallida", grave: true });
  if (marcas.hechos_no_verificados) {
    const n = marcas.hechos_no_verificados;
    lista.push({ texto: `${n} hecho${n > 1 ? "s" : ""} sin comprobar`, grave: true });
  }
  if (marcas.revisar_edicion) lista.push({ texto: "Revisar edición", grave: false });
  if (marcas.revision_humana) lista.push({ texto: "«Sin traducir»: mirar", grave: false });
  if (avisoJefe) lista.push({ texto: "Aviso del jefe", grave: false });
  if (!lista.length) return <span className="chip bg-verde/10 text-verde">✓ Sin avisos</span>;
  return (
    <span className="flex flex-wrap gap-1.5">
      {lista.map((m) => (
        <span key={m.texto} className={`chip ${m.grave ? "bg-carmesi text-papel" : "bg-subrayador text-tinta"}`}>{m.texto}</span>
      ))}
    </span>
  );
}

const ESTADOS: Record<string, { texto: string; clase: string }> = {
  propuesta: { texto: "Propuesta", clase: "border border-borde text-tinta-suave" },
  en_edicion: { texto: "En edición", clase: "bg-subrayador text-tinta" },
  aprobada: { texto: "Aprobada", clase: "bg-verde text-papel" },
  descartada: { texto: "Descartada", clase: "bg-papel-hondo text-tinta-suave line-through" },
  fallida: { texto: "Fallida", clase: "border border-carmesi text-carmesi" },
  publicada: { texto: "Publicada", clase: "bg-tinta text-papel" },
};

export function EstadoChip({ estado }: { estado: string }) {
  const e = ESTADOS[estado] ?? { texto: estado, clase: "border border-borde" };
  return <span className={`chip ${e.clase}`}>{e.texto}</span>;
}
