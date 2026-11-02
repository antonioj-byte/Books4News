"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type PropuestaDelFondo } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

// El fondo del mes (2/11, a petición del usuario): propuestas de actualidad lateral que valen unos meses, para tener
// margen de previsión. Escribir una la lleva a la mesa del día como un tema de la redacción (busca lo último del tema).
const FORMATOS: Record<string, string> = {
  lateral: "Lectura lateral", dialogo: "Diálogo", balda: "Tres libros", recomendado: "Recomendado", edicion: "Mundo del libro",
};
const ESTADOS = [
  { valor: "disponible", texto: "Disponibles" },
  { valor: "usada", texto: "Escritas" },
  { valor: "descartada", texto: "Descartadas" },
] as const;

const fecha = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "long" });

function Tarjeta({ p, eid, alCambiar }: { p: PropuestaDelFondo; eid: number | null; alCambiar: () => void }) {
  const [trabajando, setTrabajando] = useState<"" | "escribir" | "descartar">("");
  const [mensaje, setMensaje] = useState<React.ReactNode>(null);
  const escribir = async () => {
    if (!eid) return;
    setTrabajando("escribir");
    setMensaje(null);
    try {
      const r = await api.escribirDelFondo(p.id, eid);
      setMensaje(r.pieza_id
        ? <>En la mesa como <Link className="underline" href={`/pieza/${eid}/${r.pieza_id}`}>{r.pieza_id}</Link> · {r.respuesta}</>
        : <>El jefe pregunta antes de proponer: {r.preguntas.join(" ")} Contéstale en «Proponer un tema», en la mesa.</>);
      alCambiar();
    } catch (e) {
      setMensaje(`No se pudo: ${String(e)}`);
    } finally {
      setTrabajando("");
    }
  };
  const descartar = async () => {
    setTrabajando("descartar");
    try { await api.descartarDelFondo(p.id); alCambiar(); } finally { setTrabajando(""); }
  };
  return (
    <article className="panel flex flex-col gap-2 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-tinta px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-[0.12em]">{FORMATOS[p.formato] ?? p.formato}</span>
        <span className="font-mono text-[11px] text-tinta-suave">vale hasta el {fecha(p.vale_hasta)}</span>
        {p.puente && <span className="font-mono text-[11px] text-tinta-suave">· puente {p.puente}/5</span>}
        <span className="font-mono text-[11px] text-tinta-suave">· potencial {p.potencial}/10</span>
      </div>
      <h3 className="text-[19px] font-semibold leading-snug">{p.titular}</h3>
      <p className="text-[14px]">{p.de_que_se_habla}</p>
      <p className="rounded-[6px] bg-papel-hondo px-3 py-2 text-[14px]"><b>Libro:</b> {p.libros.join(" / ")}<br /><b>Puente:</b> {p.gancho_libro}</p>
      <p className="text-[13px] text-tinta-suave"><b>Por qué dura:</b> {p.por_que_dura} <b>Sacarla si…</b> {p.reactivar}</p>
      {p.cosecha && <p className="text-[12px] text-tinta-suave">De la cosecha: {p.cosecha}</p>}
      {p.estado === "disponible" && (
        <div className="flex flex-wrap items-center gap-2">
          <button className="boton" onClick={escribir} disabled={!!trabajando || !eid}
                  title={eid ? "" : "Hace falta una mesa del día"}>{trabajando === "escribir" ? "Llevando a la mesa… (1–2 min)" : "Escribir pieza"}</button>
          <button className="boton-suave" onClick={descartar} disabled={!!trabajando}>Descartar</button>
        </div>
      )}
      {mensaje && <p className="text-[13px]">{mensaje}</p>}
    </article>
  );
}

