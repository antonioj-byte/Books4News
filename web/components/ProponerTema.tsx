"use client";

import { useState } from "react";
import { api, type Tema } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

const ESTADOS: Record<string, string> = {
  pendiente: "Para la mesa de mañana", en_mesa: "En la mesa", no_elegido: "El jefe no lo llevó",
  fallido: "No se pudo", descartado: "Descartado", pregunta: "El jefe pregunta",
};

// La conversación con el jefe sobre un tema y el campo para contestarle o replicarle (2/11)
function Conversacion({ tema, eid, onPieza, onCambio }: { tema: Tema; eid?: number; onPieza: () => void; onCambio: () => void }) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const responder = async (propio?: string, enfoque?: "noticia") => {
    const m = (propio ?? texto).trim();
    if (m.length < 2 || enviando || !eid) return;
    setEnviando(true); setError(null);
    try {
      const r = await api.replicarTema(tema.id, { texto: m, ejecucion: eid, ...(enfoque ? { enfoque } : {}) });
      setTexto("");
      if (r.pieza_id) onPieza();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo enviar");
    } finally { setEnviando(false); onCambio(); }
  };
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-[12px] border border-borde bg-panel p-3 text-[14px]">
      {tema.conversacion.map((t, i) => (
        <p key={i} className={t.rol !== "redaccion" ? "whitespace-pre-line" : "self-end rounded-[10px] bg-tinta px-3 py-1.5 text-papel"}>
          {t.rol !== "redaccion" && <span className="dato mr-2 uppercase text-carmesi">{t.rol === "jefe" ? "Jefe" : "Verificación"}</span>}{String(t.texto ?? "")}
        </p>
      ))}
      <div className="flex gap-2">
        <textarea id={`replica-${tema.id}`} value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} disabled={enviando}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); responder(); } }}
                  placeholder={tema.estado === "pregunta" ? "Contesta al jefe…" : "Replica a la propuesta: «otro libro», «más perfil y menos noticia»…"}
                  className="min-w-0 flex-1 resize-none rounded-[10px] border border-borde bg-papel p-2 outline-none focus:border-tinta" />
        <button onClick={() => responder()} disabled={enviando || texto.trim().length < 2 || !eid} className="boton self-end">
          {enviando ? "Pensando…" : "Enviar"}
        </button>
      </div>
      {tema.enfoque !== "noticia" && tema.estado !== "pregunta" && (
        // 3/11: si el jefe hizo un ensayo y solo se quería la noticia, un clic lo rehace como «Noticia»
        <button onClick={() => responder("Solo la noticia: cuéntala con su contexto, sin ensayo ni libro ajeno.", "noticia")}
                disabled={enviando || !eid} className="self-start rounded-full border border-carmesi px-3 py-1 text-[12.5px] text-carmesi hover:bg-carmesi hover:text-papel">
          Solo la noticia
        </button>
      )}
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}

