"use client";

import Link from "next/link";
import { useState } from "react";
import { Newsletter } from "@/components/Newsletter";
import { SeguirTrabajo } from "@/components/SeguirTrabajo";
import { PASOS_TEMA } from "@/components/Trabajando";
import { api, type Tema, type TemaCreado } from "@/lib/api";
import { conDeshacer } from "@/lib/avisos";
import { mensajeError as fraseDeError } from "@/lib/errores";
import { TarjetaPorElegir } from "@/components/TarjetaPorElegir";
import { useDatos } from "@/lib/useDatos";

const ESTADOS: Record<string, string> = {
  pendiente: "Para la mesa de mañana", en_mesa: "En la mesa", no_elegido: "El jefe no lo llevó",
  fallido: "No se pudo", descartado: "Descartado", pregunta: "El jefe pregunta",
};

// La conversación con el jefe sobre un tema y el campo para contestarle o replicarle (2/11)
function Conversacion({ tema, eid, onPieza, onCambio }: { tema: Tema; eid?: number; onPieza: () => void; onCambio: () => void }) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [siguiendo, setSiguiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // La réplica va en segundo plano (4/11, usabilidad): se puede salir de la página y el jefe sigue pensando
  const responder = async (propio?: string, enfoque?: "noticia") => {
    const m = (propio ?? texto).trim();
    if (m.length < 2 || enviando || siguiendo || !eid) return;
    setEnviando(true); setError(null);
    try {
      await api.replicarTema(tema.id, { texto: m, ejecucion: eid, segundo_plano: true, ...(enfoque ? { enfoque } : {}) });
      setTexto(""); setSiguiendo(true);
    } catch (e) {
      setError(fraseDeError(e, "No se pudo enviar."));
    } finally { setEnviando(false); }
  };
  const ocupado = enviando || siguiendo;
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-[12px] border border-borde bg-panel p-3 text-[14px]">
      {tema.conversacion.map((t, i) => (
        <p key={i} className={t.rol !== "redaccion" ? "whitespace-pre-line" : "self-end rounded-[10px] bg-tinta px-3 py-1.5 text-papel"}>
          {t.rol !== "redaccion" && <span className="dato mr-2 uppercase text-carmesi">{t.rol === "jefe" ? "Jefe" : "Verificación"}</span>}{String(t.texto ?? "")}
        </p>
      ))}
      <div className="flex gap-2">
        <textarea id={`replica-${tema.id}`} value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} disabled={ocupado}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); responder(); } }}
                  placeholder={tema.estado === "pregunta" ? "Contesta al jefe…" : "Replica a la propuesta: «otro libro», «más perfil y menos noticia»… Los datos y enlaces que pegues pasan a la pieza"}
                  className="min-w-0 flex-1 resize-none rounded-[10px] border border-borde bg-papel p-2 outline-none focus:border-tinta" />
        <button onClick={() => responder()} disabled={ocupado || texto.trim().length < 2 || !eid} aria-busy={enviando || undefined} className="boton self-end">
          Enviar
        </button>
      </div>
      {/* Se engancha también si se recarga la página con el jefe pensando */}
      <SeguirTrabajo key={siguiendo ? "s" : "n"} clave={`tema-${tema.id}`} pasos={PASOS_TEMA} rotulo="El jefe piensa"
                     onHecho={(r) => { setSiguiendo(false); onCambio(); if ((r as TemaCreado | null)?.pieza_id) onPieza(); }} />
      {tema.estado === "en_mesa" && tema.pieza_id && eid && (
        // 3/11 («hemos entrado en un bucle raro»): con la propuesta en la mesa, el paso siguiente es escribirla
        <Link href={`/pieza/${eid}/${tema.pieza_id}`} className="boton self-start">Escribir la pieza →</Link>
      )}
      {tema.enfoque !== "noticia" && tema.estado !== "pregunta" && (
        // 3/11: si el jefe hizo un ensayo y solo se quería la noticia, un clic lo rehace como «Noticia»
        <button onClick={() => responder("Solo la noticia: cuéntala con su contexto, sin ensayo ni libro ajeno.", "noticia")}
                disabled={ocupado || !eid} className="self-start rounded-full border border-carmesi px-3 py-1 text-[12.5px] text-carmesi hover:bg-carmesi hover:text-papel">
          Solo la noticia
        </button>
      )}
      {error && <p className="text-carmesi">{error}</p>}
    </div>
  );
}

