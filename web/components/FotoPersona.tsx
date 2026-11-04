"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { mensajeError } from "@/lib/errores";

// La foto del autor o protagonista, subida desde la ficha (3/11, a petición del usuario: «muchas veces no la
// encuentra; yo puedo buscar… ahora mismo es bastante calvario»). Va como retrato al momento, sin pasar por el chat.
// Sin foto, se enseña abierta y en aviso; con foto, como un enlace discreto para cambiarla.
export function FotoPersona({ eid, pid, persona, credito, escrita, onHecho }: {
  eid: number; pid: string; persona: string; credito: string | null; escrita: boolean; onHecho: () => void;
}) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [modificable, setModificable] = useState(false);
  const [tratamiento, setTratamiento] = useState<"foto" | "papel" | "escena">("foto");
  const [subiendo, setSubiendo] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const entrada = useRef<HTMLInputElement>(null);
  const sinFoto = !credito;

  const elegir = (f: File | undefined) => {
    setError(null); setMensaje(null);
    if (!f) return;
    if (!f.type.startsWith("image/")) { setError("Tiene que ser una foto (JPEG, PNG o WebP)."); return; }
    if (f.size > 8 * 1024 * 1024) { setError("La foto pasa de 8 MB."); return; }
    setArchivo(f); setVista(URL.createObjectURL(f));
  };
  const cancelar = () => { setArchivo(null); setVista(null); setError(null); };
  const subir = async () => {
    if (!archivo) return;
    // Sin crédito no se puede publicar: se dice, en vez de dejar el botón apagado con el cursor de «cargando» (3/11)
    if (!texto.trim()) { setError("Escribe el crédito de la foto: va en el pie de la publicación."); return; }
    setSubiendo(true); setError(null);
    try {
      const r = await api.subirFotoPersona(eid, pid, archivo, texto.trim(), modificable, modificable ? tratamiento : "foto");
      setMensaje(r.nota); cancelar(); setTexto(""); onHecho();
    } catch (e) {
      setError(mensajeError(e, "No se pudo subir la foto."));
    } finally { setSubiendo(false); }
  };

  return (
    <div className={`mx-auto mb-4 flex max-w-[560px] flex-col gap-2 rounded-[6px] px-4 py-2.5 text-[14px] ${sinFoto ? "border border-carmesi" : "border border-borde bg-panel"}`}>
      {!archivo && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="min-w-0 flex-1">
            {sinFoto
              ? <><b>Sin foto de {persona}.</b> {escrita ? "Si la encuentras, súbela y va a la portada." : "Si la encuentras, súbela: el arte la usará al escribir la pieza."}</>
              : <><b>Foto de {persona}</b> <span className="text-tinta-suave">· © {credito}</span></>}
          </span>
          <button onClick={() => entrada.current?.click()} className={sinFoto ? "boton" : "boton-suave"}>
            {sinFoto ? "Subir foto" : "Cambiar foto"}
          </button>
        </div>
      )}
      {archivo && (
        <div className="flex flex-col gap-2">
          <div className="flex items-start gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local */}
            {vista && <img src={vista} alt="" className="h-20 w-16 shrink-0 rounded-[4px] object-cover" />}
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <label htmlFor={`credito-foto-${pid}`} className="font-semibold">Foto de {persona}</label>
              <input id={`credito-foto-${pid}`} value={texto} onChange={(e) => { setTexto(e.target.value); setError(null); }}
                     onKeyDown={(e) => { if (e.key === "Enter") subir(); }} autoFocus
                     placeholder="Crédito (obligatorio): «Foto: Ana Pérez · cortesía de Anagrama»"
                     className="rounded-[8px] border border-borde bg-papel px-2 py-1.5 outline-none focus:border-tinta" />
            </div>
          </div>
          <label className="flex items-start gap-2">
            <input id={`modificable-${pid}`} type="checkbox" checked={modificable} onChange={(e) => setModificable(e.target.checked)} className="mt-1" />
            <span>Tenemos derecho a modificarla <span className="text-tinta-suave">(libre o propia; las fotos de prensa de las editoriales, no)</span></span>
          </label>
          {modificable && escrita && (
            <fieldset className="flex flex-wrap gap-x-4 gap-y-1">
              <legend className="sr-only">Cómo va en la portada</legend>
              {([["foto", "Tal cual"], ["papel", "Collage sobre papel"], ["escena", "Collage con escena (~25 créditos)"]] as const).map(([v, t]) => (
                <label key={v} className="flex items-center gap-1.5">
                  <input type="radio" name={`tratamiento-${pid}`} checked={tratamiento === v} onChange={() => setTratamiento(v)} /> {t}
                </label>
              ))}
            </fieldset>
          )}
          <div className="flex gap-2">
            <button onClick={subir} disabled={subiendo} className="boton">
              {subiendo ? (tratamiento === "escena" && modificable ? "Dibujando la escena…" : "Subiendo…") : "Poner en la pieza"}
            </button>
            <button onClick={cancelar} disabled={subiendo} className="boton-suave">Cancelar</button>
          </div>
        </div>
      )}
      <input ref={entrada} type="file" hidden accept="image/jpeg,image/png,image/webp"
             onChange={(e) => { elegir(e.target.files?.[0]); e.target.value = ""; }} />
      {mensaje && <p className="text-[13px]">{mensaje}</p>}
      {error && <p className="text-[13px] text-carmesi">{error}</p>}
    </div>
  );
}
