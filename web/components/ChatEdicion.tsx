"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Material, type MensajeChat, type Para } from "@/lib/api";
import { avisar, conDeshacer } from "@/lib/avisos";
import { mensajeError } from "@/lib/errores";

type Uso = "foto" | "cubierta" | "leer";

// A quién se dirige quien edita (3/11, la agencia) y el nombre de cada rol que responde
const DESTINOS: { valor: Para | null; texto: string }[] = [
  { valor: null, texto: "Que decida el chat" }, { valor: "guionista", texto: "Guionista" },
  { valor: "director_arte", texto: "Director de arte" }, { valor: "jefe_cultura", texto: "Jefe de cultura" },
];
const NOMBRE_ROL: Record<string, string> = {
  guionista: "Guionista", director_arte: "Director de arte", jefe_cultura: "Jefe de cultura", ilustrador: "Ilustrador",
  editor_chat: "Editor",
};

// El único sitio para pedir cambios en una pieza (3/11, «se está volviendo demasiado compleja la web»): se escribe al
// editor (Opus), que devuelve la pieza revisada; cada cambio es una versión nueva y `onCambio` recarga la pieza.
// Aquí llegan también lo que antes iba por separado: los adjuntos (clip; la foto de la persona, una cubierta o algo para
// leer), los comentarios sobre una diapositiva (`borrador`, desde el carrusel) y los titulares alternativos.
export function ChatEdicion({ eid, pid, onCambio, titulares = [], titularActual = "", subtitulo = null, persona = null,
                              fotoPersona = null, borrador = null }: {
  eid: number; pid: string; onCambio: () => void;
  titulares?: string[]; titularActual?: string; subtitulo?: string | null;
  persona?: string | null; fotoPersona?: string | null;
  borrador?: { texto: string } | null;
}) {
  const [mensajes, setMensajes] = useState<MensajeChat[]>([]);
  const [locales, setLocales] = useState<string[]>([]);          // avisos de lo que se hizo sin pasar por el editor
  const [texto, setTexto] = useState("");
  const [para, setPara] = useState<Para | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [segundos, setSegundos] = useState(0);
  const [adjuntos, setAdjuntos] = useState<Material[]>([]);
  const [verTitulares, setVerTitulares] = useState(false);
  const [usando, setUsando] = useState<string | null>(null);
  const final = useRef<HTMLDivElement>(null);
  const caja = useRef<HTMLTextAreaElement>(null);

  // El adjunto en curso: qué es, su crédito y, si es la foto de la persona, cómo va
  const [archivo, setArchivo] = useState<File | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const [uso, setUso] = useState<Uso | null>(null);
  const [credito, setCredito] = useState("");
  const [modificable, setModificable] = useState(false);
  const [tratamiento, setTratamiento] = useState<"foto" | "papel" | "escena">("foto");
  const [subiendo, setSubiendo] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  const cargarAdjuntos = () => api.materiales(eid, pid).then(setAdjuntos).catch(() => setAdjuntos([]));
  useEffect(() => { api.chat(eid, pid).then(setMensajes).catch(() => setMensajes([])); cargarAdjuntos(); }, [eid, pid]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { final.current?.scrollIntoView({ block: "nearest" }); }, [mensajes, enviando, locales]);
  // Un turno con Opus tarda; el contador deja claro que sigue trabajando (2/11: «parece que se queda bugueado»)
  useEffect(() => {
    if (!enviando) return;
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => { clearInterval(t); setSegundos(0); };
  }, [enviando]);
  // «Comentar esta diapositiva» en el carrusel escribe aquí «Diapositiva 3: » y deja el cursor al final
  const [ultimoBorrador, setUltimoBorrador] = useState(borrador);
  if (borrador !== ultimoBorrador) {
    setUltimoBorrador(borrador);
    if (borrador) setTexto(borrador.texto);
  }
  useEffect(() => {
    if (!borrador) return;
    requestAnimationFrame(() => {
      const c = caja.current;
      if (c) { c.focus(); c.setSelectionRange(c.value.length, c.value.length); }
    });
  }, [borrador]);

  const enviar = async (propio?: string) => {
    const m = (propio ?? texto).trim();
    if (!m || enviando) return;
    setEnviando(true); setError(null); setTexto("");
    setMensajes((x) => [...x, { n: x.length + 1, rol: "usuario", texto: m, version_n: null, creado_en: "", opciones: [], para, agente: null }]);
    try {
      const r = await api.enviarChat(eid, pid, m, para);
      setMensajes(await api.chat(eid, pid));
      if (r.version) onCambio();
    } catch (e) {
      // Si se cortó la conexión pero la api terminó, la respuesta está guardada: se enseña en vez del error
      const guardados = await api.chat(eid, pid).catch(() => null);
      const ultimo = guardados?.at(-1), penultimo = guardados?.at(-2);
      if (ultimo?.rol === "editor" && penultimo?.rol === "usuario" && penultimo.texto === m) {
        setMensajes(guardados!);
        if (ultimo.version_n) onCambio();
      } else {
        setError(mensajeError(e, "No se pudo enviar."));
        setTexto(m);
        setMensajes((x) => x.slice(0, -1));    // el mensaje no llegó a guardarse
      }
    } finally { setEnviando(false); }
  };

  const usarTitular = async (t: string) => {
    setUsando(t); setError(null);
    try {
      await api.editarDiapositiva(eid, pid, 1, t, subtitulo ?? null);
      setLocales((x) => [...x, `Titular cambiado: «${t}».`]);
      onCambio();
    } catch (e) {
      setError(mensajeError(e, "No se pudo cambiar el titular."));
    } finally { setUsando(null); }
  };

  const elegir = (f: File | undefined) => {
    setError(null);
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { setError("El archivo pasa de 8 MB."); return; }
    const esFoto = f.type.startsWith("image/");
    setArchivo(f); setVista(esFoto ? URL.createObjectURL(f) : null);
    setUso(esFoto ? (persona && !fotoPersona ? "foto" : null) : "leer");
    setCredito(""); setModificable(false); setTratamiento("foto");
  };
  const cancelar = () => { setArchivo(null); setVista(null); setUso(null); };
  const subir = async () => {
    if (!archivo || !uso) return;
    if (uso !== "leer" && !credito.trim()) { setError("Escribe el crédito de la foto: va en el pie de la publicación."); return; }
    setSubiendo(true); setError(null);
    try {
      if (uso === "foto") {
        const r = await api.subirFotoPersona(eid, pid, archivo, credito.trim(), modificable, modificable ? tratamiento : "foto");
        setLocales((x) => [...x, r.nota]);
        onCambio();
      } else {
        const m = await api.subirMaterial(eid, pid, archivo, credito.trim(), uso === "cubierta" ? "Cubierta de un libro de la pieza" : "");
        cancelar(); cargarAdjuntos();
        if (uso === "cubierta") { await enviar(`Usa la imagen que acabo de subir (${m.id}) como cubierta del libro.`); return; }
        setLocales((x) => [...x, `«${m.nombre}» adjunto: el editor lo tendrá delante en cada mensaje.`]);
      }
      cancelar(); cargarAdjuntos();
    } catch (e) {
      setError(mensajeError(e, "No se pudo subir."));
    } finally { setSubiendo(false); }
  };
  // Quitar un adjunto: al momento, con «Deshacer» unos segundos (4/11, usabilidad; antes fallaba en silencio)
  const [quitados, setQuitados] = useState<Set<string>>(new Set());
  const quitarAdjunto = (m: Material) => {
    setQuitados((x) => new Set(x).add(m.id));
    conDeshacer({ texto: `${m.nombre} quitado.`, hacer: async () => { await api.borrarMaterial(eid, pid, m.id); cargarAdjuntos(); },
                  alDeshacer: () => setQuitados((x) => { const n = new Set(x); n.delete(m.id); return n; }),
                  alFallar: (e) => avisar({ tipo: "mal", texto: mensajeError(e, "No se pudo quitar el adjunto.") }) });
  };

  const esFoto = !!archivo?.type.startsWith("image/");
  const chip = (activo: boolean) => `rounded-full border px-3 py-1 text-[12.5px] ${activo ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-papel hover:border-tinta"}`;

  return (
    <div className="flex min-h-0 flex-col gap-2.5 text-[13.5px]">
      <div className="flex max-h-[52vh] min-h-[120px] flex-col gap-2 overflow-y-auto lg:max-h-none lg:flex-1">
        {/* Lo que la máquina sabe que falta o que puede ofrecer, antes de la conversación */}
        {persona && !fotoPersona && (
          <div className="self-start rounded-[12px] border border-carmesi px-3 py-2 leading-snug">
            No tengo foto de <b>{persona}</b>. Si la tienes, adjúntala con el clip 📎.
          </div>
        )}
        {titulares.length > 0 && (
          <div className="flex flex-col gap-1.5 self-start">
            <button onClick={() => setVerTitulares((v) => !v)} className="self-start text-tinta-suave underline-offset-2 hover:text-tinta hover:underline">
              {verTitulares ? "▾" : "▸"} {titulares.length} titulares alternativos
            </button>
            {verTitulares && (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Titulares alternativos">
                {titulares.map((t) => t === titularActual
                  ? <span key={t} className="rounded-full border border-borde px-3 py-1 text-left text-[12.5px] text-tinta-suave">{t} · en uso</span>
                  : <button key={t} onClick={() => usarTitular(t)} disabled={!!usando}
                            className="rounded-full border border-carmesi px-3 py-1 text-left text-[12.5px] text-carmesi hover:bg-carmesi hover:text-papel">
                      {usando === t ? "…" : t}
                    </button>)}
              </div>
            )}
          </div>
        )}
        {mensajes.length === 0 && (
          <p className="text-tinta-suave">Pide un cambio: «el titular más corto», «menos técnico el cierre», «otra imagen en la portada»… Para hablar de una diapositiva, «Comentar» bajo el carrusel.</p>
        )}
        {mensajes.map((m, i) => (
          <div key={m.n} className={`flex max-w-[92%] flex-col gap-1.5 ${m.rol === "usuario" ? "self-end" : "self-start"}`}>
            <div className={`rounded-[12px] px-3 py-2 leading-snug ${m.rol === "usuario" ? "bg-tinta text-papel" : "border border-borde bg-panel"}`}>
              {m.rol === "editor" && m.agente && <span className="dato mb-0.5 block uppercase tracking-[0.12em]">{NOMBRE_ROL[m.agente] ?? m.agente}</span>}
              {m.rol === "usuario" && m.para && <span className="mb-0.5 block text-[11px] uppercase tracking-[0.12em] opacity-70">Para {NOMBRE_ROL[m.para] ?? m.para}</span>}
              {m.texto}
              {m.version_n && <span className="dato mt-1 block text-carmesi">→ versión {m.version_n}</span>}
            </div>
            {/* Las opciones del editor, como botones: solo las del último mensaje, y no mientras trabaja */}
            {m.rol === "editor" && i === mensajes.length - 1 && !enviando && m.opciones.length > 0 && (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Respuestas rápidas">
                {m.opciones.map((o) => (
                  <button key={o} onClick={() => enviar(o)}
                          className="rounded-full border border-carmesi px-3 py-1 text-left text-[12.5px] text-carmesi hover:bg-carmesi hover:text-papel">
                    {o}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {locales.map((l, i) => <p key={i} className="dato self-start">{l}</p>)}
        {enviando && <Trabajando segundos={segundos} para={para} mensaje={mensajes.at(-1)?.texto ?? ""} />}
        <div ref={final} />
      </div>

      {archivo && (
        <div className="flex flex-col gap-2 rounded-[12px] border border-borde bg-panel p-2.5">
          <div className="flex items-start gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local */}
            {vista ? <img src={vista} alt="" className="h-16 w-12 shrink-0 rounded-[4px] object-cover" />
                   : <span className="dato flex h-16 w-12 shrink-0 items-center justify-center rounded-[4px] bg-papel uppercase">{archivo.name.split(".").pop()}</span>}
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <span className="truncate font-semibold">{archivo.name}</span>
              {esFoto && (
                <div className="flex flex-wrap gap-1.5" role="group" aria-label="Qué es">
                  {persona && <button className={chip(uso === "foto")} onClick={() => setUso("foto")}>Foto de {persona}</button>}
                  <button className={chip(uso === "cubierta")} onClick={() => setUso("cubierta")}>Cubierta de un libro</button>
                  <button className={chip(uso === "leer")} onClick={() => setUso("leer")}>Para que la mire el editor</button>
                </div>
              )}
            </div>
          </div>
          {uso && (
            <input id={`credito-adjunto-${pid}`} value={credito} onChange={(e) => { setCredito(e.target.value); setError(null); }}
                   onKeyDown={(e) => { if (e.key === "Enter") subir(); }}
                   placeholder={uso === "leer" ? "Fuente o nota (opcional)" : "Crédito (obligatorio): «Foto: Ana Pérez · cortesía de Anagrama»"}
                   className="rounded-[8px] border border-borde bg-papel px-2 py-1.5 outline-none focus:border-tinta" />
          )}
          {uso === "foto" && (
            <>
              <label className="flex items-start gap-2">
                <input id={`modificable-${pid}`} type="checkbox" checked={modificable} onChange={(e) => setModificable(e.target.checked)} className="mt-1" />
                <span>Podemos modificarla <span className="text-tinta-suave">(libre o propia; las de prensa de las editoriales, no)</span></span>
              </label>
              {modificable && (
                <fieldset className="flex flex-wrap gap-x-3 gap-y-1">
                  <legend className="sr-only">Cómo va en la portada</legend>
                  {([["foto", "Tal cual"], ["papel", "Collage sobre papel"], ["escena", "Collage con escena (~25 créditos)"]] as const).map(([v, t]) => (
                    <label key={v} className="flex items-center gap-1.5">
                      <input type="radio" name={`tratamiento-${pid}`} checked={tratamiento === v} onChange={() => setTratamiento(v)} /> {t}
                    </label>
                  ))}
                </fieldset>
              )}
            </>
          )}
          <div className="flex gap-2">
            <button onClick={subir} disabled={subiendo || !uso} className="boton">
              {subiendo ? (uso === "foto" && modificable && tratamiento === "escena" ? "Dibujando la escena…" : "Subiendo…")
                : uso === "foto" ? "Poner en la portada" : uso === "cubierta" ? "Poner como cubierta" : uso === "leer" ? "Adjuntar" : "Elige qué es"}
            </button>
            <button onClick={cancelar} disabled={subiendo} className="boton-suave">Cancelar</button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 text-[12px]" role="group" aria-label="A quién va el mensaje">
        <span className="dato uppercase">Para</span>
        {DESTINOS.map((d) => (
          <button key={d.texto} aria-pressed={para === d.valor} onClick={() => setPara(d.valor)}
                  className={`rounded-full border px-2.5 py-0.5 ${para === d.valor ? "border-carmesi text-carmesi" : "border-borde bg-panel hover:border-tinta"}`}>
            {d.texto}
          </button>
        ))}
      </div>
      <div className="flex items-end gap-2">
        <button onClick={() => entrada.current?.click()} disabled={enviando || subiendo} aria-label="Adjuntar una foto, un PDF o un texto"
                title="Adjuntar una foto, un PDF o un texto" className="boton-suave px-3">📎</button>
        <textarea ref={caja} id={`chat-${pid}`} value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} disabled={enviando}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); } }}
                  placeholder="Escribe al equipo… (Intro para enviar)"
                  className="min-w-0 flex-1 resize-none rounded-[12px] border border-borde bg-panel p-2.5 text-[13.5px] outline-none focus:border-tinta" />
        <button onClick={() => enviar()} disabled={enviando || !texto.trim()} className="boton">→</button>
      </div>
      <input ref={entrada} type="file" hidden accept="image/jpeg,image/png,image/webp,application/pdf,text/plain,text/markdown,.md,.txt"
             onChange={(e) => { elegir(e.target.files?.[0]); e.target.value = ""; }} />
      {error && <p className="text-carmesi">{error}</p>}
      {adjuntos.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-tinta-suave">
          <span className="dato">Adjuntos</span>
          {adjuntos.filter((m) => !quitados.has(m.id)).map((m) => (
            <span key={m.id} className="inline-flex items-center gap-1">
              <a href={api.urlMaterial(eid, pid, m.id)} target="_blank" rel="noreferrer" className="max-w-[160px] truncate hover:underline">{m.nombre}</a>
              <button onClick={() => quitarAdjunto(m)} aria-label={`Quitar ${m.nombre}`} className="hover:text-carmesi">✕</button>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}


// Mientras el equipo trabaja (4/11, a petición del usuario: «mientras el director de arte esté trabajando, que quede
// claro que se está procesando una acción»): una burbuja viva con quién trabaja, qué está haciendo (por el tiempo y
// por lo que se ha pedido: una ilustración tarda hasta un minuto) y el reloj
const PIDE_IMAGEN = /ilustraci|imagen|foto|retrato|portada|banda|friso|collage|escena|dibuj|recorte|cubierta/i;

function Trabajando({ segundos, para, mensaje }: { segundos: number; para: string | null; mensaje: string }) {
  const imagen = para === "director_arte" || PIDE_IMAGEN.test(mensaje);
  const quien = para ? (NOMBRE_ROL[para] ?? "El equipo") : imagen ? "Director de arte" : "Editor";
  const paso = segundos < 6 ? "Lee la pieza y tu mensaje"
    : segundos < 20 ? "Decide el cambio"
    : imagen ? (segundos < 75 ? "Prepara la imagen (una ilustración tarda hasta un minuto)" : "Revisa la imagen y la pone en la pieza")
    : "Reescribe y comprueba las reglas";
  const m = Math.floor(segundos / 60), s = segundos % 60;
  return (
    <div className="flex max-w-[92%] flex-col gap-1.5 self-start" role="status" aria-live="polite">
      <div className="rounded-[12px] border border-carmesi bg-panel px-3 py-2 leading-snug">
        <span className="mb-1 flex items-center gap-2">
          <span className="trabajando__punto inline-block" style={{ background: "var(--carmesi)" }} aria-hidden />
          <span className="dato uppercase tracking-[0.12em]">{quien} · trabajando</span>
          <span className="dato ml-auto">{m}:{String(s).padStart(2, "0")}</span>
        </span>
        <span>{paso}<span className="puntos-vivos" aria-hidden /></span>
      </div>
    </div>
  );
}
