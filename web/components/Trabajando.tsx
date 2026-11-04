"use client";

import { useEffect, useState } from "react";
import type { Fallo } from "@/lib/errores";

// La tarjeta de trabajo (3/11, a petición del usuario: «me pone nervioso que cuando esté trabajando el botón esté
// gris»; 4/11, usabilidad: una sola tarjeta para todas las esperas). Una píldora en tinta con una franja que avanza y
// un punto que late, el reloj real (desde que empezó en el servidor, no desde que se abrió la página), una barra con
// lo que suele tardar y los pasos del trabajo, con el que está en marcha encendido. Las etapas salen de las líneas
// «ETAPA: …» del registro; lo que suele tardar, de los registros anteriores (`tipico_s` de la API).

export type Paso = { id: string; texto: string; claves: string[] };

// Los pasos de «Proceder» (folio desarrollar): cada etapa del registro se reconoce por sus palabras
export const PASOS_PIEZA: Paso[] = [
  { id: "fuentes", texto: "Fuentes", claves: ["fuentes", "desarrollando", "empezando", "siguiendo"] },
  { id: "guion", texto: "Guion", claves: ["guionista", "guion"] },
  { id: "lector", texto: "Lector", claves: ["lector"] },
  { id: "arte", texto: "Hechos e imagen", claves: ["hechos", "imagen", "arte"] },
  { id: "pintar", texto: "Diapositivas", claves: ["pintando las diapositivas"] },
];

export const PASOS_NEWSLETTER: Paso[] = [
  { id: "frases", texto: "Titular y frases", claves: ["titular", "empezando"] },
  { id: "ilus", texto: "Ilustraciones", claves: ["ilustraciones"] },
  { id: "percha", texto: "Hechos", claves: ["comprobando"] },
  { id: "pintar", texto: "Diapositivas", claves: ["pintando"] },
];

export const PASOS_CINCO: Paso[] = [
  { id: "elegir", texto: "Noticias", claves: ["empezando", "cinco del libro"] },
  { id: "pintar", texto: "Diapositivas", claves: ["pintando"] },
];

export const PASOS_TEMA: Paso[] = [
  { id: "fuentes", texto: "Noticias", claves: ["empezando", "noticias", "fuentes", "busca"] },
  { id: "jefe", texto: "El jefe piensa", claves: ["jefe"] },
  { id: "libros", texto: "Libros", claves: ["libros", "verific"] },
];

function pasoActual(etapa: string, pasos: Paso[]): number {
  const e = etapa.toLowerCase();
  // De atrás adelante: «Pintando las diapositivas» no debe caer en «guion» por otra palabra
  for (let i = pasos.length - 1; i >= 0; i--) if (pasos[i].claves.some((c) => e.includes(c))) return i;
  return 0;
}

export function reloj(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function cuanto(s: number) {
  return s < 90 ? `${Math.round(s / 10) * 10 || 10} s` : `${Math.round(s / 60)} min`;
}

export function Trabajando({ etapa, pasos, rotulo = "Escribiendo", inicio, tipico, nota = true }: {
  etapa: string; pasos?: Paso[]; rotulo?: string;
  inicio?: string | null;           // cuándo empezó en el servidor (ISO); sin él, desde que se montó
  tipico?: number | null;           // lo que suele tardar, en segundos
  nota?: boolean;                   // «Puedes salir de la página…»
}) {
  const [desde] = useState(() => Date.now());
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const origen = inicio ? new Date(inicio).getTime() : desde;
  const segundos = Math.max(0, (ahora - (Number.isFinite(origen) ? origen : desde)) / 1000);
  const actual = pasos ? pasoActual(etapa, pasos) : 0;
  const pct = tipico ? Math.min(96, (segundos / tipico) * 100) : null;
  const tarde = !!tipico && segundos > tipico * 1.25;

  return (
    <div className="flex w-full max-w-[520px] flex-col items-start gap-2" role="status" aria-live="polite">
      <span className="trabajando">
        <span className="trabajando__punto" aria-hidden />
        <span>{rotulo}</span>
        <span className="font-mono text-[12.5px] opacity-75">{reloj(segundos)}{tipico ? ` · suele tardar ~${cuanto(tipico)}` : ""}</span>
      </span>
      {pct !== null && (
        <span className="barra-trabajo" aria-hidden><i style={{ width: `${pct}%` }} /></span>
      )}
      {pasos && (
        <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12.5px]" aria-label="Pasos">
          {pasos.map((p, i) => (
            <li key={p.id} className="flex items-center gap-1.5">
              <span className={i < actual ? "text-tinta-suave" : i === actual ? "paso-vivo font-semibold text-tinta" : "text-tinta-suave/60"}>
                {i < actual ? "✓ " : ""}{p.texto}
              </span>
              {i < pasos.length - 1 && <span className="text-borde" aria-hidden>—</span>}
            </li>
          ))}
        </ol>
      )}
      <span className="dato">
        {tarde ? "Tarda más de lo normal, pero sigue en marcha" : etapa.replace(/…$/, "")}<span className="puntos-vivos" aria-hidden />
      </span>
      {nota && <span className="text-[12px] text-tinta-suave">Puedes salir de la página: te aviso al acabar.</span>}
    </div>
  );
}

// Cuando un trabajo falla: la frase, el siguiente paso y el registro plegado
export function FalloTrabajo({ fallo, reintentar, texto = "Volver a intentarlo" }: {
  fallo: Fallo; reintentar?: () => void; texto?: string;
}) {
  return (
    <div className="flex w-full max-w-[520px] flex-col items-start gap-2 rounded-[10px] border border-carmesi/50 bg-panel px-3.5 py-3" role="alert">
      <p className="text-[14px] font-semibold text-carmesi">{fallo.titulo}</p>
      {reintentar && <button className="boton-suave" onClick={reintentar}>{texto}</button>}
      {fallo.detalle && (
        <details className="w-full text-[12px]">
          <summary className="cursor-pointer text-tinta-suave">Detalles técnicos</summary>
          <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-tinta-suave">{fallo.detalle}</pre>
        </details>
      )}
    </div>
  );
}
