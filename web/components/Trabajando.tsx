"use client";

import { useEffect, useState } from "react";

// Mientras se escribe una pieza (3/11, a petición del usuario: «me pone nervioso que cuando esté trabajando el botón
// esté gris»): en vez de un botón apagado, una píldora en tinta con una franja que avanza, un punto que late, el reloj
// y los pasos del trabajo, con el que está en marcha encendido. Las etapas salen de las líneas «ETAPA: …» del registro.

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

function pasoActual(etapa: string, pasos: Paso[]): number {
  const e = etapa.toLowerCase();
  // De atrás adelante: «Pintando las diapositivas» no debe caer en «guion» por otra palabra
  for (let i = pasos.length - 1; i >= 0; i--) if (pasos[i].claves.some((c) => e.includes(c))) return i;
  return 0;
}

function reloj(s: number) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function Trabajando({ etapa, pasos, rotulo = "Escribiendo" }: { etapa: string; pasos: Paso[]; rotulo?: string }) {
  const [inicio] = useState(() => Date.now());
  const [segundos, setSegundos] = useState(0);
  const actual = pasoActual(etapa, pasos);

  useEffect(() => {
    const t = setInterval(() => setSegundos(Math.floor((Date.now() - inicio) / 1000)), 1000);
    return () => clearInterval(t);
  }, [inicio]);

  return (
    <div className="flex flex-col items-start gap-2" role="status" aria-live="polite">
      <span className="trabajando">
        <span className="trabajando__punto" aria-hidden />
        <span>{rotulo}</span>
        <span className="font-mono text-[12.5px] opacity-75">{reloj(segundos)}</span>
      </span>
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
      <span className="dato">
        {etapa.replace(/…$/, "")}<span className="puntos-vivos" aria-hidden />
      </span>
    </div>
  );
}
