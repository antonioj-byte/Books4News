"use client";

import { useState } from "react";
import { api, type EstadoBuffer } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

// «Programar en Buffer» (2/11): solo en piezas aprobadas. Publicar es hacia fuera, así que hay un paso de
// confirmación en la propia página (el visor no muestra confirm()). Tarda hasta un minuto: pinta el carrusel.
type Modo = "hora" | "cola" | "borrador";

const manana930 = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 30, 0, 0);
  const dos = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}T09:30`;
};

const fechaLegible = (iso: string) =>
  new Date(iso).toLocaleString("es-ES", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

export function ProgramarBuffer({ eid, pid }: { eid: number; pid: string }) {
  const { datos, recargar } = useDatos(`buffer:${eid}/${pid}`, () => api.buffer(eid, pid));
  const [modo, setModo] = useState<Modo>("hora");
  const [hora, setHora] = useState(manana930);
  const [reemplazar, setReemplazar] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<EstadoBuffer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const estado = resultado ?? datos;
  if (!estado) return null;

  const resumen = modo === "borrador" ? "como borrador en Buffer (no se publica)"
    : modo === "cola" ? "en la cola de Buffer (sale en su próximo hueco)"
    : `para el ${fechaLegible(hora)}`;

  const enviar = async () => {
    setEnviando(true);
    setError(null);
    try {
      const r = await api.programarBuffer(eid, pid, {
        hora: modo === "hora" ? hora.replace("T", " ") : null, borrador: modo === "borrador", reemplazar,
      });
      setResultado(r);
      setReemplazar(false);
      recargar();
    } catch (err) {
      const texto = err instanceof Error ? err.message : String(err);
      setError(texto.replace(/^\d+ \S+: /, "") || "No se pudo programar. Prueba otra vez en un momento.");
    } finally {
      setEnviando(false);
      setConfirmando(false);
    }
  };

  const yaProgramada = estado.programada;
  return (
    <section className="mx-auto mt-6 max-w-[560px] rounded-[8px] border border-borde bg-panel p-4" aria-labelledby="h-buffer">
      <h3 id="h-buffer" className="antetitulo mb-2">Programar en Instagram</h3>
      {!estado.disponible ? (
        <p className="text-[13px] text-tinta-suave">Buffer no está configurado en el servidor: {estado.motivo}.</p>
      ) : (
        <div className="flex flex-col gap-3 text-[14px]">
          {yaProgramada && (
            <p className="rounded-[6px] bg-papel-hondo px-3 py-2 text-[13px]">
              {yaProgramada.borrador ? "Guardada como borrador en Buffer" : yaProgramada.hora ? `Programada para el ${fechaLegible(yaProgramada.hora)}` : "En la cola de Buffer"}
              {yaProgramada.canal ? ` · ${yaProgramada.canal}` : ""}
              {yaProgramada.version ? ` · versión ${yaProgramada.version}` : ""}.
              {" "}Para cambiarla, bórrala antes en Buffer y marca «Ya la he borrado en Buffer».
            </p>
          )}
          <fieldset className="flex flex-wrap gap-x-4 gap-y-2" disabled={enviando}>
            <legend className="sr-only">Cuándo</legend>
            {([["hora", "A una hora"], ["cola", "A la cola"], ["borrador", "Solo borrador"]] as [Modo, string][]).map(([v, t]) => (
              <label key={v} className="flex items-center gap-1.5">
                <input id={`buffer-modo-${v}`} type="radio" name="buffer-modo" checked={modo === v} onChange={() => { setModo(v); setConfirmando(false); }} />
                {t}
              </label>
            ))}
          </fieldset>
          {modo === "hora" && (
            <label className="flex flex-wrap items-center gap-2 text-[13px]">
              Hora de Madrid
              <input id="buffer-hora" type="datetime-local" value={hora} onChange={(e) => { setHora(e.target.value); setConfirmando(false); }}
                     className="rounded-[6px] border border-borde bg-papel px-2 py-1 font-mono text-[13px]" disabled={enviando} />
            </label>
          )}
          {yaProgramada && (
            <label className="flex items-center gap-1.5 text-[13px]">
              <input id="buffer-reemplazar" type="checkbox" checked={reemplazar} onChange={(e) => setReemplazar(e.target.checked)} disabled={enviando} />
              Ya la he borrado en Buffer
            </label>
          )}
          {!confirmando ? (
            <button className="boton-suave self-start" disabled={enviando || (!!yaProgramada && !reemplazar)} onClick={() => setConfirmando(true)}>
              Programar en Buffer
            </button>
          ) : (
            <div className="flex flex-wrap items-center gap-2 rounded-[6px] border border-tinta px-3 py-2">
              <span className="text-[13px]">¿Mandar la versión actual {resumen}?</span>
              <button className="boton-suave" onClick={enviar} disabled={enviando}>{enviando ? "Enviando…" : "Sí, programar"}</button>
              <button className="text-[13px] underline" onClick={() => setConfirmando(false)} disabled={enviando}>Cancelar</button>
            </div>
          )}
          {enviando && <p className="dato">Preparando el carrusel y enviándolo a Buffer · hasta un minuto</p>}
          {resultado?.mensaje && <p className="text-[13px] text-verde" role="status">{resultado.mensaje}</p>}
          {error && <p className="text-[13px] text-carmesi" role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
