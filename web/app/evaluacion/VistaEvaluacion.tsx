"use client";

import { api, type ResumenDia } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

const CRITERIOS = [
  { clave: "seleccion", texto: "Selección" },
  { clave: "libro", texto: "Libro" },
  { clave: "idea", texto: "Idea nueva" },
  { clave: "voz", texto: "Voz" },
] as const;

function Barra({ valor }: { valor: number | null }) {
  if (valor == null) return <span className="dato">—</span>;
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 rounded-full bg-carmesi" style={{ width: `${(valor / 5) * 80}px` }} />
      <span className="font-mono text-[13px] tabular-nums">{valor.toFixed(1)}</span>
    </span>
  );
}

// Medias por criterio a lo largo de los días de evaluación.
export function VistaEvaluacion() {
  const { datos, error } = useDatos("resumen", api.resumen);
  const filas: ResumenDia[] | null = error ? [] : datos;
  const total = (filas ?? []).reduce((s, f) => s + f.n, 0);
  const media = (clave: (typeof CRITERIOS)[number]["clave"] | "publicaria") => {
    const conDato = (filas ?? []).filter((f) => f[clave] != null);
    const n = conDato.reduce((s, f) => s + f.n, 0);
    return n ? conDato.reduce((s, f) => s + (f[clave] as number) * f.n, 0) / n : null;
  };
  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="antetitulo">Evaluación</div>
      <h1 className="titular mb-8 mt-2 text-[48px]">Medias por <em>criterio</em></h1>
      {filas && filas.length === 0 && <p className="text-tinta-suave">Aún no has evaluado ninguna pieza. Empieza por la portada del día.</p>}
      {filas && filas.length > 0 && (
        <div className="panel overflow-x-auto p-5">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-tinta text-left font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">
              <th className="py-2">Día</th><th>Piezas</th>
              {CRITERIOS.map((c) => <th key={c.clave}>{c.texto}</th>)}
              <th>Se publicaría</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.fecha} className="border-b border-borde">
                <td className="py-2.5 font-mono text-[13px]">{f.fecha}</td><td className="font-mono text-[13px]">{f.n}</td>
                {CRITERIOS.map((c) => <td key={c.clave}><Barra valor={f[c.clave]} /></td>)}
                <td className="font-mono text-[13px]">{f.publicaria == null ? "—" : `${Math.round(f.publicaria * 100)} %`}</td>
              </tr>
            ))}
            <tr className="border-t border-tinta font-semibold">
              <td className="py-2.5">Total</td><td className="font-mono text-[13px]">{total}</td>
              {CRITERIOS.map((c) => <td key={c.clave}><Barra valor={media(c.clave)} /></td>)}
              <td className="font-mono text-[13px]">{media("publicaria") == null ? "—" : `${Math.round((media("publicaria") as number) * 100)} %`}</td>
            </tr>
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