// Proponer un tema al jefe de cultura (2/11): ahora (una pieza pendiente en esta mesa) o para la mesa de mañana.
// Lo que admite la API para el texto de un tema (3/11: subido de 1.500 a 6.000 para encargos enteros)
const MAX_TEXTO = 6000;

// Un error de validación de la API, en una frase (antes salía el JSON entero)
function mensajeError(e: unknown): string {
  const m = e instanceof Error ? e.message : "";
  if (m.includes("string_too_long")) return `El texto es demasiado largo: como mucho ${MAX_TEXTO} caracteres.`;
  return fraseDeError(e, "No se pudo proponer.");
}

const MAX_NEWSLETTER = 40000;

// `modo` (7/11, «Hoy» en dos pestañas): «caja», solo el cuadro de arriba; «lista», solo los encargos, con la tarjeta
// común de «Por elegir»; sin él, los dos (como antes)
export function ProponerTema({ eid, onPieza, modo, onTema }: { eid?: number; onPieza: () => void; modo?: "caja" | "lista"; onTema?: () => void }) {
  const [texto, setTexto] = useState("");
  const [enlaces, setEnlaces] = useState("");
  const [enviando, setEnviando] = useState<"ahora" | "manana" | null>(null);
  // Lo que pide la redacción (3/11, «si lo que le pido es que me cuente una noticia… no me haga un ensayo»)
  const [enfoque, setEnfoque] = useState<"elige" | "noticia" | "ensayo" | "perfil" | "newsletter" | "opinion">("elige");
  const largo = enfoque === "newsletter" || enfoque === "opinion";   // se pega el texto entero (7/11: también la opinión)
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null);
  const { datos: temas, recargar } = useDatos("temas", api.temas);
  const [abierto, setAbierto] = useState<number | null>(null);

  // «Ahora» va en segundo plano (4/11, usabilidad: «nada atado a la página»): se responde al momento, el jefe trabaja
  // aparte y la tarjeta de trabajo lo sigue; si se sale de la página, al volver se engancha desde la lista de temas
  const [siguiendo, setSiguiendo] = useState<number | null>(null);
  const alAcabar = (tid: number, r: TemaCreado | null) => {
    setSiguiendo(null); recargar(); onTema?.();
    if (!r) return;
    setAbierto(tid);
    setMensaje({ ok: true, texto: r.preguntas.length ? "El jefe necesita saber algo antes de proponer: contéstale abajo."
      : r.estado_pieza === "pendiente" ? `El jefe lo ha llevado a la mesa (${r.pieza_id}): pulsa «Proceder» para escribirlo, o replícale abajo.`
      : r.pieza_id ? `El jefe propuso un enfoque, pero ninguno de sus libros pasó la verificación (están en la propuesta ${r.pieza_id}, en la mesa). Replícale abajo con el libro que quieras, o pídele otros.`
      : r.respuesta || "El jefe ha respondido: míralo abajo." });
    if (r.pieza_id) onPieza();
  };
  const proponer = async (cuando: "ahora" | "manana") => {
    if (texto.trim().length < 8 || enviando || siguiendo) return;
    setEnviando(cuando); setMensaje(null);
    try {
      const r = await api.proponerTema({ texto: texto.trim(), enlaces: enlaces.split(/\s+/).filter(Boolean), cuando, ejecucion: eid ?? null,
                                         enfoque: enfoque === "newsletter" || enfoque === "opinion" ? "elige" : enfoque, segundo_plano: cuando === "ahora" });
      setTexto(""); setEnlaces("");
      if (cuando === "manana") setMensaje({ ok: true, texto: "Guardado: el jefe lo verá en la mesa de mañana." });
      else setSiguiendo(r.tema.id);
    } catch (e) {
      setMensaje({ ok: false, texto: mensajeError(e) });
    } finally { setEnviando(null); recargar(); onTema?.(); }
  };
  // Descartar un tema: al momento en la lista, con «Deshacer» unos segundos (4/11, usabilidad; antes fallaba en silencio)
  const [ocultos, setOcultos] = useState<Set<number>>(new Set());
  const descartar = (t: Tema) => {
    setOcultos((x) => new Set(x).add(t.id));
    conDeshacer({ texto: "Tema descartado.", hacer: async () => { await api.descartarTema(t.id); recargar(); },
                  alDeshacer: () => setOcultos((x) => { const n = new Set(x); n.delete(t.id); return n; }),
                  alFallar: (e) => setMensaje({ ok: false, texto: fraseDeError(e, "No se pudo descartar el tema.") }) });
  };
  const recientes = (temas ?? []).filter((t) => !ocultos.has(t.id)).slice(0, 6);

  const abiertoForm = texto.length > 0 || !!enviando || enlaces.length > 0 || largo;
  const pendientes = recientes.filter((t) => t.estado === "pregunta").length;
  // 6/11 («¿no es un poco feo ver todo el historial de peticiones?»): a la vista, solo lo de hoy y lo que pide algo
  // (una pregunta del jefe, un tema en marcha o uno que falló); lo demás, plegado en «Anteriores», en una línea
  const hoy = new Date().toLocaleDateString("sv-SE");
  const pideAlgo = (t: Tema) => ["pregunta", "pendiente", "fallido"].includes(t.estado) || abierto === t.id;
  const aLaVista = recientes.filter((t) => pideAlgo(t) || t.creado_en.slice(0, 10) === hoy);
  const anteriores = recientes.filter((t) => !aLaVista.includes(t));

  if (modo === "lista") {
    // Los encargos de hoy y los que piden algo, como tarjetas; los que ya están en la mesa salen con su propuesta
    const visibles = aLaVista.filter((t) => t.estado !== "en_mesa" || abierto === t.id);
    return (
      <>
        {visibles.map(tarjeta)}
        {anteriores.length > 0 && (
          <details>
            <summary className="dato cursor-pointer uppercase text-tinta-suave">Encargos anteriores · {anteriores.length}</summary>
            <ul className="mt-1.5 flex flex-col gap-1 text-[13.5px] text-tinta-suave">{anteriores.map(fila)}</ul>
          </details>
        )}
      </>
    );
  }

  // Arriba de la mesa y en compacto (3/11, «se está volviendo demasiado compleja la web»): una línea que se abre al escribir
  return (
    <section aria-labelledby="h-tema" className="mb-8">
      <div className="panel flex flex-col gap-3 p-3 sm:p-4">
        <label id="h-tema" htmlFor="tema-texto" className="sr-only">Proponer un tema al jefe de cultura</label>
        <textarea id="tema-texto" value={texto} onChange={(e) => setTexto(e.target.value)} rows={abiertoForm ? 3 : 1} disabled={!!enviando}
                  maxLength={largo ? MAX_NEWSLETTER : MAX_TEXTO}
                  placeholder={enfoque === "newsletter" ? "Pega aquí el texto entero de la newsletter." : enfoque === "opinion" ? "Pega aquí el artículo de opinión entero." : "¿De qué quieres que hablemos hoy? El jefe de cultura le busca el ángulo y el libro."}
                  className="resize-none rounded-[12px] border border-borde bg-papel px-3 py-2.5 text-[16px] outline-none focus:border-tinta" />
        {abiertoForm && (
          <>
            {!largo && <textarea id="tema-enlaces" value={enlaces} onChange={(e) => setEnlaces(e.target.value)} rows={2} disabled={!!enviando}
                      placeholder={enfoque === "ensayo" ? "Enlaces, si los tienes (uno por línea). Sin enlaces, busca él las fuentes." : "Enlaces, si los tienes (uno por línea). Sin enlaces, busca él las noticias."}
                      aria-label="Enlaces (opcional)"
                      className="resize-y rounded-[12px] border border-borde bg-papel p-3 font-mono text-[13px] outline-none focus:border-tinta" />}
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Qué le pides al jefe">
              {([["elige", "Que el jefe elija"], ["noticia", "Solo la noticia"], ["ensayo", "Ensayo sin percha"], ["perfil", "Perfil de autor"], ["newsletter", "Newsletter del jueves"], ["opinion", "Opinión"]] as const).map(([v, txt]) => (
                <button key={v} aria-pressed={enfoque === v} onClick={() => setEnfoque(v)} disabled={!!enviando}
                        className={`rounded-full border px-3 py-1 text-[13px] ${enfoque === v ? "border-carmesi bg-carmesi text-papel" : "border-borde bg-papel hover:border-tinta"}`}>
                  {txt}
                </button>
              ))}
              <span className="text-[12.5px] text-tinta-suave">
                {enfoque === "newsletter" ? "La versión corta en Instagram del ensayo de los jueves, con tus frases literales."
                  : enfoque === "opinion" ? "Un artículo de otra firma con el carrusel de la newsletter: su foto, su nombre y sus frases literales."
                  : enfoque === "noticia" ? "Contada con su contexto, sin ensayo ni libro ajeno."
                  : enfoque === "ensayo" ? "Un tema literario con su historia, sin noticia ni libro obligatorio. Sigue tu estructura y tu tono."
                  : enfoque === "perfil" ? "Una escritora o un escritor: trayectoria, sus libros, una frase suya y lo que dice la prensa. Escribe su nombre y la percha, si la hay."
                  : "Lectura lateral, diálogo, tres libros… lo que mejor le vaya."}
              </span>
            </div>
            {largo ? <Newsletter key={enfoque} formato={enfoque === "opinion" ? "opinion" : "newsletter"} texto={texto} onHecho={() => { setTexto(""); onPieza(); }} /> : <>
            {texto.length > MAX_TEXTO * 0.8 && (
              <span className={`dato ${texto.length >= MAX_TEXTO ? "text-carmesi" : ""}`}>{texto.length} de {MAX_TEXTO} caracteres</span>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button className="boton" onClick={() => proponer("ahora")} disabled={!!enviando || !!siguiendo || !eid || texto.trim().length < 8}
                      aria-busy={enviando === "ahora" || undefined}>
                Proponer ahora<span className="boton__coste">~1–2 min · ~0,10 $</span>
              </button>
              <button className="boton-suave" onClick={() => proponer("manana")} disabled={!!enviando || texto.trim().length < 8 || enfoque !== "elige"}
                      title={enfoque !== "elige" ? "La mesa de mañana solo propone piezas con libro" : undefined}>
                {enviando === "manana" ? "Guardando…" : "Para la mesa de mañana"}
              </button>
            </div>
            </>}
          </>
        )}
        {abiertoForm && !largo && !eid && <span className="motivo">Para proponerlo ahora hace falta la mesa del día (lanza antes la ejecución); para mañana, sí se puede</span>}
        {abiertoForm && !largo && eid && texto.trim().length > 0 && texto.trim().length < 8 && <span className="motivo">Escribe un poco más: al menos una frase</span>}
        {siguiendo && <SeguirTrabajo clave={`tema-${siguiendo}`} pasos={PASOS_TEMA} rotulo="El jefe piensa" siFalla="El jefe no ha podido proponer el tema."
                                     onHecho={(r) => alAcabar(siguiendo, r as TemaCreado | null)} />}
        {mensaje && <p className={mensaje.ok ? "text-[14px]" : "text-[14px] text-carmesi"} role={mensaje.ok ? "status" : "alert"}>{mensaje.texto}</p>}
      </div>
      {modo !== "caja" && recientes.length > 0 && (
        <div className="mt-2 text-[13.5px]">
        {aLaVista.length > 0 && (
          <>
          <p className="dato uppercase">Hoy{pendientes ? ` · ${pendientes} con pregunta del jefe` : ""}</p>
          <ul className="mt-1.5 flex flex-col gap-1.5">{aLaVista.map(fila)}</ul>
          </>
        )}
        {anteriores.length > 0 && (
          <details className={aLaVista.length ? "mt-2" : ""}>
            <summary className="dato cursor-pointer uppercase text-tinta-suave">Temas anteriores · {anteriores.length}</summary>
            <ul className="mt-1.5 flex flex-col gap-1 text-tinta-suave">{anteriores.map(fila)}</ul>
          </details>
        )}
        </div>
      )}
    </section>
  );

  function tarjeta(t: Tema) {
    const conversa = (t.estado === "pregunta" || t.estado === "en_mesa" || (t.estado === "fallido" && t.pieza_id)) && t.conversacion.length > 0;
    return (
      <TarjetaPorElegir key={t.id}
        etiquetas={<><span className="chip bg-tinta text-papel">Encargo</span>
          <span className={`chip ${t.estado === "pregunta" || t.estado === "fallido" ? "bg-carmesi text-papel" : "border border-borde"}`}>{ESTADOS[t.estado] ?? t.estado}</span></>}
        titulo={<span className="line-clamp-3" title={t.texto}>{t.texto}</span>}
        linea={t.nota && t.estado !== "en_mesa" ? (t.nota === "Ningún libro candidato se pudo verificar" ? "Ninguno de los libros del jefe pasó la verificación: replícale con otro." : t.nota) : undefined}
        acciones={<>
          {conversa && (
            <button onClick={() => setAbierto(abierto === t.id ? null : t.id)} className="boton">
              {abierto === t.id ? "Cerrar" : t.estado === "pregunta" ? "Contestar al jefe →" : "Replicar"}
            </button>
          )}
          {t.estado === "pendiente" && <button onClick={() => descartar(t)} className="boton-suave">Descartar</button>}
        </>}>
        {t.estado === "pendiente" && t.cuando === "ahora" && t.id !== siguiendo && (
          <SeguirTrabajo clave={`tema-${t.id}`} pasos={PASOS_TEMA} rotulo="El jefe piensa" onHecho={(r) => alAcabar(t.id, r as TemaCreado | null)} />
        )}
        {abierto === t.id && <Conversacion tema={t} eid={eid} onPieza={onPieza} onCambio={recargar} />}
      </TarjetaPorElegir>
    );
  }

  function fila(t: Tema) {
    return (
            <li key={t.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="dato uppercase text-tinta-suave">{ESTADOS[t.estado] ?? t.estado}{t.pieza_id ? ` · ${t.pieza_id}` : ""}</span>
              <span className="min-w-0 flex-1 truncate" title={t.texto}>{t.texto}</span>
              {t.estado === "pendiente" && <button onClick={() => descartar(t)} className="text-tinta-suave hover:text-carmesi">Descartar</button>}
              {(t.estado === "pregunta" || t.estado === "en_mesa" || (t.estado === "fallido" && t.pieza_id)) && t.conversacion.length > 0 && (
                <button onClick={() => setAbierto(abierto === t.id ? null : t.id)} className="text-tinta-suave underline-offset-2 hover:text-tinta hover:underline">
                  {abierto === t.id ? "Cerrar" : t.estado === "pregunta" ? "Contestar" : "Replicar"}
                </button>
              )}
              {t.estado === "pendiente" && t.cuando === "ahora" && t.id !== siguiendo && (
                <span className="basis-full"><SeguirTrabajo clave={`tema-${t.id}`} pasos={PASOS_TEMA} rotulo="El jefe piensa" onHecho={(r) => alAcabar(t.id, r as TemaCreado | null)} /></span>
              )}
              {t.nota && t.estado !== "en_mesa" && (
                <span className="basis-full text-tinta-suave">{t.nota === "Ningún libro candidato se pudo verificar" ? "Ninguno de los libros del jefe pasó la verificación: replícale con otro." : t.nota}</span>
              )}
              {abierto === t.id && <div className="basis-full"><Conversacion tema={t} eid={eid} onPieza={onPieza} onCambio={recargar} /></div>}
            </li>
    );
  }
}
