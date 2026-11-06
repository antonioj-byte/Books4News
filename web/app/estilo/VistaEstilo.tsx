"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, type Ejemplo, type LibroEstilo } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { Boton } from "@/components/Boton";
import { Trabajando } from "@/components/Trabajando";
import { mensajeError } from "@/lib/errores";
import { avisar } from "@/lib/avisos";
import { mirarTrabajos } from "@/lib/trabajos";

// El libro de estilo vivo (6/11, a petición del usuario: «activar un proceso de retroalimentación permanente… cada línea
// de código es un nuevo if»): las fichas que cumple cada rol, con su ejemplo, su prueba en el banco y su encargo de
// código; y los ejemplos de la redacción (tus ediciones) que aprenden el guionista y el chat.
type Rol = LibroEstilo["roles"][number];
type Patron = Rol["fichas"][number];

const ESTADO: Record<string, { texto: string; clase: string }> = {
  aceptada: { texto: "Activa · desde la Memoria", clase: "border-carmesi text-carmesi" },
  aplicada: { texto: "Activa · escrita en el prompt", clase: "border-tinta" },
  propuesta: { texto: "Propuesta", clase: "border-borde text-tinta-suave" },
  retirada: { texto: "Retirada", clase: "border-borde text-tinta-suave line-through" },
};

type Prueba = { veredicto: string; con?: number; sin?: number; nota?: string; coste_usd?: number; fecha?: string };
const leerPrueba = (f: Patron): Prueba | null => { try { return f.prueba ? JSON.parse(f.prueba) : null; } catch { return null; } };
const VEREDICTO: Record<string, string> = {
  mejora: "Mejora las piezas", igual: "No cambia nada visible", empeora: "Empeora las piezas: revísala", sin_banco: "Sin piezas para probar",
};

