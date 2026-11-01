"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Material } from "@/lib/api";

// Materiales extra de la pieza (2/11): fotos, PDF o texto que el editor del chat ve en cada turno. Una foto con
// crédito puede ir en la pieza si se le pide al editor («usa la foto que he subido como retrato»).
export function MaterialesChat({ eid, pid }: { eid: number; pid: string }) {
  const [lista, setLista] = useState<Material[]>([]);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [credito, setCredito] = useState("");
  const [nota, setNota] = useState("");
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  const cargar = () => api.materiales(eid, pid).then(setLista).catch(() => setLista([]));
  useEffect(() => { cargar(); }, [eid, pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const elegir = (f: File | undefined) => {
    setError(null);
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { setError("El archivo pasa de 8 MB."); return; }
    setArchivo(f); setCredito(""); setNota("");
  };
  const subir = async () => {
    if (!archivo) return;
    setSubiendo(true); setError(null);
    try {
      await api.subirMaterial(eid, pid, archivo, credito.trim(), nota.trim());
      setArchivo(null); await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo subir");
    } finally { setSubiendo(false); }
  };
  const borrar = async (m: Material) => { await api.borrarMaterial(eid, pid, m.id).catch(() => null); cargar(); };
  const esFoto = archivo?.type.startsWith("image/");

  return (
    <div className="flex flex-col gap-2 text-[13px]">
      {lista.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {lista.map((m) => (
            <li key={m.id} className="flex items-center gap-2 rounded-[10px] border border-borde bg-panel p-1.5">
              {m.tipo === "imagen"
                // eslint-disable-next-line @next/next/no-img-element -- miniatura servida por la api
                ? <img src={api.urlMaterial(eid, pid, m.id)} alt="" className="h-10 w-10 shrink-0 rounded-[6px] object-cover" />
                : <span className="dato flex h-10 w-10 shrink-0 items-center justify-center rounded-[6px] bg-papel uppercase">{m.tipo === "pdf" ? "PDF" : "TXT"}</span>}
              <div className="min-w-0 flex-1 leading-tight">
                <a href={api.urlMaterial(eid, pid, m.id)} target="_blank" rel="noreferrer" className="block truncate font-semibold hover:underline">{m.nombre}</a>
                <span className="block truncate text-tinta-suave">{m.credito ? `© ${m.credito}` : m.tipo === "imagen" ? "Sin crédito: no se puede publicar" : m.nota || "Para que lo lea el editor"}</span>
              </div>
              <span className="dato shrink-0 text-tinta-suave">{m.id}</span>
              <button onClick={() => borrar(m)} aria-label={`Borrar ${m.nombre}`} className="shrink-0 px-1.5 text-tinta-suave hover:text-carmesi">✕</button>
            </li>
          ))}
        </ul>
      )}
      {archivo ? (
        <div className="flex flex-col gap-1.5 rounded-[12px] border border-borde bg-panel p-2.5">
          <span className="truncate font-semibold">{archivo.name}</span>
          <input id={`credito-${pid}`} value={credito} onChange={(e) => setCredito(e.target.value)}
                 placeholder={esFoto ? "Crédito (obligatorio para publicarla): «Foto: Ana Pérez · cortesía de Anagrama»" : "Crédito o fuente (opcional)"}
                 className="rounded-[8px] border border-borde bg-papel px-2 py-1.5 outline-none focus:border-tinta" />
          <input id={`nota-${pid}`} value={nota} onChange={(e) => setNota(e.target.value)}
                 placeholder="Nota para el editor: qué es y para qué sirve"
                 className="rounded-[8px] border border-borde bg-papel px-2 py-1.5 outline-none focus:border-tinta" />
          <div className="flex gap-2">
            <button onClick={subir} disabled={subiendo} className="boton">{subiendo ? "Subiendo…" : "Subir"}</button>
            <button onClick={() => setArchivo(null)} disabled={subiendo} className="boton-suave">Cancelar</button>
          </div>
        </div>
      ) : (
        <button onClick={() => entrada.current?.click()} className="self-start text-tinta-suave underline-offset-2 hover:text-tinta hover:underline">
          + Añadir material (foto, PDF o texto)
        </button>
      )}
      <input ref={entrada} type="file" hidden accept="image/jpeg,image/png,image/webp,application/pdf,text/plain,text/markdown,.md,.txt"
             onChange={(e) => { elegir(e.target.files?.[0]); e.target.value = ""; }} />
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}
