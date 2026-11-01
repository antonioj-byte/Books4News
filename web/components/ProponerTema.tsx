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
  const responder = async () => {
    if (texto.trim().length < 2 || enviando || !eid) return;
    setEnviando(true); setError(null);
    try {
      const r = await api.replicarTema(tema.id, { texto: texto.trim(), ejecucion: eid });
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
        <button onClick={responder} disabled={enviando || texto.trim().length < 2 || !eid} className="boton self-end">
          {enviando ? "Pensando…" : "Enviar"}
        </button>
      </div>
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}

// Proponer un tema al jefe de cultura (2/11): ahora (una pieza pendiente en esta mesa) o para la mesa de mañana.
export function ProponerTema({ eid, onPieza }: { eid?: number; onPieza: () => void }) {
  const [texto, setTexto] = useState("");
  const [enlaces, setEnlaces] = useState("");
  const [enviando, setEnviando] = useState<"ahora" | "manana" | null>(null);
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null);
  const { datos: temas, recargar } = useDatos("temas", api.temas);
  const [abierto, setAbierto] = useState<number | null>(null);

  const proponer = async (cuando: "ahora" | "manana") => {
    if (texto.trim().length < 8 || enviando) return;
    setEnviando(cuando); setMensaje(null);
    try {
      const r = await api.proponerTema({ texto: texto.trim(), enlaces: enlaces.split(/\s+/).filter(Boolean), cuando, ejecucion: eid ?? null });
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

  return (
    <section className="mt-12" aria-labelledby="h-tema">
      <div className="antetitulo">Jefe de cultura</div>
      <h2 id="h-tema" className="titular mb-1 mt-2 text-[30px]">Proponer <em>un tema</em></h2>
      <p className="mb-4 max-w-[62ch] text-[14px] text-tinta-suave">
        Dile al jefe de qué quieres que se hable. Le busca el ángulo y el libro, con las mismas reglas que la mesa.
        Si no pones enlaces, busca él las noticias.
      </p>
      <div className="panel flex flex-col gap-3 p-4">
        <label htmlFor="tema-texto" className="dato uppercase">El tema</label>
        <textarea id="tema-texto" value={texto} onChange={(e) => setTexto(e.target.value)} rows={3} disabled={!!enviando}
                  placeholder="«La huelga de traductores en Francia», «por qué ya nadie lee en el metro»…"
                  className="resize-y rounded-[12px] border border-borde bg-papel p-3 text-[15px] outline-none focus:border-tinta" />
        <label htmlFor="tema-enlaces" className="dato uppercase">Enlaces (opcional, uno por línea)</label>
        <textarea id="tema-enlaces" value={enlaces} onChange={(e) => setEnlaces(e.target.value)} rows={2} disabled={!!enviando}
                  placeholder="https://…"
                  className="resize-y rounded-[12px] border border-borde bg-papel p-3 font-mono text-[13px] outline-none focus:border-tinta" />
        <div className="flex flex-wrap items-center gap-2">
          <button className="boton" onClick={() => proponer("ahora")} disabled={!!enviando || !eid || texto.trim().length < 8}>
            {enviando === "ahora" ? "El jefe está pensando… (1–2 min)" : "Proponer ahora"}
          </button>
          <button className="boton-suave" onClick={() => proponer("manana")} disabled={!!enviando || texto.trim().length < 8}>
            {enviando === "manana" ? "Guardando…" : "Para la mesa de mañana"}
          </button>
          <span className="text-[13px] text-tinta-suave">Ahora: unos céntimos; la pieza se escribe después con «Proceder».</span>
        </div>
        {mensaje && <p className={mensaje.ok ? "text-[14px]" : "text-[14px] text-carmesi"}>{mensaje.texto}</p>}
      </div>
      {recientes.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5 text-[13.5px]">
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
      )}
    </section>
  );
}
