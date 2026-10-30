"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Carrusel } from "@/components/Carrusel";
import { FormEvaluacion } from "@/components/FormEvaluacion";
import { EstadoChip } from "@/components/Marcas";
import { PanelNoticia } from "@/components/PanelNoticia";
import { api, ESTADOS } from "@/lib/api";
import { conCursivas } from "@/lib/cursivas";
import { useDatos } from "@/lib/useDatos";

// Vista de pieza en tres columnas: la noticia y sus avisos, el carrusel y la evaluación (el chat
// de edición llega en el paso 5).
export function VistaPieza() {
  const { eid: eidTexto, pid } = useParams<{ eid: string; pid: string }>();
  const eid = Number(eidTexto);
  const { datos: d, error, recargar: cargar } = useDatos(`pieza:${eid}:${pid}`, () => api.pieza(eid, pid));

  if (error) return <p className="p-6 text-carmesi">{error}</p>;
  if (!d) return <p className="dato p-6">Cargando la pieza…</p>;
  const g = d.pieza.guion;

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
        {g ? (
          <>
            <Carrusel total={g.diapositivas.length} ancho={440}
                      url={(n) => api.urlDiapositiva(eid, pid, n, d.version)} />
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
        <h3 className="antetitulo mb-1">Evaluación</h3>
        <p className="titular mb-4 text-[24px]">¿La <em>publicarías</em>?</p>
        <FormEvaluacion key={`${eid}/${pid}`} eid={eid} pid={pid} inicial={d.evaluacion ?? null} />
        {d.evaluacion_version && d.evaluacion_version !== d.version && (
          <p className="dato mt-2">Evaluaste la versión {d.evaluacion_version}; la actual es la {d.version}.</p>
        )}
        <div className="mt-8 border-t border-borde pt-4 text-[13px] text-tinta-suave">
          <h3 className="antetitulo mb-1">Chat de edición</h3>
          Llega en el paso 5.
        </div>
      </aside>
    </div>
  );
}
