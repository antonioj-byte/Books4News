"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SeguirTrabajo } from "@/components/SeguirTrabajo";
import { FalloTrabajo, PASOS_TEMA, Trabajando } from "@/components/Trabajando";
import { api, type PropuestaDelFondo, type TemaCreado } from "@/lib/api";
import { conDeshacer } from "@/lib/avisos";
import { fraseDeFallo, mensajeError } from "@/lib/errores";
import { mirarTrabajos } from "@/lib/trabajos";
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

function Tarjeta({ p, eid, alCambiar, alOcultar }: { p: PropuestaDelFondo; eid: number | null; alCambiar: () => void; alOcultar: (oculta: boolean) => void }) {
  const [enviando, setEnviando] = useState(false);
  const [siguiendo, setSiguiendo] = useState(false);
  const [mensaje, setMensaje] = useState<React.ReactNode>(null);
  // Llevarla a la mesa va en segundo plano (4/11, usabilidad): se puede salir de la página y seguirla en la bandeja
  const escribir = async () => {
    if (!eid || enviando || siguiendo) return;
    setEnviando(true); setMensaje(null);
    try { await api.escribirDelFondo(p.id, eid, true); setSiguiendo(true); mirarTrabajos(); }
    catch (e) { setMensaje(<span className="text-carmesi">{mensajeError(e, "No se pudo llevar a la mesa.")}</span>); }
    finally { setEnviando(false); }
  };
  const alAcabar = (r: TemaCreado | null) => {
    setSiguiendo(false);
    if (r) setMensaje(r.pieza_id
      ? <>En la mesa como <Link className="underline" href={`/pieza/${eid}/${r.pieza_id}`}>{r.pieza_id}</Link> · {r.respuesta}</>
      : <>El jefe pregunta antes de proponer: {r.preguntas.join(" ")} Contéstale en «¿De qué quieres que hablemos hoy?», en la mesa.</>);
    alCambiar();
  };
  // Descartar sin preguntar, con «Deshacer» unos segundos («deshacer antes que confirmar»)
  const descartar = () => {
    alOcultar(true);
    conDeshacer({ texto: "Propuesta descartada.", hacer: async () => { await api.descartarDelFondo(p.id); alCambiar(); },
                  alDeshacer: () => alOcultar(false), alFallar: (e) => setMensaje(<span className="text-carmesi">{mensajeError(e, "No se pudo descartar.")}</span>) });
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
      {p.estado === "disponible" && !siguiendo && (
        <div className="flex flex-wrap items-center gap-2">
          <button className="boton" onClick={escribir} disabled={enviando || !eid} aria-busy={enviando || undefined}>
            Escribir pieza<span className="boton__coste">~1–2 min · ~0,10 $</span>
          </button>
          <button className="boton-suave boton--peligro" onClick={descartar} disabled={enviando}>Descartar</button>
          {!eid && <span className="motivo">Hace falta una mesa del día para llevarla</span>}
        </div>
      )}
      {(siguiendo || p.estado === "disponible") && (
        <SeguirTrabajo key={siguiendo ? "s" : "n"} clave={`fondo-${p.id}`} pasos={PASOS_TEMA} rotulo="Llevando a la mesa"
                       siFalla="No se pudo llevar a la mesa." onHecho={(r) => alAcabar(r as TemaCreado | null)} />
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
  const [ocultas, setOcultas] = useState<Set<number>>(new Set());
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
    try { await api.prepararFondo(1); recargar(); mirarTrabajos(); } catch (e) { setAviso(mensajeError(e, "No se pudo lanzar la tanda.")); } finally { setLanzando(false); }
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
        {preparando
          ? <Trabajando etapa={datos?.preparando?.etapa ?? "El jefe propone, el evaluador de puentes filtra y se verifican los libros"}
                        rotulo="Preparando una tanda" inicio={datos?.preparando?.inicio} tipico={datos?.preparando?.tipico_s} />
          : <button className="boton" onClick={preparar} disabled={lanzando} aria-busy={lanzando || undefined}>
              Preparar una tanda<span className="boton__coste">25 · ~15 min · ~1,40 $</span>
            </button>}
        {aviso && <span className="text-[13px] text-carmesi">{aviso}</span>}
      </div>
      {datos?.preparando && !preparando && (
        // Cómo acabó la última tanda (2/11: «le di a preparar tanda pero no ha hecho nada»: la página no lo decía)
        datos.preparando.codigo === 0
          ? <details className="mb-6 rounded-[10px] border border-borde bg-panel px-4 py-3 text-[13px]">
              <summary className="cursor-pointer font-semibold">La última tanda terminó bien</summary>
              <pre className="mt-1 whitespace-pre-wrap font-mono text-[12px] text-tinta-suave">{datos.preparando.ultimas_lineas.join("\n") || "(sin salida)"}</pre>
            </details>
          : <div className="mb-6"><FalloTrabajo fallo={{ ...fraseDeFallo(datos.preparando.ultimas_lineas), titulo: `La última tanda falló: ${fraseDeFallo(datos.preparando.ultimas_lineas, "mira los detalles.").titulo}` }} reintentar={preparar} /></div>
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
      {error && <p className="text-carmesi" role="alert">{error}</p>}
      {!datos && !error && <div className="flex flex-col gap-4" aria-busy="true">{[0, 1, 2].map((i) => <div key={i} className="esqueleto h-44 w-full" />)}</div>}
      {datos && vistas.length === 0 && <p className="text-tinta-suave">No hay propuestas aquí todavía.</p>}
      <div className="flex flex-col gap-4">
        {vistas.filter((p) => !ocultas.has(p.id)).map((p) => (
          <Tarjeta key={p.id} p={p} eid={eid} alCambiar={recargar}
                   alOcultar={(o) => setOcultas((x) => { const n = new Set(x); if (o) n.add(p.id); else n.delete(p.id); return n; })} />
        ))}
      </div>
    </div>
  );
}
