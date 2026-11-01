"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Carrusel } from "@/components/Carrusel";
import { ChatEdicion } from "@/components/ChatEdicion";
import { FormEvaluacion } from "@/components/FormEvaluacion";
import { EstadoChip, FormatoChip } from "@/components/Marcas";
import { Proceder } from "@/components/Proceder";
import { PanelNoticia } from "@/components/PanelNoticia";
import { api, ESTADOS } from "@/lib/api";
import { conCursivas } from "@/lib/cursivas";
import { useDatos } from "@/lib/useDatos";

// Vista de pieza en tres columnas: la noticia y sus avisos; el carrusel, con el texto editable sobre la
// diapositiva; y el chat de edición con la evaluación. En el móvil, una columna: carrusel, chat y
// evaluación, y la noticia al final.
export function VistaPieza() {
  const { eid: eidTexto, pid } = useParams<{ eid: string; pid: string }>();
  const eid = Number(eidTexto);
  const { datos: d, error, recargar: cargar } = useDatos(`pieza:${eid}:${pid}`, () => api.pieza(eid, pid));
  const [avisosEdicion, setAvisosEdicion] = useState<string[]>([]);

  if (error) return <p className="p-6 text-carmesi">{error}</p>;
  if (!d) return <p className="dato p-6">Cargando la pieza…</p>;
  const g = d.pieza.guion;
  // Retrato del autor generado con IA (folio.imagenes.retrato_generado): el estilo va en su crédito
  const estiloRetrato = d.pieza.arte?.retrato?.match(/retrato (.+?) generado con IA/)?.[1];

  return (
    <div className="grid grid-cols-1 lg:h-[calc(100vh-61px)] lg:grid-cols-[minmax(300px,370px)_1fr_minmax(300px,350px)]">
      <aside className="order-3 border-t border-borde px-4 py-5 lg:order-none lg:overflow-y-auto lg:border-r lg:border-t-0 lg:px-6">
        <Link href={`/dia/${d.fecha}?ejecucion=${eid}`} className="dato hover:text-carmesi">← PORTADA DEL DÍA</Link>
        <div className="mt-4"><PanelNoticia d={d} /></div>
      </aside>

      <section className="order-1 min-w-0 px-4 py-5 lg:order-none lg:overflow-y-auto lg:px-8">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <EstadoChip estado={d.pieza.estado} />
            <FormatoChip formato={d.pieza.eleccion.formato ?? "lateral"} />
            <span className="dato">{d.pieza.id} · versión {d.version}</span>
            {(d.videos ?? []).length > 0 && (
              <span className="dato text-carmesi">EN VÍDEO: {(d.videos ?? []).map((v) => v.n).join(", ")}</span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {ESTADOS.map((e) => (
              <button key={e.valor} onClick={() => api.estado(eid, pid, e.valor).then(cargar)}
                      aria-pressed={d.pieza.estado === e.valor} className="boton-suave">
                {e.texto}
              </button>
            ))}
          </div>
        </div>
        {d.pieza.arte?.escena && (
          <details className="mx-auto mb-4 max-w-[560px] rounded-[6px] border border-borde bg-panel px-4 py-2.5 text-[14px]">
            <summary className="cursor-pointer"><b>Ilustración editorial</b>{d.pieza.arte.escena_idea ? ` · ${d.pieza.arte.escena_idea}` : ""}</summary>
            <p className="mt-2 font-mono text-[12px] text-tinta-suave">{d.pieza.arte.escena}</p>
            <p className="mt-1 text-[12px] text-tinta-suave">Para otra, pídeselo al chat («dibuja otra ilustración con…»).</p>
          </details>
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
                      onEditar={async (n, texto, subtitulo) => {
                        const r = await api.editarDiapositiva(eid, pid, n, texto, subtitulo);
                        setAvisosEdicion(r.avisos);
                        cargar();
                      }} />
            <p className="mt-3 text-center">
              <a href={api.urlDescarga(eid, pid)} download className="boton-suave">Descargar el carrusel (.zip)</a>
              <span className="dato mt-2 block sm:ml-2 sm:mt-0 sm:inline">JPEG, vídeo de portada y pie · tarda hasta un minuto</span>
            </p>
            {avisosEdicion.length > 0 && (
              <div className="mx-auto mt-4 max-w-[560px] rounded-[6px] border border-carmesi px-4 py-2.5 text-[13px]">
                <b className="text-carmesi">Guardado, pero no cumple estas reglas del guion:</b>
                <ul className="mt-1 list-disc pl-5">{avisosEdicion.map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
            )}
            <div className="mx-auto mt-8 max-w-[560px]">
              <h3 className="antetitulo mb-2">Pie de Instagram</h3>
              <p className="whitespace-pre-line text-[15px] leading-relaxed">{conCursivas(g.pie_instagram)}</p>
              <h3 className="antetitulo mb-2 mt-7">Idea nueva</h3>
              <p className="titular text-[22px] italic leading-snug" style={{ fontWeight: 400 }}>{conCursivas(g.idea_elegida)}</p>
              <p className="mt-2 text-[13px] text-tinta-suave">{g.por_que}</p>
            </div>
          </>
        ) : d.pieza.libros.length > 0 ? (
          // Propuesta de la mesa sin escribir (o cuyo guion falló): se ve la propuesta y se puede proceder
          <div className="mx-auto flex max-w-[560px] flex-col gap-4">
            <h2 className="titular text-[28px] leading-tight sm:text-[34px]">{d.pieza.eleccion.titular}</h2>
            {d.pieza.eleccion.gancho_libro && (
              <p className="titular text-[20px] italic leading-snug text-tinta-suave" style={{ fontWeight: 400 }}>{d.pieza.eleccion.gancho_libro}</p>
            )}
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
          <p className="text-carmesi">Esta pieza no tiene guion: {d.pieza.error}</p>
        )}
      </section>

      <aside className="order-2 border-t border-borde px-4 py-5 lg:order-none lg:overflow-y-auto lg:border-l lg:border-t-0 lg:px-6">
        <h3 className="antetitulo mb-1">Chat de edición</h3>
        <p className="titular mb-3 text-[22px]">Pídele un <em>cambio</em></p>
        {g ? <ChatEdicion key={`chat:${eid}/${pid}`} eid={eid} pid={pid} onCambio={cargar} />
           : <p className="text-[13px] text-tinta-suave">Cuando la pieza esté escrita, podrás pedirle cambios aquí.</p>}
        <h3 className="antetitulo mb-2 mt-6 border-t border-borde pt-4">Evaluación</h3>
        <FormEvaluacion key={`${eid}/${pid}`} eid={eid} pid={pid} inicial={d.evaluacion ?? null} />
        {d.evaluacion_version && d.evaluacion_version !== d.version && (
          <p className="dato mt-2">Evaluaste la versión {d.evaluacion_version}; la actual es la {d.version}.</p>
        )}
      </aside>
    </div>
  );
}
