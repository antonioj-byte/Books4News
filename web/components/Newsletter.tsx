"use client";

import { useRef, useState } from "react";
import { api, type EstadoNewsletter } from "@/lib/api";
import { Boton } from "@/components/Boton";
import { FalloTrabajo, PASOS_NEWSLETTER, Trabajando } from "@/components/Trabajando";
import { mensajeError } from "@/lib/errores";
import { useTrabajo } from "@/lib/useTrabajo";

type Firma = EstadoNewsletter["firmantes"][number];
const CASA = "casa";

// «La newsletter del jueves» (4/11): dentro de «¿De qué quieres que hablemos hoy?», con el enfoque «Newsletter». Se pega
// el texto entero; `folio newsletter` corre en un proceso aparte (titular, percha, frases, ilustraciones) y la pieza
// entra escrita en la mesa. La foto de quien firma se sube una vez y vale para todos los jueves.
// «Opinión» (7/11, a petición del usuario: «quiero meter un tema de opinión de Diego… es básicamente como la newsletter
// del jueves»): el mismo carrusel con otra firma, que se elige o se añade aquí (nombre, cargo, dónde se publica y foto).
export function Newsletter({ texto, onHecho, formato = "newsletter" }: { texto: string; onHecho: () => void; formato?: "newsletter" | "opinion" }) {
  const opinion = formato === "opinion";
  const [info, setInfo] = useState<EstadoNewsletter | null>(null);
  const [elegida, setElegida] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [errorFoto, setErrorFoto] = useState<string | null>(null);
  // Con slug, se corrige una firma que ya existe (7/11: «no puedo cambiar la firma»); sin él, es una nueva
  const [nueva, setNueva] = useState<{ nombre: string; cargo: string; publicacion: string; url: string; slug?: string | null } | null>(null);
  const [guardando, setGuardando] = useState(false);
  const archivo = useRef<HTMLInputElement>(null);

  const firmas = info?.firmantes ?? [];
  const otras = firmas.filter((f) => f.slug !== CASA);
  const firma: Firma | undefined = opinion
    ? firmas.find((f) => f.slug === elegida) ?? otras[0] ?? firmas[0]
    : firmas.find((f) => f.slug === CASA);

  const t = useTrabajo({
    consultar: async () => { const e = await api.newsletter(); setInfo(e); return e.trabajo; },
    lanzar: () => api.lanzarNewsletter(texto.trim(), formato, opinion ? firma?.slug : undefined),
    onHecho: (e) => { if (e.codigo === 0) onHecho(); },
    siFalla: opinion ? "No se pudo escribir la opinión." : "No se pudo escribir la newsletter.",
    clave: "newsletter",
  });

  const subir = async (f: File | undefined) => {
    if (!f || !firma) return;
    setSubiendo(true); setErrorFoto(null);
    try { setInfo(firma.slug === CASA ? await api.subirFotoNewsletter(f) : await api.subirFotoFirma(firma.slug, f)); } catch (err) {
      setErrorFoto(mensajeError(err, "No se pudo subir la foto."));
    } finally { setSubiendo(false); if (archivo.current) archivo.current.value = ""; }
  };

  const guardarFirma = async () => {
    if (!nueva || nueva.nombre.trim().length < 2) return;
    setGuardando(true); setErrorFoto(null);
    try {
      const e = await api.nuevaFirma(nueva);
      setInfo(e);
      const n = nueva.nombre.trim().toLowerCase();
      setElegida(nueva.slug ?? e.firmantes.find((f) => f.nombre.toLowerCase() === n)?.slug ?? null);
      setNueva(null);
    } catch (err) {
      setErrorFoto(mensajeError(err, "No se pudo guardar la firma."));
    } finally { setGuardando(false); }
  };

  const faltan = 400 - texto.trim().length;
  const campo = "rounded-[10px] border border-borde bg-papel px-2.5 py-1.5 text-[14px] outline-none focus:border-tinta";
  return (
    <div className="flex flex-col gap-3">
      {opinion && (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Quién firma">
          <span className="text-[13px] text-tinta-suave">Firma:</span>
          {firmas.map((f) => (
            <button key={f.slug} aria-pressed={firma?.slug === f.slug} onClick={() => { setElegida(f.slug); setNueva(null); }}
                    className={`rounded-full border px-3 py-1 text-[13px] ${firma?.slug === f.slug ? "border-tinta bg-tinta text-papel" : "border-borde bg-papel hover:border-tinta"}`}>
              {f.nombre}
            </button>
          ))}
          <button className="rounded-full border border-dashed border-borde px-3 py-1 text-[13px] hover:border-tinta"
                  onClick={() => setNueva(nueva && !nueva.slug ? null : { nombre: "", cargo: "", publicacion: "", url: "" })} aria-expanded={!!nueva && !nueva.slug}>
            + Otra firma
          </button>
          {firma && firma.slug !== CASA && (
            <button className="rounded-full border border-borde px-3 py-1 text-[13px] hover:border-tinta"
                    onClick={() => setNueva(nueva?.slug ? null : { nombre: firma.nombre, cargo: firma.cargo ?? "", publicacion: firma.publicacion ?? "", url: firma.url ?? "", slug: firma.slug })}
                    aria-expanded={!!nueva?.slug}>
              Corregir la firma
            </button>
          )}
        </div>
      )}
      {nueva && (
        <div className="grid gap-2 rounded-[12px] border border-borde p-3 sm:grid-cols-2">
          <input className={campo} placeholder="Nombre (Diego …)" value={nueva.nombre} autoFocus
                 onChange={(e) => setNueva({ ...nueva, nombre: e.target.value })} aria-label="Nombre" />
          <input className={campo} placeholder="Cargo (p. ej. CEO de Alighieria)" value={nueva.cargo}
                 onChange={(e) => setNueva({ ...nueva, cargo: e.target.value })} aria-label="Cargo" />
          <input className={campo} placeholder="Dónde se publica entero (opcional)" value={nueva.publicacion}
                 onChange={(e) => setNueva({ ...nueva, publicacion: e.target.value })} aria-label="Dónde se publica" />
          <input className={campo} placeholder="Enlace (opcional, sin https)" value={nueva.url}
                 onChange={(e) => setNueva({ ...nueva, url: e.target.value })} aria-label="Enlace" />
          <div className="flex items-center gap-2 sm:col-span-2">
            <button className="boton-suave" onClick={guardarFirma} disabled={guardando || nueva.nombre.trim().length < 2} aria-busy={guardando || undefined}>
              {guardando ? "Guardando…" : nueva.slug ? "Guardar los cambios" : "Guardar la firma"}
            </button>
            <span className="text-[12.5px] text-tinta-suave">{nueva.slug
              ? "Las piezas ya escritas con esta firma la toman al momento."
              : "Sin enlace, el cierre enseña su nombre y su cargo en vez de «Léelo entero en…»."}</span>
          </div>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3 text-[13.5px]">
        {firma?.foto
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={firma.foto} alt="" className="h-10 w-10 rounded-full object-cover grayscale" />
          : <span className="grid h-10 w-10 place-items-center rounded-full border border-dashed border-borde text-[11px] text-tinta-suave">foto</span>}
        <span className="min-w-0">
          <span className="font-semibold">{firma?.nombre ?? info?.autor ?? "…"}</span>
          {firma?.cargo && <span className="text-tinta-suave"> · {firma.cargo}</span>}
          {info && firma && !firma.foto && <span className="block text-carmesi">
            Falta la foto de quien firma: súbela una vez y vale para todas sus piezas.</span>}
        </span>
        <input ref={archivo} id={`foto-firma-${formato}`} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only"
               onChange={(e) => subir(e.target.files?.[0])} />
        {firma && <label htmlFor={`foto-firma-${formato}`} className="boton-suave cursor-pointer" aria-busy={subiendo || undefined}>
          {subiendo ? <><span className="girando" aria-hidden />Subiendo…</> : firma.foto ? "Cambiar la foto" : "Subir la foto"}
        </label>}
      </div>
      {errorFoto && <p className="text-[13px] text-carmesi" role="alert">{errorFoto}</p>}
      {t.enMarcha
        ? <Trabajando etapa={t.estado?.etapa ?? "Trabajando…"} pasos={PASOS_NEWSLETTER} inicio={t.estado?.inicio} tipico={t.estado?.tipico_s} onCancelar={t.cancelar} />
        : <Boton onClick={t.lanzar}
                 motivo={faltan > 0 ? `Pega arriba el texto entero (faltan ${faltan} caracteres)`
                   : opinion && !otras.length && !elegida ? "Añade antes la firma con «+ Otra firma»" : null}
                 coste={`~${Math.round((t.estado?.tipico_s ?? 180) / 60)} min · ~0,10 $ y ~125 créditos`} hecho={null}>
            {opinion ? "Escribir la opinión →" : "Escribir la newsletter →"}
          </Boton>}
      {t.error && !t.enMarcha && <FalloTrabajo fallo={t.error} reintentar={t.lanzar} />}
    </div>
  );
}