// Proponer un tema al jefe de cultura (2/11): ahora (una pieza pendiente en esta mesa) o para la mesa de mañana.
export function ProponerTema({ eid, onPieza }: { eid?: number; onPieza: () => void }) {
  const [texto, setTexto] = useState("");
  const [enlaces, setEnlaces] = useState("");
  const [enviando, setEnviando] = useState<"ahora" | "manana" | null>(null);
  // Lo que pide la redacción (3/11, «si lo que le pido es que me cuente una noticia… no me haga un ensayo»)
  const [enfoque, setEnfoque] = useState<"elige" | "noticia">("elige");
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null);
  const { datos: temas, recargar } = useDatos("temas", api.temas);
  const [abierto, setAbierto] = useState<number | null>(null);

  const proponer = async (cuando: "ahora" | "manana") => {
    if (texto.trim().length < 8 || enviando) return;
    setEnviando(cuando); setMensaje(null);
    try {
      const r = await api.proponerTema({ texto: texto.trim(), enlaces: enlaces.split(/\s+/).filter(Boolean), cuando, ejecucion: eid ?? null, enfoque });
      setTexto(""); setEnlaces("");
      setMensaje({ ok: true, texto: cuando === "manana" ? "Guardado: el jefe lo verá en la mesa de mañana."
        : r.preguntas.length ? "El jefe necesita saber algo antes de proponer: contéstale abajo."
        : r.estado_pieza === "pendiente" ? `El jefe lo ha llevado a la mesa (${r.pieza_id}): pulsa «Proceder» para escribirlo, o replícale abajo.`
        : `El jefe propuso un enfoque, pero ninguno de sus libros pasó la verificación (están en la propuesta ${r.pieza_id}, en la mesa). Replícale abajo con el libro que quieras, o pídele otros.` });
      if (cuando === "ahora") { setAbierto(r.tema.id); if (r.pieza_id) onPieza(); }
    } catch (e) {
      setMensaje({ ok: false, texto: e instanceof Error ? e.message.replace(/^\d+ \S+: /, "") : "No se pudo proponer" });
    } finally { setEnviando(null); recargar(); }
  };
  const descartar = async (t: Tema) => { await api.descartarTema(t.id).catch(() => null); recargar(); };
  const recientes = (temas ?? []).slice(0, 6);

  const abiertoForm = texto.length > 0 || !!enviando || enlaces.length > 0;
  const pendientes = recientes.filter((t) => t.estado === "pregunta").length;

  // Arriba de la mesa y en compacto (3/11, «se está volviendo demasiado compleja la web»): una línea que se abre al escribir
  return (
    <section aria-labelledby="h-tema" className="mb-8">
      <div className="panel flex flex-col gap-3 p-3 sm:p-4">
        <label id="h-tema" htmlFor="tema-texto" className="sr-only">Proponer un tema al jefe de cultura</label>
        <textarea id="tema-texto" value={texto} onChange={(e) => setTexto(e.target.value)} rows={abiertoForm ? 3 : 1} disabled={!!enviando}
                  placeholder="¿De qué quieres que hablemos hoy? El jefe de cultura le busca el ángulo y el libro."
                  className="resize-none rounded-[12px] border border-borde bg-papel px-3 py-2.5 text-[16px] outline-none focus:border-tinta" />
        {abiertoForm && (
          <>
            <textarea id="tema-enlaces" value={enlaces} onChange={(e) => setEnlaces(e.target.value)} rows={2} disabled={!!enviando}
                      placeholder="Enlaces, si los tienes (uno por línea). Sin enlaces, busca él las noticias."
                      aria-label="Enlaces (opcional)"
                      className="resize-y rounded-[12px] border border-borde bg-papel p-3 font-mono text-[13px] outline-none focus:border-tinta" />
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Qué le pides al jefe">
              {([["elige", "Que el jefe elija"], ["noticia", "Solo la noticia"]] as const).map(([v, txt]) => (
                <button key={v} aria-pressed={enfoque === v} onClick={() => setEnfoque(v)} disabled={!!enviando}
                        className={`rounded-full border px-3 py-1 text-[13px] ${enfoque === v ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-papel hover:border-tinta"}`}>
                  {txt}
                </button>
              ))}
              <span className="text-[12.5px] text-tinta-suave">
                {enfoque === "noticia" ? "Contada con su contexto, sin ensayo ni libro ajeno." : "Lectura lateral, diálogo, tres libros… lo que mejor le vaya."}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button className="boton" onClick={() => proponer("ahora")} disabled={!!enviando || !eid || texto.trim().length < 8}>
                {enviando === "ahora" ? "El jefe está pensando… (1–2 min)" : "Proponer ahora"}
              </button>
              <button className="boton-suave" onClick={() => proponer("manana")} disabled={!!enviando || texto.trim().length < 8 || enfoque === "noticia"}
                      title={enfoque === "noticia" ? "La mesa de mañana solo propone piezas con libro" : undefined}>
                {enviando === "manana" ? "Guardando…" : "Para la mesa de mañana"}
              </button>
            </div>
          </>
        )}
        {mensaje && <p className={mensaje.ok ? "text-[14px]" : "text-[14px] text-carmesi"}>{mensaje.texto}</p>}
      </div>
      {recientes.length > 0 && (
        <details className="mt-2 text-[13.5px]" open={pendientes > 0 || abierto !== null}>
        <summary className="dato cursor-pointer uppercase">Temas propuestos · {recientes.length}{pendientes ? ` · ${pendientes} con pregunta del jefe` : ""}</summary>
        <ul className="mt-2 flex flex-col gap-1.5">
          {recientes.map((t) => (
            <li key={t.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="dato uppercase text-tinta-suave">{ESTADOS[t.estado] ?? t.estado}{t.pieza_id ? ` · ${t.pieza_id}` : ""}</span>
              <span className="min-w-0 flex-1">{t.texto}</span>
              {t.estado === "pendiente" && <button onClick={() => descartar(t)} className="text-tinta-suave hover:text-carmesi">Descartar</button>}
              {(t.estado === "pregunta" || t.estado === "en_mesa" || (t.estado === "fallido" && t.pieza_id)) && t.conversacion.length > 0 && (
                <button onClick={() => setAbierto(abierto === t.id ? null : t.id)} className="text-tinta-suave underline-offset-2 hover:text-tinta hover:underline">
                  {abierto === t.id ? "Cerrar" : t.estado === "pregunta" ? "Contestar" : "Replicar"}
                </button>
              )}
              {t.nota && t.estado !== "en_mesa" && (
                <span className="basis-full text-tinta-suave">{t.nota === "Ningún libro candidato se pudo verificar" ? "Ninguno de los libros del jefe pasó la verificación: replícale con otro." : t.nota}</span>
              )}
              {abierto === t.id && <div className="basis-full"><Conversacion tema={t} eid={eid} onPieza={onPieza} onCambio={recargar} /></div>}
            </li>
          ))}
        </ul>
        </details>
      )}
    </section>
  );
}
