"use client";

import Link from "next/link";
import { api, type ResumenRol } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

// El equipo de la agencia (3/11, a petición del usuario: «una agencia donde hay un director de arte, un director creativo,
// un copy…»). Cada rol con lo que hace, su modelo, lo que ha costado esta semana, su nota y las reglas que ha aprendido.
export const CAPA: Record<string, { texto: string; clase: string }> = {
  oficio: { texto: "oficio", clase: "bg-[#dfeae4] text-verde" },
  marca: { texto: "Folio", clase: "bg-[#fbe1ea] text-carmesi" },
  celda: { texto: "aprendida de Folio", clase: "border border-dashed border-tinta-suave text-tinta-suave" },
};
const CRITERIO: Record<string, string> = { seleccion: "selección", libro: "libro", idea: "idea", voz: "voz" };
export const modeloCorto = (m?: string | null) => (m ? m.replace("claude-", "").replace(/-(\d)-(\d)$/, " $1.$2") : "sin modelo");

export function coste(r: Pick<ResumenRol, "coste_7d_usd" | "coste_7d_eur">) {
  const partes = [r.coste_7d_usd ? `${r.coste_7d_usd.toFixed(2)} $` : "", r.coste_7d_eur ? `${r.coste_7d_eur.toFixed(2)} €` : ""].filter(Boolean);
  return partes.length ? partes.join(" · ") : "0 $";
}

function Tarjeta({ r }: { r: ResumenRol }) {
  const reglas = Object.entries(r.reglas ?? {}).filter(([, n]) => n > 0);
  return (
    <Link href={`/equipo/${r.id}`} className="panel flex flex-col gap-2.5 p-4 transition hover:-translate-y-0.5 hover:border-tinta">
      <h3 className="titular text-[19px] leading-tight">{r.nombre}</h3>
      <p className="text-[13.5px] leading-snug text-tinta-suave">{r.que_hace}</p>
      <span className="dato">{modeloCorto(r.modelo)}{r.esfuerzo ? ` · esfuerzo ${r.esfuerzo}` : ""} · {coste(r)} esta semana</span>
      {r.nota != null && (
        <span className="flex items-center gap-2 font-mono text-[12px] text-tinta-suave">
          {r.criterios.map((c) => CRITERIO[c] ?? c).join(" y ")}
          <span className="h-1.5 flex-1 overflow-hidden rounded bg-papel-hondo"><span className="block h-full bg-carmesi" style={{ width: `${(r.nota / 5) * 100}%` }} /></span>
          {r.nota.toFixed(1)}
        </span>
      )}
      <span className="mt-auto flex flex-wrap gap-1.5">
        {reglas.length
          ? reglas.map(([capa, n]) => <span key={capa} className={`rounded-[6px] px-2 py-0.5 font-mono text-[11px] ${CAPA[capa]?.clase ?? ""}`}>{n} · {CAPA[capa]?.texto ?? capa}</span>)
          : <span className="dato">Sin reglas propias</span>}
        {r.pendientes > 0 && <span className="rounded-[6px] bg-subrayador px-2 py-0.5 font-mono text-[11px]">{r.pendientes} por decidir</span>}
        {r.pedidos_7d > 0 && <span className="dato">{r.pedidos_7d} pedidos esta semana</span>}
      </span>
    </Link>
  );
}

export function VistaEquipo() {
  const { datos, error } = useDatos("equipo", api.equipo);
  const total = (datos ?? []).reduce((s, d) => s + d.roles.length, 0);
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="antetitulo">El equipo de Folio{total ? ` · ${total} roles` : ""}</div>
      <h1 className="titular mt-2 text-[40px] leading-tight">Quién hace <em>cada cosa</em></h1>
      <p className="mb-6 mt-2 max-w-[66ch] text-[14.5px] text-tinta-suave">
        Los roles son de la agencia; lo que aprenden de Folio, de Folio. Cada uno tiene sus reglas en tres capas: el oficio, que valdría para cualquier marca; lo que es de Folio para todos; y lo que ese rol ha aprendido de Folio en concreto.
      </p>
      {error && <p className="text-carmesi">{error}</p>}
      <div className="flex flex-col gap-7">
        {(datos ?? []).map((d) => (
          <section key={d.nombre} aria-labelledby={`dep-${d.nombre}`}>
            <h2 id={`dep-${d.nombre}`} className="dato mb-2.5 uppercase tracking-[0.16em]">{d.nombre}</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {d.roles.map((r) => <Tarjeta key={r.id} r={r} />)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
