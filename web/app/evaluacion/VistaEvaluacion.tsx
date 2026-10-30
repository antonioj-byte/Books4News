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
  if (valor == null) return <span className="text-tinta-suave">—</span>;
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 bg-tinta" style={{ width: `${(valor / 5) * 80}px` }} />
      <span className="font-texto tabular-nums">{valor.toFixed(1)}</span>
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
    <div className="mx-auto max-w-4xl px-6 py-6">
      <div className="rotulo">Evaluación</div>
      <h1 className="mb-6 font-texto text-[40px] leading-none">Medias por criterio</h1>
      {filas && filas.length === 0 && <p className="text-tinta-suave">Aún no hay piezas evaluadas.</p>}
      {filas && filas.length > 0 && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b-[3px] border-tinta text-left">
              <th className="py-2">Día</th><th>Piezas</th>
              {CRITERIOS.map((c) => <th key={c.clave}>{c.texto}</th>)}
              <th>Se publicaría</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.fecha} className="border-b border-filete">
                <td className="py-2">{f.fecha}</td><td>{f.n}</td>
                {CRITERIOS.map((c) => <td key={c.clave}><Barra valor={f[c.clave]} /></td>)}
                <td className="font-texto">{f.publicaria == null ? "—" : `${Math.round(f.publicaria * 100)} %`}</td>
              </tr>
            ))}
            <tr className="border-t-[3px] border-tinta font-semibold">
              <td className="py-2">Total</td><td>{total}</td>
              {CRITERIOS.map((c) => <td key={c.clave}><Barra valor={media(c.clave)} /></td>)}
              <td className="font-texto">{media("publicaria") == null ? "—" : `${Math.round((media("publicaria") as number) * 100)} %`}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}
