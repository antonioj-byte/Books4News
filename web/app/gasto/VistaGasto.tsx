"use client";

import { useState } from "react";
import { api, type PanelGasto } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";

// Panel de gasto: lo que cuestan Anthropic (dólares) y Magnific (euros y créditos), hoy, este mes, cada día
// y por etapa. Sale del registro de la base de datos: cada llamada y cada imagen nueva dejan un apunte.
const ETAPAS: Record<string, string> = {
  resumen: "Resúmenes de la ingesta",
  seleccion: "Jefe de cultura (mesa del día)",
  "seleccion-completar": "Jefe de cultura (completar la mesa)",
  guion: "Guionista",
  hechos: "Comprobación de hechos",
  arte: "Director de arte (propuesta)",
  "arte-eleccion": "Director de arte (elección de imagen)",
  chat: "Chat de edición",
  ilustracion: "Ilustrador SVG (desactivado)",
  retrato: "Retratos generados",
  "ilustración": "Ilustraciones editoriales",
  esquema: "Esquemas de infografía",
  radar: "Radar del libro",
  memoria: "Memoria del feedback",
  escena: "Ilustrador (escenas)",
};

// Por debajo de un céntimo, con cuatro decimales: un resumen cuesta centésimas de céntimo
const cantidad = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: n > 0 && n < 0.01 ? 4 : 2 });
const dolares = (n: number) => `${cantidad(n)} $`;
const euros = (n: number) => `${cantidad(n)} €`;
const diaCorto = (f: string) => { const [, m, d] = f.split("-"); return `${Number(d)}/${Number(m)}`; };

function Cifra({ titulo, valor, detalle }: { titulo: string; valor: string; detalle?: string }) {
  return (
    <div className="panel flex flex-col gap-1 p-5">
      <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">{titulo}</span>
      <span className="titular text-[34px] leading-none tabular-nums">{valor}</span>
      {detalle && <span className="text-[13px] text-tinta-suave">{detalle}</span>}
    </div>
  );
}

// Barras por día de una sola serie: la marca lleva el color y el texto va en tinta. Tooltip al pasar.
function Barras({ titulo, dias, valor, formato, clase }: {
  titulo: string; dias: PanelGasto["dias"]; valor: (d: PanelGasto["dias"][number]) => number;
  formato: (n: number) => string; clase: string;
}) {
  const [encima, setEncima] = useState<number | null>(null);
  const max = Math.max(...dias.map(valor), 0);
  const alto = 140;
  const total = dias.reduce((s, d) => s + valor(d), 0);
  return (
    <figure className="panel m-0 p-5">
      <figcaption className="mb-3 flex items-baseline justify-between gap-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">{titulo}</span>
        <span className="text-[13px] tabular-nums">{formato(total)} en {dias.length} días</span>
      </figcaption>
      {max === 0 ? (
        <p className="py-8 text-center text-[14px] text-tinta-suave">Sin gasto en estos días.</p>
      ) : (
        <div className="relative">
          <span className="absolute left-0 top-0 font-mono text-[11px] tabular-nums text-tinta-suave">{formato(max)}</span>
          <div className="flex items-end gap-[2px] border-b border-tinta pt-5" style={{ height: alto + 20 }}
               onMouseLeave={() => setEncima(null)}>
            {dias.map((d, i) => {
              const v = valor(d);
              return (
                <button key={d.fecha} type="button" onMouseEnter={() => setEncima(i)} onFocus={() => setEncima(i)}
                        aria-label={`${diaCorto(d.fecha)}: ${formato(v)}`}
                        className="flex h-full min-w-0 flex-1 items-end focus-visible:outline-2 focus-visible:outline-carmesi">
                  <span className={`block w-full rounded-t-[4px] ${clase} ${encima === i ? "opacity-100" : "opacity-85"}`}
                        style={{ height: v ? Math.max(2, (v / max) * alto) : 0 }} />
                </button>
              );
            })}
          </div>
          <div className="mt-1 flex justify-between font-mono text-[11px] text-tinta-suave">
            <span>{diaCorto(dias[0].fecha)}</span><span>{diaCorto(dias[dias.length - 1].fecha)}</span>
          </div>
          {encima != null && (
            <div className="pointer-events-none absolute -top-2 rounded-[6px] bg-tinta px-2.5 py-1.5 text-[12px] text-papel shadow-lg"
                 style={{ left: `clamp(0px, calc(${((encima + 0.5) / dias.length) * 100}% - 60px), calc(100% - 120px))` }}>
              <b>{diaCorto(dias[encima].fecha)}</b> · {formato(valor(dias[encima]))}
              {dias[encima].magnific_imagenes > 0 && clase !== "bg-carmesi" && ` · ${dias[encima].magnific_imagenes} imágenes`}
            </div>
          )}
        </div>
      )}
    </figure>
  );
}