export function VistaFondo() {
  const { datos, error, recargar } = useDatos("fondo", api.fondo);
  const dias = useDatos("dias", api.dias);
  const [estado, setEstado] = useState<string>("disponible");
  const [formato, setFormato] = useState<string>("");
  const [lanzando, setLanzando] = useState(false);
  const [aviso, setAviso] = useState("");
  const preparando = datos?.preparando?.en_marcha;
  useEffect(() => {
    if (!preparando) return;
    const t = setInterval(recargar, 8000);
    return () => clearInterval(t);
  }, [preparando, recargar]);
  // La mesa en que entra lo que se escribe: la última ejecución del último día
  const eid = dias.datos?.[0]?.ejecuciones?.[0]?.id ?? null;
  const preparar = async () => {
    setLanzando(true);
    setAviso("");
    try { await api.prepararFondo(1); recargar(); } catch (e) { setAviso(String(e)); } finally { setLanzando(false); }
  };
  const todas = datos?.propuestas ?? [];
  const disponibles = todas.filter((p) => p.estado === "disponible");
  const vistas = todas.filter((p) => p.estado === estado && (!formato || p.formato === formato));
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="mb-1 text-[28px] font-semibold tracking-tight">Fondo del mes</h1>
      <p className="mb-4 text-[14px] text-tinta-suave">
        Propuestas de actualidad lateral que valen unos meses. Se prepara solo el día 1 de cada mes; al escribir una, se
        buscan sus noticias más recientes para que la pieza cuente lo último.
      </p>
      <div className="mb-4 flex flex-wrap gap-2 text-[13px]">
        {Object.entries(datos?.objetivo ?? {}).map(([f, n]) => (
          <span key={f} className="rounded-full bg-papel-hondo px-3 py-1">
            {FORMATOS[f] ?? f}: {disponibles.filter((p) => p.formato === f).length} / {n}
          </span>
        ))}
      </div>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button className="boton" onClick={preparar} disabled={lanzando || !!preparando}>
          {preparando ? "Preparando una tanda…" : "Preparar una tanda (25 · ~1,40 $)"}
        </button>
        {preparando && <span className="dato">El jefe propone, el evaluador de puentes filtra y se verifican los libros: unos 15 minutos{datos?.preparando?.etapa ? ` · ${datos.preparando.etapa}` : ""}</span>}
        {aviso && <span className="text-[13px] text-carmesi">{aviso}</span>}
      </div>
      {datos?.preparando && !preparando && (
        // Cómo acabó la última tanda (2/11: «le di a preparar tanda pero no ha hecho nada»: la página no lo decía)
        <div className={`mb-6 rounded-[10px] border px-4 py-3 text-[13px] ${datos.preparando.codigo === 0 ? "border-borde bg-panel" : "border-carmesi bg-papel"}`}>
          <p className="mb-1 font-semibold">{datos.preparando.codigo === 0 ? "La última tanda terminó" : `La última tanda falló (código ${datos.preparando.codigo ?? "?"})`}</p>
          <pre className="whitespace-pre-wrap font-mono text-[12px] text-tinta-suave">{datos.preparando.ultimas_lineas.join("\n") || "(sin salida)"}</pre>
        </div>
      )}
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Estado">
        {ESTADOS.map((e) => (
          <button key={e.valor} aria-pressed={estado === e.valor} onClick={() => setEstado(e.valor)}
                  className={`rounded-full border px-3 py-1 text-[13px] ${estado === e.valor ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-papel hover:border-tinta"}`}>
            {e.texto} ({todas.filter((p) => p.estado === e.valor).length})
          </button>
        ))}
      </div>
      <div className="mb-6 flex flex-wrap gap-1.5" role="group" aria-label="Formato">
        {[["", "Todos"], ...Object.entries(FORMATOS)].map(([f, t]) => (
          <button key={f || "todos"} aria-pressed={formato === f} onClick={() => setFormato(f)}
                  className={`rounded-full border px-3 py-1 text-[13px] ${formato === f ? "border-tinta bg-tinta text-papel" : "border-borde bg-papel hover:border-tinta"}`}>{t}</button>
        ))}
      </div>
      {error && <p className="text-carmesi">{String(error)}</p>}
      {!datos && !error && <p>Cargando…</p>}
      {datos && vistas.length === 0 && <p className="text-tinta-suave">No hay propuestas aquí todavía.</p>}
      <div className="flex flex-col gap-4">
        {vistas.map((p) => <Tarjeta key={p.id} p={p} eid={eid} alCambiar={recargar} />)}
      </div>
    </div>
  );
}
