"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { Diapositiva } from "@/components/Diapositiva";
import { Estanteria } from "@/components/Estanteria";
import { LanzarEjecucion } from "@/components/LanzarEjecucion";
import { EstadoChip, FormatoChip, Marcas } from "@/components/Marcas";
import { Proceder } from "@/components/Proceder";
import { api } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

const hora = (iso: string) => new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

// Portada del día: la mesa de propuestas de una ejecución. Las escritas, con su portada, estado y avisos;
// las pendientes, con su titular, gancho y libro, y el botón «Proceder» para escribirlas.
export function VistaDia() {
  const { fecha } = useParams<{ fecha: string }>();
  const busqueda = useSearchParams();
  const router = useRouter();
  const ejecucion = busqueda.get("ejecucion") ? Number(busqueda.get("ejecucion")) : undefined;
  const { datos: listaDias, error: errorDias, recargar: recargarDias } = useDatos("dias", api.dias);
  const { datos: dia, error: errorDia, recargar: recargarDia } = useDatos(`dia:${fecha}:${ejecucion ?? ""}`, () => api.dia(fecha, ejecucion));
  const dias = listaDias ?? [];
  const error = errorDias ? "No responde la API (uv run folio web)." : errorDia;
  const alTerminar = useCallback(() => {
    recargarDias();
    api.dias().then((ds) => { if (ds.length) router.push(`/dia/${ds[0].fecha}`); router.refresh(); });
  }, [router, recargarDias]);

  const fechaLarga = new Date(`${fecha}T12:00:00`);
  const diaSemana = fechaLarga.toLocaleDateString("es-ES", { weekday: "long" });
  const diaMes = fechaLarga.toLocaleDateString("es-ES", { day: "numeric", month: "long" });
  const escritas = (dia?.piezas ?? []).filter((p) => p.estado !== "pendiente");
  const libros = escritas.flatMap((p) => p.libros);
  // Los temas del radar del libro sin escribir van en una lista aparte, debajo de la mesa; escritos, a la mesa
  const enRadar = (p: { radar: boolean; estado: string }) => p.radar && p.estado === "pendiente";
  const mesa = (dia?.piezas ?? []).filter((p) => !enRadar(p));
  const radar = (dia?.piezas ?? []).filter(enRadar);
  const pendientes = mesa.filter((p) => p.estado === "pendiente").length;
  const select = "rounded-full border border-borde bg-panel px-3 py-1.5 font-mono text-[12px] outline-none focus:border-tinta";

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="antetitulo">
            Mesa del día{dia ? ` · ${hora(dia.ejecucion.generado_en)} · ${mesa.length} propuestas, ${mesa.length - pendientes} escritas` : ""}
          </div>
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
        {mesa.map((p) => p.estado === "pendiente" ? (
          <div key={p.pieza_id} className="panel flex flex-col gap-3 border-dashed p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <FormatoChip formato={p.formato} />
              <EstadoChip estado={p.estado} />
            </div>
            <Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="titular text-[22px] leading-snug hover:text-carmesi">{p.titular}</Link>
            {p.gancho && <p className="font-titular text-[17px] italic leading-snug text-tinta-suave" style={{ fontWeight: 400 }}>{p.gancho}</p>}
            {!p.libros[0] && p.formato === "curiosidad" && <p className="dato">Del cajón de curiosidades · sin libro</p>}
            {p.libros[0] && (
              <div className="flex items-center gap-3">
                {p.libros[0].cubierta
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={p.libros[0].cubierta} alt={`Cubierta de ${p.libros[0].titulo}`} className="h-[84px] w-[56px] object-cover shadow-[var(--sombra-libro)]" />
                  : <div className="flex h-[84px] w-[56px] items-center justify-center bg-papel-hondo text-[10px] text-tinta-suave">sin cubierta</div>}
                <div className="text-[14px]"><b>{p.libros[0].titulo}</b><br /><span className="text-tinta-suave">{p.libros[0].autor}</span></div>
              </div>
            )}
            <div className="mt-auto pt-1"><Proceder eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} /></div>
          </div>
        ) : (
          <Link key={p.pieza_id} href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`}
                className="panel group flex flex-col gap-4 p-5 transition hover:-translate-y-0.5 hover:border-tinta">
            <div className="flex items-center justify-between">
              <span className="flex flex-wrap gap-1.5"><EstadoChip estado={p.estado} /><FormatoChip formato={p.formato} /></span>
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

      {radar.length > 0 && (
        <section className="mt-12" aria-labelledby="h-radar">
          <div className="antetitulo">Radar del libro</div>
          <h2 id="h-radar" className="titular mb-1 mt-2 text-[30px]">Temas del mundo del libro <em>para hoy</em></h2>
          <p className="mb-4 max-w-[62ch] text-[14px] text-tinta-suave">
            Historias de los medios culturales y del sector que se sostienen solas. Sin escribir: «Desarrollar» hace la pieza (unos minutos).
          </p>
          <ul className="panel divide-y divide-borde">
            {radar.map((p) => (
              <li key={p.pieza_id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="titular text-[19px] leading-snug hover:text-carmesi">{p.titular}</Link>
                  {p.por_que && <p className="mt-1 text-[14px] text-tinta-suave">{p.por_que}</p>}
                </div>
                <div className="flex-none"><Proceder eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} texto="Desarrollar" /></div>
              </li>
            ))}
          </ul>
        </section>
      )}

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