function Ficha({ f, rol, probando, alProbar, recargar }: { f: Patron; rol: string; probando: boolean; alProbar: () => void; recargar: () => void }) {
  const p = leerPrueba(f);
  const activa = f.estado === "aceptada" || f.estado === "aplicada";
  const probable = (f.destino === "guionista" || f.destino === "formatos") && f.estado === "aceptada";
  const accion = async (fn: () => Promise<{ avisos: string[] }>, hecho: string) => {
    try { const r = await fn(); avisar({ tipo: "ok", texto: [hecho, ...r.avisos].join(" · ") }); recargar(); }
    catch (e) { avisar({ tipo: "mal", texto: mensajeError(e) }); }
  };
  return (
    <article className={`panel flex flex-col gap-2 p-4 ${f.estado === "retirada" ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-[0.1em] ${ESTADO[f.estado]?.clase ?? "border-borde"}`}>
          {ESTADO[f.estado]?.texto ?? f.estado}
        </span>
        <span className="font-mono text-[11px] text-tinta-suave">#{f.id} · {f.origen === "conversacion" ? "pedido en conversación" : f.origen === "poda" ? "poda" : `${f.veces} análisis`} · {f.actualizado_en.slice(0, 10)}</span>
        {f.destino === "formatos" && <span className="font-mono text-[11px] text-tinta-suave">formatos</span>}
      </div>
      <p className="text-[15px] leading-snug">{f.propuesta}</p>
      {(f.ejemplo_bueno || f.ejemplo_malo) && (
        <div className="grid gap-1.5 text-[13px] sm:grid-cols-2">
          {f.ejemplo_bueno && <p className="rounded-[6px] bg-papel-hondo px-2.5 py-1.5"><b>Así sí:</b> «{f.ejemplo_bueno}»</p>}
          {f.ejemplo_malo && <p className="rounded-[6px] bg-papel-hondo px-2.5 py-1.5"><b>Así no:</b> «{f.ejemplo_malo}»</p>}
        </div>
      )}
      {p && (
        <p className={`text-[13px] ${p.veredicto === "empeora" ? "text-carmesi" : "text-tinta-suave"}`}>
          Prueba en el banco ({p.fecha}): <b>{VEREDICTO[p.veredicto] ?? p.veredicto}</b>
          {p.con !== undefined && <> · con la ficha {p.con}, sin ella {p.sin} (idea y voz, de 1 a 5)</>}{p.nota && <> · {p.nota}</>}
        </p>
      )}
      {f.encargo && (
        <p className="text-[13px] text-tinta-suave">Encargo de código: {f.encargo.startsWith("http")
          ? <a className="underline" href={f.encargo} target="_blank" rel="noreferrer">la issue en GitHub</a>
          : f.encargo}</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {activa && <Boton tipo="secundario" hecho={null} onClick={() => accion(() => api.retirarFicha(f.id), "Ficha retirada")}>Retirar</Boton>}
        {f.estado === "retirada" && <Boton tipo="secundario" hecho={null} onClick={() => accion(() => api.reactivarFicha(f.id), "Ficha activa otra vez")}>Reactivar</Boton>}
        {probable && !probando && (
          <button className="boton-suave" onClick={alProbar}>
            {p ? "Probar otra vez" : "Probar en el banco"}<span className="boton__coste">~0,30 $ · unos minutos</span>
          </button>
        )}
        {f.estado === "aplicada" && rol !== "codigo" && <span className="motivo">Retirarla encarga quitarla del prompt</span>}
      </div>
    </article>
  );
}

function SeccionRol({ r, probando, probar, recargar }: { r: Rol; probando: number | null; probar: (id: number) => void; recargar: () => void }) {
  const [verTodas, setVerTodas] = useState(false);
  const activas = r.fichas.filter((f) => f.estado === "aceptada" || f.estado === "aplicada");
  const resto = r.fichas.filter((f) => !(f.estado === "aceptada" || f.estado === "aplicada"));
  const sobra = r.activas > r.tope;
  return (
    <section className="mb-10">
      <div className="mb-3 flex flex-wrap items-baseline gap-3">
        <h2 className="text-[22px] font-semibold">{r.nombre}</h2>
        <span className={`font-mono text-[12px] ${sobra ? "text-carmesi" : "text-tinta-suave"}`}>
          {r.activas} activas de {r.tope}{sobra && " · toca podar"}
        </span>
      </div>
      {activas.length === 0 && <p className="text-[14px] text-tinta-suave">Ninguna ficha activa.</p>}
      <div className="flex flex-col gap-3">
        {(verTodas ? activas : activas.slice(0, 6)).map((f) => (
          <Ficha key={f.id} f={f} rol={r.id} probando={probando !== null} alProbar={() => probar(f.id)} recargar={recargar} />
        ))}
      </div>
      {activas.length > 6 && (
        <button className="boton-suave mt-3" onClick={() => setVerTodas(!verTodas)}>{verTodas ? "Ver menos" : `Ver las ${activas.length}`}</button>
      )}
      {resto.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[13px] text-tinta-suave">Propuestas y retiradas · {resto.length}</summary>
          <div className="mt-3 flex flex-col gap-3">
            {resto.map((f) => <Ficha key={f.id} f={f} rol={r.id} probando={probando !== null} alProbar={() => probar(f.id)} recargar={recargar} />)}
          </div>
        </details>
      )}
    </section>
  );
}

function Ejemplos({ ejemplos, candidatos, max, recargar }: { ejemplos: Ejemplo[]; candidatos: number; max: number; recargar: () => void }) {
  const activos = ejemplos.filter((e) => e.estado === "activo");
  const decidir = async (e: Ejemplo, estado: "activo" | "retirado") => {
    try { await api.decidirEjemplo(e.id, estado); recargar(); } catch (err) { avisar({ tipo: "mal", texto: mensajeError(err) }); }
  };
  return (
    <section className="mb-10">
      <h2 className="mb-1 text-[22px] font-semibold">Tus ediciones, como ejemplos</h2>
      <p className="mb-4 max-w-[62ch] text-[14px] text-tinta-suave">
        Cada semana se recogen las diapositivas que cambiaste (a mano o con el chat) y se eligen las que enseñan criterio. Las
        activas, como mucho {max}, las reciben el guionista y el chat: «así lo escribió, así lo dejaste». {candidatos > 0 && `${candidatos} esperan al próximo análisis.`}
      </p>
      {activos.length === 0 && <p className="text-[14px] text-tinta-suave">Todavía ninguno. Salen de las piezas que editas.</p>}
      <div className="flex flex-col gap-3">
        {ejemplos.map((e) => (
          <article key={e.id} className={`panel flex flex-col gap-2 p-4 text-[14px] ${e.estado !== "activo" ? "opacity-60" : ""}`}>
            <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-tinta-suave">
              <Link className="underline" href={`/pieza/${e.pieza_id}`}>{e.pieza_id}</Link>
              <span>diapositiva {e.n} · {e.tipo}{e.formato && ` · ${e.formato}`}</span>
              <span>{e.estado === "activo" ? "activo" : "retirado"}</span>
            </div>
            <p className="text-tinta-suave line-through decoration-carmesi/50">{e.antes}</p>
            <p>{e.despues}</p>
            {e.leccion && <p className="text-[13px] italic">Lo que enseña: {e.leccion}</p>}
            <div>
              {e.estado === "activo"
                ? <button className="boton-suave" onClick={() => decidir(e, "retirado")}>Quitar de los ejemplos</button>
                : <button className="boton-suave" onClick={() => decidir(e, "activo")}>Volver a usar</button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function VistaEstilo() {
  const { datos, error, recargar } = useDatos("estilo", api.libroEstilo);
  const [probando, setProbando] = useState<number | null>(null);
  const [resultado, setResultado] = useState("");
  const seguir = useCallback(async () => {
    const e = await api.pruebaFicha().catch(() => null);
    if (!e) return;
    if (e.en_marcha) { setProbando((x) => x ?? -1); return; }
    setProbando((x) => {
      if (x !== null) {
        setResultado(e.codigo === 0 ? e.ultimas_lineas.join(" · ") : `La prueba no salió: ${e.ultimas_lineas.slice(-2).join(" · ")}`);
        recargar();
      }
      return null;
    });
  }, [recargar]);
  useEffect(() => { const t = setTimeout(seguir, 0); return () => clearTimeout(t); }, [seguir]);
  useEffect(() => {
    if (probando === null) return;
    const t = setInterval(seguir, 5000);
    return () => clearInterval(t);
  }, [probando, seguir]);
  const probar = async (id: number) => {
    setResultado("");
    try { await api.probarFicha(id); setProbando(id); mirarTrabajos(); }
    catch (e) { setResultado(`No se pudo probar: ${mensajeError(e)}`); }
  };
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="antetitulo">Libro de estilo</div>
      <h1 className="titular mb-2 mt-2 text-[40px] sm:text-[48px]">Lo que <em>cumple cada rol</em></h1>
      <p className="mb-5 max-w-[62ch] text-[14px] text-tinta-suave">
        Cada regla es una ficha: de dónde sale, un ejemplo bueno y uno malo, y si se ha probado. Las nuevas salen de la{" "}
        <Link className="underline" href="/como-vamos?ver=memoria">Memoria</Link> y, si las aceptas, su rol las cumple desde la siguiente
        pieza. Cada semana se prueban las nuevas del guionista en el banco (unas piezas aprobadas, reescritas con y sin la
        ficha, con un juez a ciegas) y, si un rol pasa de su tope, se proponen fusiones y retiros.
      </p>
      {datos && !datos.github && (
        <p className="mb-5 rounded-[8px] border border-borde bg-papel p-3 text-[13px]">
          Los encargos de código (fichas que necesitan cambiar el programa) quedan apuntados en cada ficha. Para que se abran
          solos en GitHub y los recoja la tarea semanal, falta poner <code>FOLIO_GITHUB_TOKEN</code> en Railway.
        </p>
      )}
      {probando !== null && <div className="mb-5"><Trabajando etapa="Reescribiendo piezas del banco con y sin la ficha, y juzgándolas a ciegas" rotulo="Probando" /></div>}
      {resultado && <p className="mb-5 text-[14px]">{resultado}</p>}
      {error && <p className="text-carmesi" role="alert">No se pudo cargar el libro de estilo: {error}</p>}
      {!datos && !error && <div className="flex flex-col gap-4" aria-busy="true">{[0, 1, 2].map((i) => <div key={i} className="esqueleto h-32 w-full" />)}</div>}
      {datos && <Ejemplos ejemplos={datos.ejemplos} candidatos={datos.candidatos} max={datos.ejemplos_max} recargar={recargar} />}
      {datos && datos.roles.map((r) => <SeccionRol key={r.id} r={r} probando={probando} probar={probar} recargar={recargar} />)}
    </div>
  );
}
