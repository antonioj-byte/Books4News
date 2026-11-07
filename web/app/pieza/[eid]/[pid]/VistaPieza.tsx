"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Atajos } from "@/components/Atajos";
import { Boton } from "@/components/Boton";
import { Carrusel } from "@/components/Carrusel";
import { DescargarZip } from "@/components/DescargarZip";
import { Descartar } from "@/components/Descartar";
import { ChatEdicion } from "@/components/ChatEdicion";
import { Creditos } from "@/components/Creditos";
import { FormEvaluacion } from "@/components/FormEvaluacion";
import { FotoPersona } from "@/components/FotoPersona";
import { EstadoChip, FormatoChip } from "@/components/Marcas";
import { Proceder } from "@/components/Proceder";
import { ProgramarBuffer } from "@/components/ProgramarBuffer";
import { PanelNoticia } from "@/components/PanelNoticia";
import { api, ESTADOS } from "@/lib/api";
import { conCursivas } from "@/lib/cursivas";
import { avisar } from "@/lib/avisos";
import { mensajeError } from "@/lib/errores";
import { useDatos } from "@/lib/useDatos";

// Vista de pieza en tres columnas: la noticia y sus avisos; el carrusel, con el texto editable sobre la
// diapositiva; y el chat de edición con la evaluación. En el móvil, una columna: carrusel, chat y
// evaluación, y la noticia al final.
function VerificarDeNuevo({ eid, pid, onHecho }: { eid: number; pid: string; onHecho: () => void }) {
  // El motivo real si falla (4/11, usabilidad: antes se tiraba el detalle, también el 409 de «se está escribiendo»)
  return (
    <Boton onClick={async () => { await api.verificarDeNuevo(eid, pid); onHecho(); }} trabajando="Verificando los libros…" hecho="Verificados">
      Volver a verificar los libros →
    </Boton>
  );
}

// «Más ▾»: se cierra al pulsar fuera, con Escape y al elegir un cambio de estado (4/11, usabilidad: antes se quedaba abierto)
function MenuMas({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const fuera = (e: MouseEvent) => { if (ref.current?.open && !ref.current.contains(e.target as Node)) ref.current.open = false; };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape" && ref.current) ref.current.open = false; };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", fuera); document.removeEventListener("keydown", escape); };
  }, []);
  return (
    <details ref={ref} className="relative">
      {children}
    </details>
  );
}

// Mientras carga la pieza: la forma de la página, no un «Cargando…» (4/11, usabilidad)
function EsqueletoPieza() {
  return (
    <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-[1fr_minmax(340px,440px)] lg:p-8" aria-busy="true" aria-label="Cargando la pieza">
      <div className="flex flex-col items-center gap-4">
        <div className="esqueleto h-8 w-2/3 self-start" />
        <div className="esqueleto aspect-[4/5] w-full max-w-[440px]" />
        <div className="flex gap-2">{Array.from({ length: 6 }, (_, i) => <div key={i} className="esqueleto h-16 w-12" />)}</div>
      </div>
      <div className="flex flex-col gap-3"><div className="esqueleto h-9 w-1/2" /><div className="esqueleto h-24 w-full" /><div className="esqueleto h-24 w-5/6" /></div>
    </div>
  );
}

