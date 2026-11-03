"use client";

import { useState } from "react";
import { api, type EstadoBuffer } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

// «Programar en Buffer» (2/11): solo en piezas aprobadas. Publicar es hacia fuera, así que hay un paso de
// confirmación en la propia página (el visor no muestra confirm()). Tarda hasta un minuto: pinta el carrusel.
type Modo = "hora" | "cola" | "borrador";
type Red = "instagram" | "linkedin";
const NOMBRE: Record<Red, string> = { instagram: "Instagram", linkedin: "LinkedIn" };

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
  // 3/11 («molaría que mandase también a Buffer LinkedIn»): las dos redes, marcadas por defecto
  const [redes, setRedes] = useState<Red[]>(["instagram", "linkedin"]);
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
        hora: modo === "hora" ? hora.replace("T", " ") : null, borrador: modo === "borrador", reemplazar, redes,
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

  const programadas: [Red, EstadoBuffer["programada"]][] = [["instagram", estado.programada], ["linkedin", estado.linkedin]];
  // Un borrador no se publica solo: se puede programar encima sin borrarlo antes (2/11)
  const ocupadas = programadas.filter(([r, p]) => redes.includes(r) && p && !p.borrador).map(([r]) => r);
  const bloqueada = redes.length === 0 || (ocupadas.length > 0 && !reemplazar);
  return (
    <section className="mx-auto mt-6 max-w-[560px] rounded-[8px] border border-borde bg-panel p-4" aria-labelledby="h-buffer">
      <h3 id="h-buffer" className="antetitulo mb-2">Programar en redes</h3>
      {!estado.disponible ? (
        <p className="text-[13px] text-tinta-suave">Buffer no está configurado en el servidor: {estado.motivo}.</p>
      ) : (
        <div className="flex flex-col gap-3 text-[14px]">
          {programadas.filter(([, p]) => p).map(([r, p]) => p && (
            <p key={r} className="rounded-[6px] bg-papel-hondo px-3 py-2 text-[13px]">
              <strong>{NOMBRE[r]}:</strong>{" "}
              {p.borrador ? "guardada como borrador en Buffer" : p.hora ? `programada para el ${fechaLegible(p.hora)}` : "en la cola de Buffer"}
              {p.canal ? ` · ${p.canal}` : ""}
              {p.version ? ` · versión ${p.version}` : ""}.
              {" "}{p.borrador
                ? "Puedes programarla ya: el borrador se queda en Buffer y conviene borrarlo allí después."
                : "Para cambiarla, bórrala antes en Buffer y marca «Ya la he borrado en Buffer»."}
            </p>
          ))}
          <fieldset className="flex flex-wrap gap-x-4 gap-y-2" disabled={enviando}>
            <legend className="sr-only">Redes</legend>
            {(["instagram", "linkedin"] as Red[]).map((r) => (
              <label key={r} className="flex items-center gap-1.5">
                <input id={`buffer-red-${r}`} type="checkbox" checked={redes.includes(r)}
                       onChange={(e) => { setRedes(e.target.checked ? [...redes, r] : redes.filter((x) => x !== r)); setConfirmando(false); }} />
                {NOMBRE[r]}
              </label>
            ))}
            {redes.includes("linkedin") && <span className="text-[12px] text-tinta-suave">En LinkedIn va en imágenes (no admite vídeo junto a imágenes).</span>}
          </fieldset>
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
          {ocupadas.length > 0 && (
            <label className="flex items-center gap-1.5 text-[13px]">
              <input id="buffer-reemplazar" type="checkbox" checked={reemplazar} onChange={(e) => setReemplazar(e.target.checked)} disabled={enviando} />
              Ya la he borrado en Buffer
            </label>
          )}
          {!confirmando ? (
            <button className="boton-suave self-start disabled:cursor-not-allowed disabled:opacity-40" disabled={enviando || bloqueada}
                    title={redes.length === 0 ? "Elige al menos una red" : bloqueada ? `Ya está en ${ocupadas.map((r) => NOMBRE[r]).join(" y ")}: bórrala antes en Buffer y marca «Ya la he borrado en Buffer», o desmarca esa red` : undefined}
                    onClick={() => setConfirmando(true)}>
              Programar en Buffer
            </button>
          ) : (
            <div className="flex flex-wrap items-center gap-2 rounded-[6px] border border-tinta px-3 py-2">
              <span className="text-[13px]">¿Mandar la versión actual a {redes.map((r) => NOMBRE[r]).join(" y ")} {resumen}?</span>
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
