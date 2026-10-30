"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Carrusel } from "@/components/Carrusel";
import { FormEvaluacion } from "@/components/FormEvaluacion";
import { EstadoChip } from "@/components/Marcas";
import { PanelNoticia } from "@/components/PanelNoticia";
import { api, ESTADOS, type PiezaDetalle } from "@/lib/api";

// Vista de pieza en tres columnas: la noticia y sus avisos, el carrusel y la evaluación (el chat
// de edición llega en el paso 5).
export function VistaPieza() {
  const { eid: eidTexto, pid } = useParams<{ eid: string; pid: string }>();
  const eid = Number(eidTexto);
  const [d, setD] = useState<PiezaDetalle | null>(null);
  const [error, setError] = useState("");
  const cargar = useCallback(() => {
    api.pieza(eid, pid).then(setD).catch((e) => setError(String(e)));
  }, [eid, pid]);
  useEffect(cargar, [cargar]);

  if (error) return <p className="p-6 text-acento">{error}</p>;
  if (!d) return <p className="p-6 text-tinta-suave">Cargando la pieza…</p>;
  const g = d.pieza.guion;

  return (
    <div className="grid h-[calc(100vh-58px)] grid-cols-[minmax(300px,360px)_1fr_minmax(300px,340px)]">
      <aside className="overflow-y-auto border-r border-filete px-5 py-4">
        <Link href={`/dia/${d.fecha}?ejecucion=${eid}`} className="text-sm text-tinta-suave hover:text-acento">← Portada del día</Link>
        <div className="mt-3"><PanelNoticia d={d} /></div>
      </aside>

      <section className="overflow-y-auto px-6 py-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <EstadoChip estado={d.pieza.estado} />
            <span className="text-sm text-tinta-suave">{d.pieza.id} · versión {d.version}</span>
          </div>
          <div className="flex gap-1">
            {ESTADOS.map((e) => (
              <button key={e.valor} onClick={() => api.estado(eid, pid, e.valor).then(cargar)}
                      className={`rounded-sm border px-2 py-1 text-[12px] ${d.pieza.estado === e.valor ? "border-tinta bg-tinta text-papel" : "border-filete hover:border-tinta"}`}>
                {e.texto}
              </button>
            ))}
          </div>
        </div>
        {g ? (
          <>
            <Carrusel total={g.diapositivas.length} ancho={460}
                      url={(n) => api.urlDiapositiva(eid, pid, n, d.version)} />
            <div className="mx-auto mt-6 max-w-[560px]">
              <h3 className="rotulo mb-2">Pie de Instagram</h3>
              <p className="whitespace-pre-line font-texto text-[16px] leading-relaxed">{g.pie_instagram}</p>
              <h3 className="rotulo mb-2 mt-6">Idea nueva</h3>
              <p className="font-texto text-[16px] italic">{g.idea_elegida}</p>
              <p className="mt-1 text-[13px] text-tinta-suave">{g.por_que}</p>
            </div>
          </>
        ) : (
          <p className="text-acento">Esta pieza no tiene guion: {d.pieza.error}</p>
        )}
      </section>

      <aside className="overflow-y-auto border-l border-filete px-5 py-4">
        <h3 className="rotulo mb-3">Evaluación</h3>
        <FormEvaluacion key={`${eid}/${pid}`} eid={eid} pid={pid} inicial={d.evaluacion ?? null} />
        {d.evaluacion_version && d.evaluacion_version !== d.version && (
          <p className="mt-2 text-[12px] text-tinta-suave">Evaluaste la versión {d.evaluacion_version}; la actual es la {d.version}.</p>
        )}
        <div className="mt-8 border-t border-filete pt-3 text-[13px] text-tinta-suave">
          <h3 className="rotulo mb-1">Chat de edición</h3>
          Llega en el paso 5.
        </div>
      </aside>
    </div>
  );
}
