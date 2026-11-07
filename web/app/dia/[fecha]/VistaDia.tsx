"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
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
import { TarjetaPorElegir } from "@/components/TarjetaPorElegir";

type Filtro = "todo" | "propuestas" | "breves" | "encargos" | "cinco";

const hora = (iso: string) => new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

// La mesa del día, en dos pestañas (7/11, a petición del usuario: «muy feo esto de que presente las noticias con
// algunas diapositivas sí, otras no… primero tiene que presentar los temas sin un desarrollo, yo lo selecciono»; eligió
// la opción H2 del Artifact «La portada de Folio»). «Por elegir»: todo lo que aún no está escrito con la misma tarjeta
// (propuestas, breves del radar, encargos de la redacción y «Cinco del libro»), con un filtro por tipo y «Escribir».
// «En la mesa»: lo escrito, con su portada. De madrugada ya no se escribe nada solo (`desarrollar_al_inicio: 0`).
export function VistaDia() {
  const { fecha } = useParams<{ fecha: string }>();
  const busqueda = useSearchParams();
  const router = useRouter();
  const ejecucion = busqueda.get("ejecucion") ? Number(busqueda.get("ejecucion")) : undefined;
  const filtroInicial = busqueda.get("filtro") as Filtro | null;
  const [pestana, setPestana] = useState<"elegir" | "mesa">(busqueda.get("ver") === "mesa" ? "mesa" : "elegir");
  const [filtro, setFiltro] = useState<Filtro>(filtroInicial ?? "todo");
  const [vTemas, setVTemas] = useState(0);
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
  const todas = dia?.piezas ?? [];
  const porEscribir = (p: { estado: string }) => p.estado === "pendiente" || p.estado === "fallida";
  const propuestas = todas.filter((p) => porEscribir(p) && !p.radar);
  const radar = todas.filter((p) => p.radar && p.estado === "pendiente");
  const mesa = todas.filter((p) => !porEscribir(p) && p.estado !== "descartada");
  const cincoHecha = todas.some((p) => p.formato === "cinco");
  const nElegir = propuestas.length + radar.length + (cincoHecha ? 0 : 1);
  const ver = (f: Filtro) => filtro === "todo" || filtro === f;
  const select = "rounded-full border border-borde bg-panel px-3 py-1.5 font-mono text-[12px] outline-none focus:border-tinta";

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="antetitulo">
            Mesa del día{dia ? ` · ${hora(dia.ejecucion.generado_en)} · ${propuestas.length + radar.length} por elegir, ${mesa.length} escritas` : ""}
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

      <ProponerTema eid={dia?.ejecucion.id} onPieza={recargarDia} modo="caja" onTema={() => setVTemas((v) => v + 1)} />

      {error && <p className="text-carmesi" role="alert">{error}</p>}
      {!dia && !error && <EsqueletoTarjetas n={6} rejilla />}

      {dia && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-2 border-b border-borde pb-3" role="tablist" aria-label="La mesa">
            {([["elegir", "Por elegir", nElegir], ["mesa", "En la mesa", mesa.length]] as const).map(([v, txt, n]) => (
              <button key={v} role="tab" aria-selected={pestana === v} onClick={() => setPestana(v)}
                      className={`rounded-full border px-4 py-1.5 text-[14px] ${pestana === v ? "border-tinta bg-tinta text-papel" : "border-borde bg-panel hover:border-tinta"}`}>
                {txt} <span className="font-mono text-[12px] opacity-70">{n}</span>
              </button>
            ))}
          </div>

          {pestana === "elegir" && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Qué enseñar">
                {([["todo", "Todo"], ["propuestas", `Propuestas · ${propuestas.length}`], ["breves", `Breves · ${radar.length}`], ["encargos", "Encargos"], ["cinco", "Breves del libro"]] as const).map(([v, txt]) => (
                  <button key={v} aria-pressed={filtro === v} onClick={() => setFiltro(v)}
                          className={`rounded-full border px-3 py-1 text-[13px] ${filtro === v ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-panel hover:border-tinta"}`}>
                    {txt}
                  </button>
                ))}
              </div>

              {ver("encargos") && <ProponerTema key={vTemas} eid={dia.ejecucion.id} onPieza={recargarDia} modo="lista" />}

              {ver("propuestas") && propuestas.map((p) => (
                <TarjetaPorElegir key={p.pieza_id}
                  etiquetas={<><FormatoChip formato={p.formato} />{p.estado === "fallida" && <EstadoChip estado={p.estado} />}
                    {p.encargo && <span className="chip bg-tinta text-papel">Encargo</span>}
                    {p.n_medios > 1 && <span className="dato">{p.n_medios} medios</span>}</>}
                  titulo={<Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="hover:text-carmesi">{p.titular}</Link>}
                  linea={p.estado === "fallida" ? (p.marcas.error ?? "No se pudo preparar") : p.gancho}
                  acciones={p.estado === "pendiente" ? <>
                    <Proceder eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} texto="Escribir" />
                    <Descartar eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} compacto />
                  </> : <Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="boton-suave text-center">Ver por qué</Link>}>
                  {p.libros[0] ? (
                    <div className="flex items-center gap-3">
                      {p.libros[0].cubierta
                        // eslint-disable-next-line @next/next/no-img-element
                        ? <img src={p.libros[0].cubierta} alt={`Cubierta de ${p.libros[0].titulo}`} className="h-[60px] w-[40px] object-cover shadow-[var(--sombra-libro)]" />
                        : null}
                      <div className="text-[14px]"><b>{p.libros[0].titulo}</b> <span className="text-tinta-suave">· {p.libros[0].autor}</span></div>
                    </div>
                  ) : ["curiosidad", "noticia", "ensayo", "edicion"].includes(p.formato) && p.estado === "pendiente" ? <p className="dato">Sin libro</p> : null}
                </TarjetaPorElegir>
              ))}

              {ver("breves") && radar.map((p) => (
                <TarjetaPorElegir key={p.pieza_id}
                  etiquetas={<><span className="chip border border-borde">Breve</span>{p.n_medios > 1 && <span className="dato">{p.n_medios} medios</span>}</>}
                  titulo={p.titular}
                  linea={p.por_que}
                  acciones={<>
                    <Proceder eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} texto="Escribir" />
                    <Descartar eid={p.ejecucion_id} pid={p.pieza_id} onHecho={recargarDia} compacto />
                  </>}>
                  {p.enlaces.length > 0 && (
                    <p className="flex flex-wrap gap-x-3 gap-y-1 text-[13px]">
                      {p.enlaces.map((e) => (
                        <a key={e.url} href={e.url} target="_blank" rel="noreferrer" className="underline decoration-borde underline-offset-2 hover:text-carmesi">Leer en {e.medio} ↗</a>
                      ))}
                    </p>
                  )}
                </TarjetaPorElegir>
              ))}

              {ver("cinco") && (!cincoHecha || filtro === "cinco") && (
                <TarjetaPorElegir
                  etiquetas={<span className="chip bg-subrayador text-tinta">Breves del libro</span>}
                  titulo="Elige las noticias del post de hoy"
                  linea="Las noticias del mundo del libro que valgan hoy, de una a siete, cada una con su ilustración. El jefe deja marcadas las que publicaría; si hoy no hay ninguna, ninguna.">
                  <CincoDelLibro fecha={fecha} onHecho={recargarDia} yaHecha={cincoHecha} />
                </TarjetaPorElegir>
              )}

              {nElegir === 0 && <p className="text-tinta-suave">No queda nada por elegir hoy. Lo escrito está en «En la mesa».</p>}
            </div>
          )}

          {pestana === "mesa" && (
            <>
              {mesa.length === 0 && <p className="text-tinta-suave">Aún no hay nada escrito. En «Por elegir», pulsa «Escribir» en los temas que quieras.</p>}
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {mesa.map((p) => (
                  <Link key={p.pieza_id} href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`}
                        className="panel group flex flex-col gap-4 p-5 transition hover:-translate-y-0.5 hover:border-tinta">
                    <div className="flex items-center justify-between">
                      <span className="flex flex-wrap gap-1.5"><EstadoChip estado={p.estado} /><FormatoChip formato={p.formato} /></span>
                      <span className="dato">v{p.version}</span>
                    </div>
                    <div className="flex justify-center py-1">
                      {p.portada ? (
                        <Diapositiva src={api.urlDiapositiva(p.ejecucion_id, p.pieza_id, 1, p.version)} ancho={260} titulo={p.titular} />
                      ) : (
                        <div className="flex h-[325px] w-[260px] items-center justify-center rounded-[6px] bg-papel-hondo text-tinta-suave">Sin portada</div>
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
            </>
          )}
        </>
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
