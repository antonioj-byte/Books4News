"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Capa, type EstadoMemoria, type Patron } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { Boton } from "@/components/Boton";
import { Trabajando } from "@/components/Trabajando";
import { mensajeError } from "@/lib/errores";
import { mirarTrabajos } from "@/lib/trabajos";

// Memoria del feedback: lo que se repite en las evaluaciones, comentarios, ediciones y peticiones al chat,
// con una propuesta de regla. Quien edita decide; las aceptadas cuentan desde ya en el prompt de su agente (2/11) y
// luego se escriben en él en una sesión de trabajo.
const DESTINOS: Record<string, string> = {
  jefe_cultura: "Jefe de cultura", guionista: "Guionista", director_arte: "Director de arte",
  formatos: "Formatos", codigo: "Programa",
};
const ESTADOS = [
  { valor: "propuesta", texto: "Propuestas" },
  { valor: "aceptada", texto: "Aceptadas · ya las cumplen sus agentes (las del programa, pendientes)" },
  { valor: "aplicada", texto: "Ya son reglas" },
  { valor: "retirada", texto: "Retiradas (libro de estilo)" },
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

// A quién alcanza la regla (3/11, la agencia): la Memoria la propone y quien edita la confirma al aceptar
const CAPAS: { valor: Capa; texto: string; ayuda: string }[] = [
  { valor: "oficio", texto: "Oficio", ayuda: "de este rol, para cualquier marca" },
  { valor: "marca", texto: "Folio", ayuda: "de Folio, para todos sus roles" },
  { valor: "celda", texto: "Este rol en Folio", ayuda: "lo más estrecho" },
];

function Tarjeta({ p, decidir }: { p: Patron; decidir: (estado: Patron["estado"], capa?: Capa) => Promise<void> }) {
  // Aceptar cambia los prompts de producción desde la siguiente pieza: se confirma en la página (4/11, usabilidad)
  const [confirmar, setConfirmar] = useState(false);
  const [capa, setCapa] = useState<Capa>((p.capa as Capa) ?? "celda");
  const decidible = p.origen !== "conversacion";
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
      {(p.ejemplo_bueno || p.ejemplo_malo) && (
        <div className="grid gap-1.5 text-[13px] sm:grid-cols-2">
          {p.ejemplo_bueno && <p className="rounded-[6px] border border-borde px-2.5 py-1.5"><b>Así sí:</b> «{p.ejemplo_bueno}»</p>}
          {p.ejemplo_malo && <p className="rounded-[6px] border border-borde px-2.5 py-1.5"><b>Así no:</b> «{p.ejemplo_malo}»</p>}
        </div>
      )}
      <ul className="list-disc pl-5 text-[13px] text-tinta-suave">
        {p.evidencia.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
      </ul>
      {p.nota && <p className="text-[13px] italic">Nota: {p.nota}</p>}
      <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]" role="group" aria-label="A quién alcanza">
        <span className="dato uppercase">¿Dónde va?</span>
        {CAPAS.map((c) => (
          <button key={c.valor} aria-pressed={capa === c.valor} title={c.ayuda} disabled={!decidible || p.estado === "aplicada"}
                  onClick={() => setCapa(c.valor)}
                  className={`rounded-full border px-2.5 py-0.5 ${capa === c.valor ? "border-carmesi text-carmesi" : "border-borde bg-panel hover:border-tinta"} disabled:cursor-default disabled:hover:border-borde`}>
            {c.texto}
          </button>
        ))}
        <span className="dato">{CAPAS.find((c) => c.valor === capa)?.ayuda}</span>
      </div>
      {decidible && <div className="flex flex-wrap gap-2">
        {p.estado !== "aceptada" && p.estado !== "aplicada" && !confirmar && <button className="boton" onClick={() => setConfirmar(true)}>Aceptar</button>}
        {confirmar && (
          <span className="flex basis-full flex-col items-start gap-2 rounded-[10px] border border-borde bg-papel p-3 text-[13px]">
            <span>Desde la siguiente pieza, {p.destino === "codigo" ? "se encarga como cambio de código (una issue en GitHub que recoge la tarea semanal)" : p.origen === "poda" ? "se aplica la poda: las fichas que funde o retira dejan de contar" : "su agente cumplirá esta regla en producción"}.</span>
            <span className="flex gap-2">
              <Boton onClick={async () => { await decidir("aceptada", capa); setConfirmar(false); }} hecho="Aceptada">Sí, aceptarla</Boton>
              <button className="boton-suave" onClick={() => setConfirmar(false)}>Cancelar</button>
            </span>
          </span>
        )}
        {p.estado !== "rechazada" && p.estado !== "aplicada" && !confirmar && <Boton tipo="secundario" hecho={null} onClick={() => decidir("rechazada")}>Rechazar</Boton>}
        {p.estado === "aceptada" && <Boton tipo="secundario" hecho={null} onClick={() => decidir("aplicada")}>Marcar como ya aplicada</Boton>}
        {p.estado !== "propuesta" && !confirmar && <Boton tipo="secundario" hecho={null} onClick={() => decidir("propuesta")}>Volver a propuesta</Boton>}
      </div>}
    </article>
  );
}

