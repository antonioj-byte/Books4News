"use client";

import { useRef, useState } from "react";
import { api, type EstadoNewsletter } from "@/lib/api";
import { Boton } from "@/components/Boton";
import { FalloTrabajo, PASOS_NEWSLETTER, Trabajando } from "@/components/Trabajando";
import { mensajeError } from "@/lib/errores";
import { useTrabajo } from "@/lib/useTrabajo";

// «La newsletter del jueves» (4/11): dentro de «¿De qué quieres que hablemos hoy?», con el enfoque «Newsletter». Se pega
// el texto entero; `folio newsletter` corre en un proceso aparte (titular, percha, frases, ilustraciones) y la pieza
// entra escrita en la mesa. La foto de quien firma se sube una vez y vale para todos los jueves.
export function Newsletter({ texto, onHecho }: { texto: string; onHecho: () => void }) {
  const [info, setInfo] = useState<EstadoNewsletter | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [errorFoto, setErrorFoto] = useState<string | null>(null);
  const archivo = useRef<HTMLInputElement>(null);
  const t = useTrabajo({
    consultar: async () => { const e = await api.newsletter(); setInfo(e); return e.trabajo; },
    lanzar: () => api.lanzarNewsletter(texto.trim()),
    onHecho: (e) => { if (e.codigo === 0) onHecho(); },
    siFalla: "No se pudo escribir la newsletter.",
    clave: "newsletter",
  });

  const subir = async (f: File | undefined) => {
    if (!f) return;
    setSubiendo(true); setErrorFoto(null);
    try { setInfo(await api.subirFotoNewsletter(f)); } catch (err) {
      setErrorFoto(mensajeError(err, "No se pudo subir la foto."));
    } finally { setSubiendo(false); if (archivo.current) archivo.current.value = ""; }
  };

  const faltan = 400 - texto.trim().length;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 text-[13.5px]">
        {info?.foto
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={info.foto} alt="" className="h-10 w-10 rounded-full object-cover grayscale" />
          : <span className="grid h-10 w-10 place-items-center rounded-full border border-dashed border-borde text-[11px] text-tinta-suave">foto</span>}
        <span className="min-w-0">
          <span className="font-semibold">{info?.autor ?? "Antonio J. Rodríguez"}</span>
          <span className="text-tinta-suave"> · {info?.cargo ?? "Director editorial de Alighieria"}</span>
          {info && !info.foto && <span className="block text-carmesi">Falta la foto de quien firma: súbela una vez y vale para todos los jueves.</span>}
        </span>
        <input ref={archivo} id="newsletter-foto" type="file" accept="image/jpeg,image/png,image/webp" className="sr-only"
               onChange={(e) => subir(e.target.files?.[0])} />
        <label htmlFor="newsletter-foto" className="boton-suave cursor-pointer" aria-busy={subiendo || undefined}>
          {subiendo ? <><span className="girando" aria-hidden />Subiendo…</> : info?.foto ? "Cambiar la foto" : "Subir la foto"}
        </label>
      </div>
      {errorFoto && <p className="text-[13px] text-carmesi" role="alert">{errorFoto}</p>}
      {t.enMarcha
        ? <Trabajando etapa={t.estado?.etapa ?? "Trabajando…"} pasos={PASOS_NEWSLETTER} inicio={t.estado?.inicio} tipico={t.estado?.tipico_s} onCancelar={t.cancelar} />
        : <Boton onClick={t.lanzar} motivo={faltan > 0 ? `Pega arriba el texto entero de la newsletter (faltan ${faltan} caracteres)` : null}
                 coste={`~${Math.round((t.estado?.tipico_s ?? 180) / 60)} min · ~0,10 $ y ~125 créditos`} hecho={null}>
            Escribir la newsletter →
          </Boton>}
      {t.error && !t.enMarcha && <FalloTrabajo fallo={t.error} reintentar={t.lanzar} />}
    </div>
  );
}
