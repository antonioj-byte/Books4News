import type { PiezaResumen } from "@/lib/api";

type Marcas = PiezaResumen["marcas"];

const chip = "inline-block rounded-sm px-1.5 py-0.5 text-[11px] font-semibold leading-tight";

export function Marcas({ marcas, avisoJefe }: { marcas: Marcas; avisoJefe?: boolean }) {
  const lista: { texto: string; grave: boolean }[] = [];
  if (marcas.error) lista.push({ texto: "Fallida", grave: true });
  if (marcas.hechos_no_verificados)
    lista.push({ texto: `${marcas.hechos_no_verificados} hecho${marcas.hechos_no_verificados > 1 ? "s" : ""} no verificado${marcas.hechos_no_verificados > 1 ? "s" : ""}`, grave: true });
  if (marcas.revisar_edicion) lista.push({ texto: "Revisar edición", grave: false });
  if (marcas.revision_humana) lista.push({ texto: "«Sin traducir»: revisar", grave: false });
  if (avisoJefe) lista.push({ texto: "Aviso del jefe", grave: false });
  if (!lista.length) return <span className={`${chip} bg-[#e3eadf] text-[#3d5a33]`}>Sin avisos</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {lista.map((m) => (
        <span key={m.texto} className={`${chip} ${m.grave ? "bg-acento text-papel" : "bg-[#f1dfb5] text-[#6b4b0c]"}`}>{m.texto}</span>
      ))}
    </span>
  );
}

export function EstadoChip({ estado }: { estado: string }) {
  const estilos: Record<string, string> = {
    propuesta: "border-tinta-suave text-tinta-suave",
    en_edicion: "border-[#8a6a1f] text-[#8a6a1f]",
    aprobada: "border-[#3d5a33] bg-[#3d5a33] text-papel",
    descartada: "border-tinta-suave text-tinta-suave line-through",
    fallida: "border-acento text-acento",
    publicada: "border-tinta bg-tinta text-papel",
  };
  const texto: Record<string, string> = { en_edicion: "en edición" };
  return (
    <span className={`rounded-sm border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${estilos[estado] ?? ""}`}>
      {texto[estado] ?? estado}
    </span>
  );
}
