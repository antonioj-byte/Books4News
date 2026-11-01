"use client";

import { useState } from "react";
import { api, type EstadoMemoria, type Patron } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

// Memoria del feedback: lo que se repite en las evaluaciones, comentarios, ediciones y peticiones al chat,
// con una propuesta de regla. Quien edita decide; las aceptadas se pasan a los prompts en una sesión de trabajo.
const DESTINOS: Record<string, string> = {
  jefe_cultura: "Jefe de cultura", guionista: "Guionista", director_arte: "Director de arte",
  formatos: "Formatos", codigo: "Programa",
};
const ESTADOS = [
  { valor: "propuesta", texto: "Propuestas" },
  { valor: "aceptada", texto: "Aceptadas · pendientes de pasar a las reglas" },
  { valor: "aplicada", texto: "Ya son reglas" },
  { valor: "rechazada", texto: "Rechazadas" },
] as const;

const fecha = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00` : iso)
  .toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });

function Calendario({ e }: { e: EstadoMemoria }) {
  return (
    <p className="mb-6 text-[13px] text-tinta-suave">
      Se analiza solo cada lunes, después de la ejecución de madrugada. {e.ultimo
        ? <>Último análisis: {fecha(e.ultimo)} ({e.ultimo_origen === "semanal" ? "automático" : "a mano"}).</>
        : <>Todavía no se ha analizado nunca.</>} Próximo: {fecha(e.proximo)}.
      {e.de_conversacion > 0 && <> En «Ya son reglas» están también las {e.de_conversacion} que salieron de lo que has pedido en las conversaciones.</>}
    </p>
  );
}

function Tarjeta({ p, decidir }: { p: Patron; decidir: (estado: Patron["estado"]) => void }) {
  return (
    <article className="panel flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-tinta px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-[0.12em]">{DESTINOS[p.destino] ?? p.destino}</span>
        {p.origen === "conversacion"
          ? <span className="rounded-full bg-papel-hondo px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-[0.12em]">Pedido en conversación · {p.creado_en.slice(0, 10)}</span>
          : <span className="font-mono text-[11px] text-tinta-suave">{p.veces} análisis · #{p.id}</span>}
      </div>
      <h3 className="text-[19px] font-semibold leading-snug">{p.patron}</h3>
      <p className="rounded-[6px] bg-papel-hondo px-3 py-2 text-[14px]"><b>{p.origen === "conversacion" ? "Regla:" : "Regla propuesta:"}</b> {p.propuesta}</p>
      <ul className="list-disc pl-5 text-[13px] text-tinta-suave">
        {p.evidencia.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
      </ul>
      {p.nota && <p className="text-[13px] italic">Nota: {p.nota}</p>}
      {p.origen !== "conversacion" && <div className="flex flex-wrap gap-2">
        {p.estado !== "aceptada" && p.estado !== "aplicada" && <button className="boton" onClick={() => decidir("aceptada")}>Aceptar</button>}
        {p.estado !== "rechazada" && p.estado !== "aplicada" && <button className="boton-suave" onClick={() => decidir("rechazada")}>Rechazar</button>}
        {p.estado === "aceptada" && <button className="boton-suave" onClick={() => decidir("aplicada")}>Marcar como ya aplicada</button>}
        {p.estado !== "propuesta" && <button className="boton-suave" onClick={() => decidir("propuesta")}>Volver a propuesta</button>}
      </div>}
    </article>
  );
}

export function VistaMemoria() {
  const { datos, error, recargar } = useDatos("memoria", api.memoria);
  const estado = useDatos("memoria-estado", api.estadoMemoria);
  const [analizando, setAnalizando] = useState(false);
  const [resultado, setResultado] = useState("");
  const analizar = async () => {
    setAnalizando(true);
    setResultado("");
    try {
      const r = await api.analizarMemoria(14);
      setResultado(`${r.piezas} piezas con feedback · ${r.patrones} patrones guardados o reforzados${r.aviso ? ` · ${r.aviso}` : ""}`);
      recargar();
      estado.recargar();
    } catch (e) {
      setResultado(`No se pudo analizar: ${String(e)}`);
    } finally {
      setAnalizando(false);
    }
  };
  const decidir = async (p: Patron, estado: Patron["estado"]) => { await api.decidirPatron(p.id, estado); recargar(); };
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="antetitulo">Memoria</div>
      <h1 className="titular mb-2 mt-2 text-[40px] sm:text-[48px]">Lo que <em>se repite</em></h1>
      <p className="mb-5 max-w-[62ch] text-[14px] text-tinta-suave">
        Patrones que salen de tus evaluaciones, comentarios, ediciones a mano y peticiones al chat, cada uno con una regla
        propuesta. Tú decides: las aceptadas se pasan a las instrucciones de los agentes en una sesión de trabajo.
      </p>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button className="boton" onClick={analizar} disabled={analizando}>{analizando ? "Analizando…" : "Analizar el feedback de los últimos 14 días"}</button>
        <span className="text-[13px] text-tinta-suave">Una llamada a Opus, unos céntimos.</span>
      </div>
      {estado.datos && <Calendario e={estado.datos} />}
      {resultado && <p className="mb-6 text-[14px]">{resultado}</p>}
      {error && <p className="text-carmesi">No se pudo cargar la memoria: {error}</p>}
      {datos && datos.length === 0 && <p className="text-tinta-suave">Todavía no hay patrones. Evalúa y edita piezas, y analiza el feedback.</p>}
      {datos && ESTADOS.map((e) => {
        const grupo = datos.filter((p) => p.estado === e.valor);
        if (!grupo.length) return null;
        return (
          <section key={e.valor} className="mb-8">
            <h2 className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">{e.texto} · {grupo.length}</h2>
            <div className="flex flex-col gap-4">{grupo.map((p) => <Tarjeta key={p.id} p={p} decidir={(s) => decidir(p, s)} />)}</div>
          </section>
        );
      })}
    </div>
  );
}