export function VistaGasto() {
  const [dias, setDias] = useState(30);
  const { datos: g, error } = useDatos(`gastos-${dias}`, () => api.gastos(dias));
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="antetitulo">Gasto</div>
      <h1 className="titular mb-2 mt-2 text-[40px] sm:text-[48px]">Lo que cuestan <em>las piezas</em></h1>
      <p className="mb-6 max-w-[62ch] text-[14px] text-tinta-suave">
        Anthropic (los agentes) en dólares y Magnific (retratos, ilustraciones y esquemas) en euros. Buffer, Europeana,
        Open Library y Google Books son gratis. Lo que sale de una caché no cuesta y no se apunta.
      </p>
      {error && <p className="text-carmesi">No se pudo cargar el gasto: {error}</p>}
      {g && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Cifra titulo="Anthropic, hoy" valor={dolares(g.anthropic_hoy_usd)} />
            <Cifra titulo="Anthropic, este mes" valor={dolares(g.anthropic_mes_usd)} />
            <Cifra titulo="Magnific, hoy" valor={euros(g.magnific_hoy_eur)} />
            <Cifra titulo="Magnific, este mes" valor={euros(g.magnific_mes_eur)}
                   detalle={`${g.magnific_mes_imagenes} imágenes · ${g.magnific_mes_creditos.toLocaleString("es-ES")} créditos`} />
          </div>

          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Días que se ven">
            {[7, 30, 90].map((n) => (
              <button key={n} onClick={() => setDias(n)} aria-pressed={dias === n} className="boton-suave">Últimos {n} días</button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Barras titulo="Anthropic por día" dias={g.dias} valor={(d) => d.anthropic_usd} formato={dolares} clase="bg-carmesi" />
            <Barras titulo="Magnific por día" dias={g.dias} valor={(d) => d.magnific_eur} formato={euros} clase="bg-tinta" />
          </div>

          <section className="panel overflow-x-auto p-5">
            <h2 className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">Este mes, por etapa</h2>
            {g.conceptos.length === 0 ? <p className="text-[14px] text-tinta-suave">Todavía no hay gasto este mes.</p> : (
              <table className="w-full min-w-[480px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-tinta text-left font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">
                    <th className="py-2">Etapa</th><th>Servicio</th><th className="text-right">Llamadas o imágenes</th><th className="text-right">Coste</th>
                  </tr>
                </thead>
                <tbody>
                  {g.conceptos.map((c) => (
                    <tr key={`${c.servicio}-${c.concepto}`} className="border-b border-borde">
                      <td className="py-2">{ETAPAS[c.concepto] ?? c.concepto}</td>
                      <td className="text-tinta-suave">{c.servicio === "anthropic" ? "Anthropic" : "Magnific"}</td>
                      <td className="text-right tabular-nums">{c.n}</td>
                      <td className="text-right tabular-nums">{c.moneda === "USD" ? dolares(c.coste) : euros(c.coste)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="panel overflow-x-auto p-5">
            <h2 className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-tinta-suave">Últimos apuntes</h2>
            <table className="w-full min-w-[560px] border-collapse text-[13px]">
              <tbody>
                {g.ultimos.map((a, i) => (
                  <tr key={i} className="border-b border-borde">
                    <td className="py-1.5 font-mono text-[11px] text-tinta-suave">{a.ts.slice(0, 16).replace("T", " ")}</td>
                    <td>{ETAPAS[a.concepto] ?? a.concepto}</td>
                    <td className="font-mono text-[11px] text-tinta-suave">{a.detalle}</td>
                    <td className="text-right tabular-nums">{a.moneda === "USD" ? dolares(a.coste) : euros(a.coste)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[12px] text-tinta-suave">
              Todo se apunta desde el {g.registro_desde}; de antes, solo las ejecuciones del día (sin «Proceder» ni chat).
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
