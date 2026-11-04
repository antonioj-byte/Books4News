"use client";

import { useEffect, useRef, useState } from "react";
import { api, type EstadoNewsletter } from "@/lib/api";
import { PASOS_NEWSLETTER, Trabajando } from "@/components/Trabajando";

// «La newsletter del jueves» (4/11): dentro de «¿De qué quieres que hablemos hoy?», con el enfoque «Newsletter». Se pega
// el texto entero; `folio newsletter` corre en un proceso aparte (titular, percha, frases, ilustraciones) y la pieza
// entra escrita en la mesa. La foto de quien firma se sube una vez y vale para todos los jueves.
export function Newsletter({ texto, onHecho }: { texto: string; onHecho: () => void }) {
  const [estado, setEstado] = useState<EstadoNewsletter | null>(null);
  const [etapa, setEtapa] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const archivo = useRef<HTMLInputElement>(null);

  const vigilar = () => {
    let fallos = 0;
    const paso = async () => {
      let e: EstadoNewsletter;
      try { e = await api.newsletter(); fallos = 0; } catch {
        if (++fallos < 6) { setTimeout(paso, 5000); return; }
        setEtapa(null); setError("Se perdió el seguimiento. Recarga la página para ver cómo acabó."); return;
      }
      setEstado(e);
      if (e.trabajo.en_marcha) { setEtapa(e.trabajo.etapa ?? "Trabajando…"); setTimeout(paso, 4000); return; }
      setEtapa(null);
      if (e.trabajo.codigo !== 0) setError(e.trabajo.ultimas_lineas.at(-1) ?? "No se pudo escribir la newsletter.");
      onHecho();
    };
    setTimeout(paso, 3000);
  };

  useEffect(() => {
    api.newsletter().then((e) => {
      setEstado(e);
      if (e.trabajo.en_marcha) { setEtapa(e.trabajo.etapa ?? "Trabajando…"); vigilar(); }
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lanzar = async () => {
    setError(null);
    try { await api.lanzarNewsletter(texto.trim()); } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^\d+ \S+: /, "") : "No se pudo lanzar."); return;
    }
    setEtapa("Empezando…");
    vigilar();
  };

  const subir = async (f: File | undefined) => {
    if (!f) return;
    setSubiendo(true); setError(null);
    try { setEstado(await api.subirFotoNewsletter(f)); } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^\d+ \S+: /, "") : "No se pudo subir la foto.");
    } finally { setSubiendo(false); if (archivo.current) archivo.current.value = ""; }
  };

  const corto = texto.trim().length < 400;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 text-[13.5px]">
        {estado?.foto
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={estado.foto} alt="" className="h-10 w-10 rounded-full object-cover grayscale" />
          : <span className="grid h-10 w-10 place-items-center rounded-full border border-dashed border-borde text-[11px] text-tinta-suave">foto</span>}
        <span className="min-w-0">
          <span className="font-semibold">{estado?.autor ?? "Antonio J. Rodríguez"}</span>
          <span className="text-tinta-suave"> · {estado?.cargo ?? "Director editorial de Alighieria"}</span>
          {!estado?.foto && <span className="block text-carmesi">Falta la foto de quien firma: súbela una vez y vale para todos los jueves.</span>}
        </span>
        <input ref={archivo} id="newsletter-foto" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only"
               onChange={(e) => subir(e.target.files?.[0])} />
        <label htmlFor="newsletter-foto" className="boton-suave cursor-pointer">{subiendo ? "Subiendo…" : estado?.foto ? "Cambiar la foto" : "Subir la foto"}</label>
      </div>
      {etapa
        ? <Trabajando etapa={etapa} pasos={PASOS_NEWSLETTER} />
        : <div className="flex flex-wrap items-center gap-2">
            <button className="boton" onClick={lanzar} disabled={corto}>Escribir la newsletter →</button>
            <span className="text-[12.5px] text-tinta-suave">
              {corto ? "Pega arriba el texto entero de la newsletter." : "Titular entre comillas, percha, cuatro frases ilustradas y el enlace. Unos 3 minutos."}
            </span>
          </div>}
      {error && <p className="text-[14px] text-carmesi">{error}</p>}
    </div>
  );
}
