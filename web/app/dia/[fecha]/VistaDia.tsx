"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Diapositiva } from "@/components/Diapositiva";
import { EstadoChip, Marcas } from "@/components/Marcas";
import { api, type Dia, type DiaDetalle } from "@/lib/api";

const hora = (iso: string) => new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

// Portada del día: las piezas de una ejecución con su estado y sus avisos.
export function VistaDia() {
  const { fecha } = useParams<{ fecha: string }>();
  const busqueda = useSearchParams();
  const router = useRouter();
  const ejecucion = busqueda.get("ejecucion") ? Number(busqueda.get("ejecucion")) : undefined;
  const [dias, setDias] = useState<Dia[]>([]);
  const [dia, setDia] = useState<DiaDetalle | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.dias().then(setDias).catch(() => setError("No responde la API (uv run folio web).")); }, []);
  useEffect(() => {
    api.dia(fecha, ejecucion).then(setDia).catch((e) => setError(String(e)));
  }, [fecha, ejecucion]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="rotulo">Portada del día</div>
          <h1 className="font-texto text-[40px] leading-none">
            {new Date(`${fecha}T12:00:00`).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </h1>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">Día
            <select value={fecha} onChange={(e) => router.push(`/dia/${e.target.value}`)}
                    className="rounded-sm border border-tinta bg-papel px-2 py-1">
              {dias.map((d) => <option key={d.fecha} value={d.fecha}>{d.fecha}</option>)}
            </select>
          </label>
          {dia && dia.ejecuciones.length > 1 && (
            <label className="flex items-center gap-2">Ejecución
              <select value={dia.ejecucion.id} onChange={(e) => router.push(`/dia/${fecha}?ejecucion=${e.target.value}`)}
                      className="rounded-sm border border-tinta bg-papel px-2 py-1">
                {dia.ejecuciones.map((e) => (
                  <option key={e.id} value={e.id}>{hora(e.generado_en)} · {e.piezas} piezas · {e.coste_usd.toFixed(2)} $</option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>

      {error && <p className="text-acento">{error}</p>}
      {dia?.aviso_jefe && (
        <p className="mb-4 border-l-[3px] border-acento bg-[#efe6d6] px-3 py-2 text-sm">
          <b>Aviso del jefe de cultura:</b> {dia.aviso_jefe}
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {dia?.piezas.map((p) => (
          <Link key={p.pieza_id} href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`}
                className="group flex flex-col gap-3 border-t-[3px] border-tinta pt-3 hover:border-acento">
            <div className="flex items-center justify-between">
              <EstadoChip estado={p.estado} />
              <span className="text-[12px] text-tinta-suave">
                {p.n_medios} medios{p.reserva ? " · reserva" : ""} · v{p.version}{p.evaluada ? " · evaluada ✓" : ""}
              </span>
            </div>
            {p.portada ? (
              <Diapositiva src={api.urlDiapositiva(p.ejecucion_id, p.pieza_id, 1, p.version)} ancho={300} titulo={p.titular} />
            ) : (
              <div className="flex h-[375px] w-[300px] items-center justify-center bg-[#e6e0d4] text-tinta-suave">Sin guion</div>
            )}
            <h2 className="font-texto text-[19px] leading-snug group-hover:text-acento">{p.titular}</h2>
            <Marcas marcas={p.marcas} />
          </Link>
        ))}
      </div>

      {dia && dia.avisos.length > 0 && (
        <details className="mt-8 text-sm text-tinta-suave">
          <summary className="cursor-pointer">Avisos de la ejecución ({dia.avisos.length}) · coste {dia.coste_usd.toFixed(2)} $</summary>
          <ul className="mt-2 list-disc pl-5">{dia.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}
    </div>
  );
}
