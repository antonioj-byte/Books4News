"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { Diapositiva } from "@/components/Diapositiva";
import { LanzarEjecucion } from "@/components/LanzarEjecucion";
import { EstadoChip, FormatoChip, Marcas } from "@/components/Marcas";
import { Descartar } from "@/components/Descartar";
import { Proceder } from "@/components/Proceder";
import { ProponerTema } from "@/components/ProponerTema";
import { CincoDelLibro } from "@/components/CincoDelLibro";
import { api } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { EsqueletoTarjetas } from "@/components/Esqueleto";

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
        </div>
      </div>

      {/* 4/11 («al entrar me lleva al domingo 1 de noviembre»): el navegador abría una dirección guardada de un día
          viejo; si hay uno más reciente, se dice y se lleva a él con un clic */}
      {!ejecucion && dias[0] && dias[0].fecha > fecha && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-[12px] border border-carmesi bg-panel px-4 py-3 text-[14px]" role="status">
          <span>Estás viendo la mesa de un día anterior.</span>
          <Link href={`/dia/${dias[0].fecha}`} className="boton-suave border-carmesi text-carmesi">
            Ir a la mesa más reciente ({new Date(`${dias[0].fecha}T12:00:00`).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" })}) →
          </Link>
        </div>
      )}

      <ProponerTema eid={dia?.ejecucion.id} onPieza={recargarDia} />

      {error && <p className="text-carmesi" role="alert">{error}</p>}
      {!dia && !error && <EsqueletoTarjetas n={6} rejilla />}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {mesa.map((p) => p.estado === "pendiente" ? (
          <div key={p.pieza_id} className="panel flex flex-col gap-3 border-dashed p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <FormatoChip formato={p.formato} />
              <EstadoChip estado={p.estado} />
            </div>
            <Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="titular text-[22px] leading-snug hover:text-carmesi">{p.titular}</Link>
            {p.gancho && <p className="font-titular text-[17px] italic leading-snug text-tinta-suave" style={{ fontWeight: 400 }}>{p.gancho}</p>}
            {!p.libros[0] && ["curiosidad", "noticia", "ensayo"].includes(p.formato) && <p className="dato">Sin libro</p>}
            {p.libros[0] && (
              <div className="flex items-center gap-3">
                {p.libros[0].cubierta
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={p.libros[0].cubierta} alt={`Cubierta de ${p.libros[0].titulo}`} className="h-[84px] w-[56px] object-cover shadow-[var(--sombra-libro)]" />
                  : <div className="flex h-[84px] w-[56px] items-center justify-center bg-papel-hondo text-[10px] text-tinta-suave">sin cubierta</div>}
                <div className="text-[14px]"><b>{p.libros[0].titulo}</b><br /><span className="text-tinta-suave">{p.libros[0].autor}</span></div>
              </div>
            )}
            <div className="mt-auto flex flex-col gap-2 pt-1">
              <Proceder eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} />
              <Descartar eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} compacto />
            </div>
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
                <div className="flex h-[325px] w-[260px] flex-col items-center justify-center gap-2 overflow-hidden rounded-[6px] bg-papel-hondo p-4 text-center text-tinta-suave">
                  <span>Sin guion</span>
                  {p.marcas.error && <span className="line-clamp-6 text-[12.5px] leading-snug text-carmesi">{p.marcas.error}</span>}
                </div>
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

      {dia && <CincoDelLibro fecha={fecha} onHecho={recargarDia} yaHecha={(dia.piezas ?? []).some((p) => p.formato === "cinco")} />}

      {radar.length > 0 && (
        <details className="mt-10">
          <summary className="cursor-pointer">
            <span className="titular text-[24px]">Breves del <em>mundo del libro</em></span>
            <span className="dato ml-2">{radar.length}</span>
          </summary>
          <p className="mb-4 mt-2 max-w-[62ch] text-[14px] text-tinta-suave">
            Noticias con gancho que no necesitan una pieza propia. Si alguna lo merece, «Escribir pieza» la desarrolla.
          </p>
          <ul className="panel divide-y divide-borde">
            {radar.map((p) => (
              <li key={p.pieza_id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="titular text-[19px] leading-snug">{p.titular}</p>
                  {p.por_que && <p className="mt-1 text-[14px] text-tinta-suave">{p.por_que}</p>}
                  {p.enlaces.length > 0 && (
                    <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[13px]">
                      {p.enlaces.map((e) => (
                        <a key={e.url} href={e.url} target="_blank" rel="noreferrer" className="underline decoration-borde underline-offset-2 hover:text-carmesi">Leer en {e.medio} ↗</a>
                      ))}
                    </p>
                  )}
                </div>
                <div className="flex-none"><Proceder eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} texto="Escribir pieza" /></div>
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Lo técnico, plegado al pie (3/11, «se está volviendo demasiado compleja»): otro día u otra ejecución, lanzar a mano, avisos y coste */}
      <details className="mt-10 text-sm">
        <summary className="dato cursor-pointer uppercase">
          Detalles{dia ? ` · ejecución de las ${hora(dia.ejecucion.generado_en)} · ${dia.coste_usd.toFixed(2)} $${dia.avisos.length ? ` · ${dia.avisos.length} avisos` : ""}${dia.aviso_jefe ? " · notas del jefe" : ""}` : ""}
        </summary>
        <div className="mt-3 flex flex-col items-start gap-4">
          <div className="flex flex-wrap items-center gap-2">
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
          <LanzarEjecucion alTerminar={alTerminar} />
          {/* 6/11 («no sé si me parece innecesario el mensaje del aviso del jefe… no me aporta mucho»): sus notas sobre
              lo que dejó fuera, aquí y no encima de la mesa */}
          {dia?.aviso_jefe && <p className="max-w-[72ch] text-tinta-suave"><b>Notas del jefe de cultura:</b> {dia.aviso_jefe}</p>}
          {dia && dia.avisos.length > 0 && (
            <ul className="list-disc pl-5 text-tinta-suave">{dia.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
          )}
        </div>
      </details>
    </div>
  );
}
