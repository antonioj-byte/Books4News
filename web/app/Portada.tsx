"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FormatoChip } from "@/components/Marcas";
import { LanzarEjecucion } from "@/components/LanzarEjecucion";
import { api, type DiaDetalle, type ListaCinco, type PiezaArchivo } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

const Esqueleto = ({ className = "" }: { className?: string }) => <div className={`esqueleto rounded-[10px] ${className}`} aria-hidden />;

// La portada de Folio (7/11, a petición del usuario: «no hay una URL principal… me gustaría que hubiese como un panel
// general, que no sean las noticias del día»; eligió la opción C, «La portada del día», del Artifact «La portada de
// Folio»): lo más importante del mundo del libro hoy (la lista que Folio ya selecciona, la misma que va por Telegram)
// y, al lado, lo que hay por publicar y por elegir.
export function Portada() {
  const { datos: dias, error } = useDatos("dias", api.dias);
  const fecha = dias?.[0]?.fecha;
  const { datos: archivo } = useDatos("archivo", api.archivo);
  const [dia, setDia] = useState<DiaDetalle | null>(null);
  const [lista, setLista] = useState<ListaCinco | null>(null);
  useEffect(() => {
    if (!fecha) return;
    api.dia(fecha).then(setDia).catch(() => setDia(null));
    api.listaCinco(fecha).then(setLista).catch(() => setLista({ modo: "", propuesta: null }));
  }, [fecha]);

  if (error) return <p className="p-6 text-carmesi" role="alert">No responde la API (uv run folio web).</p>;
  if (dias && dias.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="titular text-[48px]">¿Qué leemos hoy? <em>Te lo chivamos.</em></h1>
        <p className="mt-4 text-[17px]">Aún no hay ninguna ejecución. Lánzala y en unos minutos tienes la mesa del día.</p>
        <div className="mt-6"><LanzarEjecucion alTerminar={() => location.reload()} /></div>
      </div>
    );
  }

  const candidatas = [...(lista?.propuesta?.candidatas ?? [])].sort((a, b) => Number(b.marcada) - Number(a.marcada));
  const [primera, ...resto] = candidatas;
  const porElegir = (dia?.piezas ?? []).filter((p) => p.estado === "pendiente").length;
  const deHoy = (a: PiezaArchivo) => a.fecha === fecha;
  const programadas = (archivo ?? []).filter((a) => a.categoria === "programada");
  const porAprobar = (archivo ?? []).filter((a) => a.categoria === "aprobada" || (a.categoria === "nevera" && deHoy(a)));
  const fechaLarga = fecha ? new Date(`${fecha}T12:00:00`) : null;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="antetitulo">Folio · la portada</div>
      <h1 className="titular mt-2 text-[40px] sm:text-[52px]">
        {fechaLarga ? <>{fechaLarga.toLocaleDateString("es-ES", { weekday: "long" })}, <em>{fechaLarga.toLocaleDateString("es-ES", { day: "numeric", month: "long" })}</em></> : "…"}
      </h1>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="panel flex min-w-0 flex-col gap-4 p-5 sm:p-6" aria-labelledby="h-libro-hoy">
          <h2 id="h-libro-hoy" className="dato uppercase">El libro hoy</h2>
          {!lista && <Esqueleto className="h-40" />}
          {lista && !primera && <p className="text-tinta-suave">Aún no hay lista de noticias del libro para hoy.</p>}
          {primera && (
            <article className="flex flex-col gap-2">
              <a href={primera.url || undefined} target="_blank" rel="noreferrer" className="titular text-[28px] leading-[1.08] hover:text-carmesi sm:text-[34px]">{primera.titular}</a>
              <p className="max-w-[60ch] text-[16px] text-tinta-suave">{primera.por_que}</p>
              <p className="dato">{primera.medio}{primera.n_medios > 1 ? ` · ${primera.n_medios} medios` : ""}</p>
            </article>
          )}
          {resto.length > 0 && (
            <ol className="flex flex-col divide-y divide-borde border-t border-borde">
              {resto.map((c, i) => (
                <li key={c.historia} className="flex items-baseline gap-3 py-2.5">
                  <span className="dato w-5 flex-none text-right">{i + 2}</span>
                  <div className="min-w-0 flex-1">
                    <a href={c.url || undefined} target="_blank" rel="noreferrer" className="font-titular text-[17px] leading-snug hover:text-carmesi">{c.titular}</a>
                    <p className="text-[13.5px] text-tinta-suave">{c.por_que}</p>
                  </div>
                  <span className="dato hidden flex-none sm:inline">{c.medio}{c.n_medios > 1 ? ` · ${c.n_medios}` : ""}</span>
                </li>
              ))}
            </ol>
          )}
          {fecha && primera && (
            <Link href={`/dia/${fecha}?filtro=cinco`} className="boton-suave self-start">Elegir los breves del libro →</Link>
          )}
        </section>

        <div className="flex flex-col gap-6">
          <section className="panel flex flex-col gap-3 p-6" aria-labelledby="h-publicar">
            <h2 id="h-publicar" className="dato uppercase">Por publicar</h2>
            {!archivo && <Esqueleto className="h-24" />}
            {archivo && programadas.length + porAprobar.length === 0 && <p className="text-[14px] text-tinta-suave">Nada escrito por publicar.</p>}
            {[...programadas.map((a) => ({ a, etiqueta: "Programada", clase: "bg-subrayador text-tinta" })),
              ...porAprobar.map((a) => ({ a, etiqueta: a.categoria === "aprobada" ? "Aprobada" : "Por aprobar", clase: "border border-borde" }))]
              .map(({ a, etiqueta, clase }) => (
                <Link key={`${a.ejecucion_id}-${a.pieza_id}`} href={`/pieza/${a.ejecucion_id}/${a.pieza_id}`}
                      className="flex items-baseline gap-2 text-[14px] hover:text-carmesi">
                  <span className={`chip flex-none ${clase}`}>{etiqueta}</span>
                  <span className="min-w-0 flex-1 truncate">{a.titular}</span>
                </Link>
              ))}
          </section>

          <section className="panel flex flex-col gap-3 p-6" aria-labelledby="h-elegir">
            <h2 id="h-elegir" className="dato uppercase">Por elegir</h2>
            {!dia && <Esqueleto className="h-16" />}
            {dia && (
              <>
                <p className="text-[15px]"><b className="titular text-[28px]">{porElegir}</b> temas del día esperan a que elijas cuáles se escriben.</p>
                <div className="flex flex-col gap-1.5">
                  {(dia.piezas ?? []).filter((p) => p.estado === "pendiente" && !p.radar).slice(0, 4).map((p) => (
                    <div key={p.pieza_id} className="flex items-baseline gap-2 text-[14px]">
                      <FormatoChip formato={p.formato} />
                      <span className="min-w-0 flex-1 truncate">{p.titular}</span>
                    </div>
                  ))}
                </div>
                <Link href={`/dia/${fecha}`} className="boton self-start">Ir a «Hoy» →</Link>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