export function VistaPieza() {
  const { eid: eidTexto, pid } = useParams<{ eid: string; pid: string }>();
  const eid = Number(eidTexto);
  const { datos: d, error, recargar: cargar } = useDatos(`pieza:${eid}:${pid}`, () => api.pieza(eid, pid));
  const [avisosEdicion, setAvisosEdicion] = useState<string[]>([]);
  const [pestana, setPestana] = useState<"chat" | "fuentes" | "evaluacion">("chat");
  const [borrador, setBorrador] = useState<{ texto: string } | null>(null);

  if (error) return (
    <div className="flex flex-col items-start gap-3 p-6">
      <p className="text-carmesi" role="alert">{error}</p>
      <div className="flex gap-2"><button className="boton-suave" onClick={cargar}>Volver a intentarlo</button><Link href="/hoy" className="boton-suave">Ir a la mesa de hoy</Link></div>
    </div>
  );
  if (!d) return <EsqueletoPieza />;
  const g = d.pieza.guion;
  // Retrato del autor generado con IA (folio.imagenes.retrato_generado): el estilo va en su crédito
  const estiloRetrato = d.pieza.arte?.retrato?.match(/retrato (.+?) generado con IA/)?.[1];

  const estado = d.pieza.estado;
  const escrita = !!g;
  const otrosEstados = ESTADOS.filter((e) => e.valor !== "descartada" && e.valor !== estado);

  // Dos columnas (3/11, «se está volviendo demasiado compleja la web»): el carrusel y, a la derecha, el chat (el único
  // sitio para pedir cambios), las fuentes y la evaluación en pestañas. Arriba, solo el paso siguiente.
  return (
    <div className="grid grid-cols-1 lg:h-screen lg:grid-cols-[1fr_minmax(340px,440px)]">
      <section className="min-w-0 px-4 py-5 lg:overflow-y-auto lg:px-8">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <Link href={`/dia/${d.fecha}?ejecucion=${eid}`} className="dato hover:text-carmesi">← HOY</Link>
            <EstadoChip estado={estado} />
            <FormatoChip formato={d.pieza.eleccion.formato ?? "lateral"} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {escrita && (estado === "propuesta" || estado === "en_edicion") && (
              <Boton onClick={async () => { await api.estado(eid, pid, "aprobada"); cargar(); }} hecho="Aprobada">Aprobar</Boton>
            )}
            {estado === "descartada" && (
              <Boton tipo="secundario" onClick={async () => { await api.estado(eid, pid, "propuesta"); cargar(); }} hecho="Recuperada">Recuperar</Boton>
            )}
            {estado !== "descartada" && <Descartar eid={eid} pid={pid} onHecho={cargar} />}
            <Atajos atajos={[
              { tecla: "A", texto: "Aprobar la pieza",
                hacer: escrita && (estado === "propuesta" || estado === "en_edicion")
                  ? () => { api.estado(eid, pid, "aprobada").then(() => { cargar(); avisar({ tipo: "ok", texto: `Pieza ${pid} aprobada.` }); })
                              .catch((e) => avisar({ tipo: "mal", texto: mensajeError(e, "No se pudo aprobar.") })); }
                  : undefined },
              { tecla: "/", texto: "Escribir al equipo (chat)",
                hacer: () => { setPestana("chat"); setTimeout(() => (document.getElementById(`chat-${pid}`) as HTMLTextAreaElement | null)?.focus(), 50); } },
              { tecla: "F", texto: "Ver las fuentes", hacer: () => setPestana("fuentes") },
              { tecla: "E", texto: "Ver la evaluación", hacer: () => setPestana("evaluacion") },
            ]} />
            <MenuMas>
              <summary className="boton-suave cursor-pointer list-none">Más ▾</summary>
              <div className="absolute right-0 z-20 mt-1.5 flex w-[260px] flex-col gap-2 rounded-[10px] border border-borde bg-panel p-3 text-[13px] shadow-lg">
                <span className="dato">{d.pieza.id} · versión {d.version}{(d.videos ?? []).length ? ` · vídeo en ${(d.videos ?? []).map((v) => v.n).join(", ")}` : ""}</span>
                {escrita && <DescargarZip eid={eid} pid={pid} />}
                {escrita && otrosEstados.length > 0 && (
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="dato">Pasar a</span>
                    {otrosEstados.map((e) => (
                      <Boton key={e.valor} tipo="secundario" hecho={null} onClick={async () => { await api.estado(eid, pid, e.valor); cargar(); }}>{e.texto}</Boton>
                    ))}
                  </span>
                )}
                {d.pieza.arte?.escena && (
                  <span><b>Ilustración</b>{d.pieza.arte.escena_idea ? ` · ${d.pieza.arte.escena_idea}` : ""}<span className="mt-1 block font-mono text-[11.5px] text-tinta-suave">{d.pieza.arte.escena}</span></span>
                )}
              </div>
            </MenuMas>
          </div>
        </div>
        <Creditos creditos={d.creditos ?? []} />
        {d.hechos_no_verificados.length > 0 && (
          <button onClick={() => setPestana("fuentes")}
                  className="mx-auto mb-4 block w-full max-w-[560px] rounded-[6px] border border-carmesi px-4 py-2.5 text-left text-[14px] hover:bg-papel-hondo">
            <b className="text-carmesi">{d.hechos_no_verificados.length === 1 ? "1 hecho sin verificar" : `${d.hechos_no_verificados.length} hechos sin verificar`}</b> · ver en Fuentes
          </button>
        )}
        {estiloRetrato && (
          <p className="mx-auto mb-4 max-w-[560px] rounded-[6px] bg-tinta px-4 py-2.5 text-[14px] text-papel">
            <b>Retrato {estiloRetrato.startsWith("dithering") ? "generado" : "3D"} del autor · {estiloRetrato}</b>, generado con IA a partir de su foto libre.
            Comprueba el parecido antes de aprobar.
          </p>
        )}
        {g ? (
          <>
            <Carrusel total={d.total_diapositivas || g.diapositivas.length} editables={g.diapositivas.length}
                      ancho={440} video={d.video_portada}
                      videos={Object.fromEntries((d.videos ?? []).map((v) => [v.n, v.url]))}
                      url={(n) => api.urlDiapositiva(eid, pid, n, d.version)}
                      onEditar={async (n, texto, subtitulo, firma) => {
                        const r = await api.editarDiapositiva(eid, pid, n, texto, subtitulo, firma);
                        setAvisosEdicion(r.avisos);
                        cargar();
                      }}
                      onQuitar={["cinco", "newsletter", "opinion"].includes(d.pieza.eleccion.formato ?? "") ? undefined : async (n) => {
                        // Al momento, con «Deshacer» (vuelve a la versión de antes como versión nueva)
                        const antes = d.version;
                        try {
                          const r = await api.quitarDiapositiva(eid, pid, n);
                          setAvisosEdicion(r.avisos);
                          cargar();
                          avisar({ tipo: "info", texto: `Diapositiva ${n} quitada`, duracion: 10000,
                                   accion: { texto: "Deshacer", hacer: async () => { await api.restaurarVersion(eid, pid, antes); setAvisosEdicion([]); cargar(); } } });
                        } catch (e) {
                          avisar({ tipo: "mal", texto: mensajeError(e) });
                        }
                      }}
                      extra={(n) => (
                        <button onClick={() => { setBorrador({ texto: `Diapositiva ${n}: ` }); setPestana("chat"); }} className="boton-suave">
                          Comentar
                        </button>
                      )} />
            {d.pieza.estado === "aprobada" && <ProgramarBuffer key={`buffer:${eid}/${pid}`} eid={eid} pid={pid} />}
            {avisosEdicion.length > 0 && (
              <div className="mx-auto mt-4 max-w-[560px] rounded-[6px] border border-carmesi px-4 py-2.5 text-[13px]">
                <b className="text-carmesi">Guardado, pero no cumple estas reglas del guion:</b>
                <ul className="mt-1 list-disc pl-5">{avisosEdicion.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
            )}
            {/* El pie y la idea, plegados (3/11): en el móvil dejaban el chat al fondo de la página */}
            <details className="mx-auto mt-6 max-w-[560px]">
              <summary className="cursor-pointer">
                <span className="antetitulo">Pie de Instagram e idea nueva</span>
                <span className="mt-1 block truncate text-[14px] text-tinta-suave">{g.pie_instagram}</span>
              </summary>
              <EditarPie key={`${d.version}`} pie={g.pie_instagram}
                         guardar={async (pie) => { const r = await api.editarPie(eid, pid, pie); setAvisosEdicion(r.avisos); cargar(); }} />
              <h3 className="antetitulo mb-2 mt-7">Idea nueva</h3>
              <p className="titular text-[22px] italic leading-snug" style={{ fontWeight: 400 }}>{conCursivas(g.idea_elegida)}</p>
              <p className="mt-2 text-[13px] text-tinta-suave">{g.por_que}</p>
            </details>
          </>
        ) : d.pieza.libros.length > 0 || ["curiosidad", "radar", "noticia", "ensayo"].includes(d.pieza.eleccion.formato) ? (
          // Propuesta de la mesa sin escribir (o cuyo guion falló): se ve la propuesta y se puede proceder
          <div className="mx-auto flex max-w-[560px] flex-col gap-4">
            <h2 className="titular text-[28px] leading-tight sm:text-[34px]">{d.pieza.eleccion.titular}</h2>
            {d.pieza.eleccion.gancho_libro && (
              <p className="titular text-[20px] italic leading-snug text-tinta-suave" style={{ fontWeight: 400 }}>{d.pieza.eleccion.gancho_libro}</p>
            )}
            {d.lomos.length === 0 && <p className="dato">{d.pieza.eleccion.formato === "radar" ? "Radar del libro" : "Historia editorial"} · sin libro</p>}
            <div className="flex flex-wrap gap-4">
              {d.lomos.map((l) => (
                <div key={l.titulo} className="flex items-center gap-3">
                  {l.cubierta
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <img src={l.cubierta} alt={`Cubierta de ${l.titulo}`} className="h-[120px] w-[80px] object-cover shadow-[var(--sombra-libro)]" />
                    : <div className="flex h-[120px] w-[80px] items-center justify-center bg-papel-hondo text-[11px] text-tinta-suave">sin cubierta</div>}
                  <div className="text-[14px]"><b>{l.titulo}</b><br /><span className="text-tinta-suave">{l.autor}</span></div>
                </div>
              ))}
            </div>
            <p className="text-[15px]"><b>De qué se habla.</b> {d.pieza.eleccion.de_que_se_habla}</p>
            <p className="text-[15px]"><b>Cuestión de fondo.</b> {d.pieza.eleccion.cuestion_de_fondo}</p>
            {d.pieza.error && <p className="text-[14px] text-carmesi">El intento anterior falló: {d.pieza.error}</p>}
            <Proceder eid={eid} pid={pid} onHecho={cargar} texto={d.pieza.error ? "Volver a intentarlo" : "Proceder: escribir la pieza"} />
            <p className="dato">Guion, comprobación de hechos, arte (con retrato 3D si toca), PNG y vídeo · unos minutos y unos 0,30 $</p>
          </div>
        ) : (
          // Falló sin libro (2/11): los motivos de cada descarte y la forma de reintentar (un catálogo caído de madrugada)
          <div className="mx-auto flex max-w-[560px] flex-col gap-3">
            <h2 className="titular text-[28px] leading-tight">{d.pieza.eleccion.titular}</h2>
            <p className="text-carmesi">{d.pieza.error}</p>
            {d.pieza.libros_descartados.length > 0 && (
              <ul className="list-disc pl-5 text-[14px]">
                {d.pieza.libros_descartados.map((x) => <li key={x.titulo}><i>{x.titulo}</i>, {x.autor}: {x.motivo}</li>)}
              </ul>
            )}
            <VerificarDeNuevo eid={eid} pid={pid} onHecho={cargar} />
            <p className="dato">Si ningún libro vale, descártala con su motivo o propón el tema de nuevo con el libro que quieras.</p>
          </div>
        )}
      </section>

      <aside className="flex min-h-0 flex-col border-t border-borde px-4 py-4 lg:border-l lg:border-t-0 lg:px-5">
        <nav className="mb-3 flex gap-1.5" aria-label="Panel de la pieza">
          {([["chat", "Chat"], ["fuentes", "Fuentes"], ["evaluacion", "Evaluación"]] as const).map(([v, t]) => (
            <button key={v} aria-pressed={pestana === v} onClick={() => setPestana(v)}
                    className={`rounded-full px-3.5 py-1.5 text-[13px] ${pestana === v ? "bg-tinta text-papel" : "bg-papel-hondo hover:bg-borde"}`}>
              {t}{v === "fuentes" && d.hechos_no_verificados.length ? ` · ${d.hechos_no_verificados.length}` : ""}{v === "evaluacion" && d.evaluacion ? " ✓" : ""}
            </button>
          ))}
        </nav>
        <div className={`min-h-0 flex-1 lg:overflow-y-auto ${pestana === "chat" ? "flex flex-col" : ""}`}>
          {pestana === "chat" && (g
            ? <ChatEdicion key={`chat:${eid}/${pid}`} eid={eid} pid={pid} onCambio={cargar}
                           titulares={g.titulares_alternativos ?? []} titularActual={g.diapositivas[0]?.texto ?? ""}
                           subtitulo={g.diapositivas[0]?.subtitulo ?? null}
                           persona={d.persona ?? null} fotoPersona={d.foto_persona ?? null} borrador={borrador} />
            : <div className="flex flex-col gap-3">
                <p className="text-[13px] text-tinta-suave">Cuando la pieza esté escrita, podrás pedirle cambios aquí.</p>
                {d.persona && (d.pieza.libros.length > 0 || d.pieza.eleccion.protagonista) && (
                  <FotoPersona key={`foto:${eid}/${pid}`} eid={eid} pid={pid} persona={d.persona} credito={d.foto_persona ?? null}
                               escrita={false} onHecho={cargar} />
                )}
              </div>)}
          {pestana === "fuentes" && <PanelNoticia d={d} />}
          {pestana === "evaluacion" && (
            <>
              <FormEvaluacion key={`${eid}/${pid}`} eid={eid} pid={pid} inicial={d.evaluacion ?? null} formato={d.pieza.eleccion.formato} />
              {d.evaluacion_version && d.evaluacion_version !== d.version && (
                <p className="dato mt-2">Evaluaste la versión {d.evaluacion_version}; la actual es la {d.version}.</p>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}


// El pie de Instagram, editable (4/11, a petición del usuario: «permite que se pueda editar el pie, que ahora no se
// puede»): se lee como antes y, con «Editar el pie», se cambia en un cuadro de texto y se guarda como versión nueva
function EditarPie({ pie, guardar }: { pie: string; guardar: (pie: string) => Promise<void> }) {
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(pie);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!editando) {
    return (
      <div className="mt-3">
        <p className="whitespace-pre-line text-[15px] leading-relaxed">{conCursivas(pie)}</p>
        <button className="boton-suave mt-2" onClick={() => { setTexto(pie); setEditando(true); }}>Editar el pie</button>
      </div>
    );
  }
  return (
    <div className="mt-3 flex flex-col gap-2">
      <label htmlFor="pie-editar" className="sr-only">Pie de Instagram</label>
      <textarea id="pie-editar" value={texto} onChange={(e) => setTexto(e.target.value)} rows={9} maxLength={3000} disabled={guardando}
                className="rounded-[12px] border border-borde bg-papel p-3 text-[15px] leading-relaxed outline-none focus:border-tinta" />
      <div className="flex flex-wrap items-center gap-2">
        <button className="boton" disabled={guardando || !texto.trim()}
                onClick={async () => {
                  setGuardando(true); setError(null);
                  try { await guardar(texto); setEditando(false); }
                  catch (e) { setError(mensajeError(e, "No se pudo guardar.")); }
                  finally { setGuardando(false); }
                }}>
          {guardando ? "Guardando…" : "Guardar el pie"}
        </button>
        <button className="text-[13px] underline" onClick={() => setEditando(false)} disabled={guardando}>Cancelar</button>
        <span className="dato">{texto.length} caracteres · Instagram admite 2.200; LinkedIn, 3.000 · los créditos se añaden al publicar</span>
      </div>
      {error && <p className="text-[13px] text-carmesi">{error}</p>}
    </div>
  );
}
