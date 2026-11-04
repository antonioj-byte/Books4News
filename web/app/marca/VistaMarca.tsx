"use client";

import { FormatoChip } from "@/components/Marcas";
import { api } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { EsqueletoPagina } from "@/components/Esqueleto";

// La memoria de marca (3/11, a petición del usuario: «cada cuenta tiene su propia memoria»): lo que comparten todos los
// roles cuando trabajan para Folio. Es lo que cambiaría al cambiar de cuenta; el equipo sería el mismo. De lectura.
function Apartado({ ante, titulo, texto, fuente }: { ante: string; titulo: string; texto: string; fuente?: string }) {
  return (
    <section className="panel flex flex-col gap-2 p-5">
      <span className="antetitulo">{ante}</span>
      <h2 className="titular text-[21px] leading-tight">{titulo}</h2>
      <p className="text-[14px] leading-relaxed">{texto}</p>
      {fuente && <span className="dato mt-auto">{fuente}</span>}
    </section>
  );
}

export function VistaMarca() {
  const { datos: m, error } = useDatos("marca", api.marca);
  if (error) return <p className="p-6 text-carmesi">{error}</p>;
  if (!m) return <EsqueletoPagina />;
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="antetitulo">La memoria de marca</div>
      <h1 className="titular mt-2 text-[40px] leading-tight">Así es <em>{m.nombre}</em></h1>
      <p className="mb-6 mt-2 max-w-[66ch] text-[15px] text-tinta-suave">{m.que_es}</p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Apartado ante="Línea editorial" {...m.linea_editorial} />
        <Apartado ante="Voz" {...m.voz} />
        <section className="panel flex flex-col gap-3 p-5">
          <span className="antetitulo">Diseño</span>
          <h2 className="titular text-[21px] leading-tight">{m.diseno.titulo}</h2>
          <div className="flex flex-wrap gap-2.5">
            {m.colores.map((c) => (
              <span key={c.nombre} className="flex w-[60px] flex-col gap-1 font-mono text-[10.5px] text-tinta-suave">
                <span className="h-11 rounded-[8px] border border-borde" style={{ background: c.valor }} />{c.nombre}
              </span>
            ))}
          </div>
          <p className="text-[14px] leading-relaxed">{m.diseno.texto}</p>
          <span className="dato">{m.letras.join(" · ")}</span>
        </section>
        <section className="panel flex flex-col gap-2 p-5 md:col-span-2">
          <span className="antetitulo">Formatos · {m.formatos.length}</span>
          <ul className="grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2">
            {m.formatos.map((f) => (
              <li key={f.id} className="flex flex-col gap-1">
                <span><FormatoChip formato={f.id} /></span>
                <span className="text-[13.5px] leading-snug text-tinta-suave">{f.descripcion}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel flex flex-col gap-2 p-5">
          <span className="antetitulo">Reglas de la casa</span>
          <ul className="flex list-disc flex-col gap-1.5 pl-4 text-[14px]">{m.reglas.map((r) => <li key={r}>{r}</li>)}</ul>
        </section>
        <section className="panel flex flex-col gap-2 p-5">
          <span className="antetitulo">Fuentes</span>
          <p className="titular text-[21px] leading-tight">{m.medios + m.medios_libro} medios y {m.editoriales} editoriales</p>
          <p className="text-[14px] text-tinta-suave">{m.medios} de actualidad, {m.medios_libro} del mundo del libro y los catálogos de {m.editoriales} editoriales independientes.</p>
        </section>
        <section className="panel flex flex-col gap-2 p-5 md:col-span-2">
          <span className="antetitulo">Aprendido de la redacción · {m.aprendidas.length}</span>
          {m.aprendidas.length === 0
            ? <p className="text-[14px] text-tinta-suave">Aún no hay reglas de marca aceptadas en Memoria.</p>
            : <ul className="flex flex-col gap-2 text-[14px]">{m.aprendidas.map((a) => <li key={a.patron} className="border-b border-borde pb-2 last:border-b-0">{a.propuesta}</li>)}</ul>}
        </section>
      </div>
    </div>
  );
}