export function VistaMemoria() {
  const { datos, error, recargar } = useDatos("memoria", api.memoria);
  const estado = useDatos("memoria-estado", api.estadoMemoria);
  const [analizando, setAnalizando] = useState(false);
  const [resultado, setResultado] = useState("");
  const recargarEstado = estado.recargar;
  // Sigue el análisis en marcha (proceso aparte) y, al acabar, enseña su salida y recarga los patrones
  const seguir = useCallback(async () => {
    const e = await api.analisisMemoria().catch(() => null);
    if (!e) return false;
    if (e.en_marcha) { setAnalizando(true); return true; }
    setAnalizando(false);
    const salida = e.ultimas_lineas.join(" · ");
    setResultado(e.codigo === 0 ? salida : `No se pudo analizar (código ${e.codigo ?? "?"}): ${salida}`);
    recargar();
    recargarEstado();
    return false;
  }, [recargar, recargarEstado]);
  // Al entrar, por si hay un análisis en marcha (lanzado antes o por la diaria): se mira tras el primer pintado
  useEffect(() => { const t = setTimeout(seguir, 0); return () => clearTimeout(t); }, [seguir]);
  useEffect(() => {
    if (!analizando) return;
    const t = setInterval(seguir, 5000);
    return () => clearInterval(t);
  }, [analizando, seguir]);
  const analizar = async () => {
    setResultado("");
    try {
      await api.analizarMemoria(14);
      setAnalizando(true);
      mirarTrabajos();
    } catch (e) {
      setResultado(`No se pudo analizar: ${mensajeError(e)}`);
    }
  };
  const decidir = async (p: Patron, estado: Patron["estado"], capa?: Capa) => { await api.decidirPatron(p.id, estado, "", capa); recargar(); };
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="antetitulo">Memoria</div>
      <h1 className="titular mb-2 mt-2 text-[40px] sm:text-[48px]">Lo que <em>se repite</em></h1>
      <p className="mb-5 max-w-[62ch] text-[14px] text-tinta-suave">
        Patrones que salen de tus evaluaciones, comentarios, ediciones a mano y peticiones al chat, cada uno con una regla
        propuesta. Tú decides: una regla aceptada la cumple su agente (jefe de cultura, guionista o director de arte) desde la siguiente pieza. Las del programa necesitan cambiar el código y esperan a una sesión de trabajo.
      </p>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        {analizando
          ? <Trabajando etapa="Opus está leyendo el feedback y buscando lo que se repite" rotulo="Analizando" />
          : <button className="boton" onClick={analizar}>Analizar el feedback de los últimos 14 días<span className="boton__coste">unos minutos · unos céntimos</span></button>}
      </div>
      {estado.datos && <Calendario e={estado.datos} />}
      {resultado && <p className="mb-6 text-[14px]">{resultado}</p>}
      {error && <p className="text-carmesi" role="alert">No se pudo cargar la memoria: {error}</p>}
      {!datos && !error && <div className="flex flex-col gap-4" aria-busy="true">{[0, 1].map((i) => <div key={i} className="esqueleto h-40 w-full" />)}</div>}
      {datos && datos.length === 0 && <p className="text-tinta-suave">Todavía no hay patrones. Evalúa y edita piezas, y analiza el feedback.</p>}
      {datos && ESTADOS.map((e) => {
        const grupo = datos.filter((p) => p.estado === e.valor);
        if (!grupo.length) return null;
        return (
          <section key={e.valor} className="mb-8">
            <h2 className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">{e.texto} · {grupo.length}</h2>
            <div className="flex flex-col gap-4">{grupo.map((p) => <Tarjeta key={p.id} p={p} decidir={(s, c) => decidir(p, s, c)} />)}</div>
          </section>
        );
      })}
    </div>
  );
}
