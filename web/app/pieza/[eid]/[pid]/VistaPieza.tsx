"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Carrusel } from "@/components/Carrusel";
import { ChatEdicion } from "@/components/ChatEdicion";
import { FormEvaluacion } from "@/components/FormEvaluacion";
import { EstadoChip } from "@/components/Marcas";
import { PanelNoticia } from "@/components/PanelNoticia";
import { api, ESTADOS } from "@/lib/api";
import { conCursivas } from "@/lib/cursivas";
import { useDatos } from "@/lib/useDatos";

// Vista de pieza en tres columnas: la noticia y sus avisos; el carrusel, con el texto editable sobre la
// diapositiva; y el chat de edición con la evaluación.
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
    <div className="grid h-[calc(100vh-61px)] grid-cols-[minmax(300px,370px)_1fr_minmax(300px,350px)]">
      <aside className="overflow-y-auto border-r border-borde px-6 py-5">
        <Link href={`/dia/${d.fecha}?ejecucion=${eid}`} className="dato hover:text-carmesi">← PORTADA DEL DÍA</Link>
        <div className="mt-4"><PanelNoticia d={d} /></div>
      </aside>

      <section className="overflow-y-auto px-8 py-5">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <EstadoChip estado={d.pieza.estado} />
            <span className="dato">{d.pieza.id} · versión {d.version}</span>
            {d.video_portada && <span className="dato text-carmesi">PORTADA EN VÍDEO</span>}
          </div>
          <div className="flex gap-1.5">
            {ESTADOS.map((e) => (
              <button key={e.valor} onClick={() => api.estado(eid, pid, e.valor).then(cargar)}
                      aria-pressed={d.pieza.estado === e.valor} className="boton-suave">
                {e.texto}
              </button>
            ))}
          </div>
        </div>
        {estiloRetrato && (
          <p className="mx-auto mb-4 max-w-[560px] rounded-[6px] bg-tinta px-4 py-2.5 text-[14px] text-papel">
            <b>Retrato {estiloRetrato.startsWith("dithering") ? "generado" : "3D"} del autor · {estiloRetrato}</b>, generado con IA a partir de su foto libre.
            Comprueba el parecido antes de aprobar.
          </p>
        )}
        {g ? (
          <>
            <Carrusel total={g.diapositivas.length} ancho={440} video={d.video_portada}
                      url={(n) => api.urlDiapositiva(eid, pid, n, d.version)}
                      onEditar={async (n, texto, subtitulo) => {
                        const r = await api.editarDiapositiva(eid, pid, n, texto, subtitulo);
                        setAvisosEdicion(r.avisos);
                        cargar();
                      }} />
            <p className="mt-3 text-center">
              <a href={api.urlDescarga(eid, pid)} download className="boton-suave">Descargar el carrusel (.zip)</a>
              <span className="dato ml-2">JPEG, vídeo de portada y pie · tarda hasta un minuto</span>
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
        ) : (
          <p className="text-carmesi">Esta pieza no tiene guion: {d.pieza.error}</p>
        )}
      </section>

      <aside className="overflow-y-auto border-l border-borde px-6 py-5">
        <h3 className="antetitulo mb-1">Chat de edición</h3>
        <p className="titular mb-3 text-[22px]">Pídele un <em>cambio</em></p>
        <ChatEdicion key={`chat:${eid}/${pid}`} eid={eid} pid={pid} onCambio={cargar} />
        <h3 className="antetitulo mb-2 mt-6 border-t border-borde pt-4">Evaluación</h3>
        <FormEvaluacion key={`${eid}/${pid}`} eid={eid} pid={pid} inicial={d.evaluacion ?? null} />
        {d.evaluacion_version && d.evaluacion_version !== d.version && (
          <p className="dato mt-2">Evaluaste la versión {d.evaluacion_version}; la actual es la {d.version}.</p>
        )}
      </aside>
    </div>
  );
}
