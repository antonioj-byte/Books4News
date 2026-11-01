"use client";

import { useState } from "react";
import { api, type Tema } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

const ESTADOS: Record<string, string> = {
  pendiente: "Para la mesa de mañana", en_mesa: "En la mesa", no_elegido: "El jefe no lo llevó",
  fallido: "No se pudo", descartado: "Descartado",
};

// Proponer un tema al jefe de cultura (2/11): ahora (una pieza pendiente en esta mesa) o para la mesa de mañana.
export function ProponerTema({ eid, onPieza }: { eid?: number; onPieza: () => void }) {
  const [texto, setTexto] = useState("");
  const [enlaces, setEnlaces] = useState("");
  const [enviando, setEnviando] = useState<"ahora" | "manana" | null>(null);
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null);
  const { datos: temas, recargar } = useDatos("temas", api.temas);

  const proponer = async (cuando: "ahora" | "manana") => {
    if (texto.trim().length < 8 || enviando) return;
    setEnviando(cuando); setMensaje(null);
    try {
      const r = await api.proponerTema({ texto: texto.trim(), enlaces: enlaces.split(/\s+/).filter(Boolean), cuando, ejecucion: eid ?? null });
      setTexto(""); setEnlaces("");
      setMensaje({ ok: true, texto: cuando === "manana" ? "Guardado: el jefe lo verá en la mesa de mañana."
        : r.estado_pieza === "pendiente" ? `El jefe lo ha llevado a la mesa (${r.pieza_id}): pulsa «Proceder» para escribirlo.`
        : `La propuesta está en la mesa (${r.pieza_id}), pero ${r.avisos.at(-1) ?? "sin libro verificado"}.` });
      if (cuando === "ahora") onPieza();
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
              {t.nota && t.estado !== "en_mesa" && <span className="basis-full text-tinta-suave">{t.nota}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
