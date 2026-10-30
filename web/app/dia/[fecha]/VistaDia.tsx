"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { Diapositiva } from "@/components/Diapositiva";
import { Estanteria } from "@/components/Estanteria";
import { LanzarEjecucion } from "@/components/LanzarEjecucion";
import { EstadoChip, Marcas } from "@/components/Marcas";
import { api } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

const hora = (iso: string) => new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

// Portada del día: las piezas de una ejecución con su estado y sus avisos.
export function VistaDia() {
  const { fecha } = useParams<{ fecha: string }>();
  const busqueda = useSearchParams();
  const router = useRouter();
  const ejecucion = busqueda.get("ejecucion") ? Number(busqueda.get("ejecucion")) : undefined;
  const { datos: listaDias, error: errorDias, recargar: recargarDias } = useDatos("dias", api.dias);
  const { datos: dia, error: errorDia } = useDatos(`dia:${fecha}:${ejecucion ?? ""}`, () => api.dia(fecha, ejecucion));
  const dias = listaDias ?? [];
  const error = errorDias ? "No responde la API (uv run folio web)." : errorDia;
  const alTerminar = useCallback(() => {
    recargarDias();
    api.dias().then((ds) => { if (ds.length) router.push(`/dia/${ds[0].fecha}`); router.refresh(); });
  }, [router, recargarDias]);

  const fechaLarga = new Date(`${fecha}T12:00:00`);
  const diaSemana = fechaLarga.toLocaleDateString("es-ES", { weekday: "long" });
  const diaMes = fechaLarga.toLocaleDateString("es-ES", { day: "numeric", month: "long" });
  const libros = (dia?.piezas ?? []).flatMap((p) => p.libros);
  const select = "rounded-full border border-borde bg-panel px-3 py-1.5 font-mono text-[12px] outline-none focus:border-tinta";

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="antetitulo">Portada del día{dia ? ` · ${hora(dia.ejecucion.generado_en)}` : ""}</div>
          <h1 className="titular mt-2 text-[52px]">
            {diaSemana}, <em>{diaMes}</em>
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select value={fecha} onChange={(e) => router.push(`/dia/${e.target.value}`)} className={select} aria-label="Día">
              {dias.map((d) => <option key={d.fecha} value={d.fecha}>{d.fecha}</option>)}
            </select>
            {dia && dia.ejecuciones.length > 1 && (
              <select value={dia.ejecucion.id} onChange={(e) => router.push(`/dia/${fecha}?ejecucion=${e.target.value}`)}
                      className={select} aria-label="Ejecución">
                {dia.ejecuciones.map((e) => (
                  <option key={e.id} value={e.id}>{hora(e.generado_en)} · {e.piezas} piezas · {e.coste_usd.toFixed(2)} $</option>
                ))}
              </select>
            )}
          </div>
        </div>
        <LanzarEjecucion alTerminar={alTerminar} />
      </div>

      {error && <p className="text-carmesi">{error}</p>}
      {dia?.aviso_jefe && (
        <p className="panel mb-6 px-5 py-3 text-sm">
          <span className="subrayado font-semibold">Aviso del jefe de cultura</span> {dia.aviso_jefe}
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {dia?.piezas.map((p) => (
          <Link key={p.pieza_id} href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`}
                className="panel group flex flex-col gap-4 p-5 transition hover:-translate-y-0.5 hover:border-tinta">
            <div className="flex items-center justify-between">
              <EstadoChip estado={p.estado} />
              <span className="dato">
                {p.n_medios} medios{p.reserva ? " · reserva" : ""} · v{p.version}
              </span>
            </div>
            <div className="flex justify-center py-1">
              {p.portada ? (
                <Diapositiva src={api.urlDiapositiva(p.ejecucion_id, p.pieza_id, 1, p.version)} ancho={260} titulo={p.titular} />
              ) : (
                <div className="flex h-[325px] w-[260px] items-center justify-center rounded-[6px] bg-papel-hondo text-tinta-suave">Sin guion</div>
              )}
            </div>
            <h2 className="titular text-[21px] leading-snug group-hover:text-carmesi">{p.titular}</h2>
            <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
              <Marcas marcas={p.marcas} />
              {p.evaluada && <span className="chip bg-verde text-papel">Evaluada</span>}
            </div>
          </Link>
        ))}
      </div>

      {libros.length > 0 && (
        <div className="mt-12 max-w-xl">
          <Estanteria libros={libros} pie="Estantería · los libros que recomienda hoy Folio" />
        </div>
      )}

      {dia && dia.avisos.length > 0 && (
        <details className="mt-10 text-sm text-tinta-suave">
          <summary className="dato cursor-pointer uppercase">Avisos de la ejecución · {dia.avisos.length} · coste {dia.coste_usd.toFixed(2)} $</summary>
          <ul className="mt-2 list-disc pl-5">{dia.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}
    </div>
  );
}
