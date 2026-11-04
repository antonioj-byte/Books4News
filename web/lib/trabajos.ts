"use client";

import { useEffect, useState } from "react";
import { api, type Trabajo } from "@/lib/api";

// Los trabajos en segundo plano, con una sola consulta compartida (4/11, usabilidad): la bandeja del menú y los avisos
// de fin de tarea leen de aquí. Cada 4 s si hay algo en marcha; cada 15 s si no.
let lista: Trabajo[] = [];
const oyentes = new Set<(l: Trabajo[]) => void>();
let temporizador: ReturnType<typeof setTimeout> | null = null;

async function mirar() {
  try { lista = await api.trabajos(); oyentes.forEach((f) => f(lista)); } catch { /* sin conexión: se reintenta */ }
  temporizador = setTimeout(mirar, lista.some((t) => t.en_marcha) ? 4000 : 15000);
}

/** Pide mirar ya (p. ej. justo después de lanzar algo). */
export function mirarTrabajos() {
  if (temporizador) clearTimeout(temporizador);
  mirar();
}

export function useTrabajos(): Trabajo[] {
  const [l, setL] = useState<Trabajo[]>(lista);
  useEffect(() => {
    oyentes.add(setL);
    if (oyentes.size === 1) mirar();
    return () => { oyentes.delete(setL); if (!oyentes.size && temporizador) { clearTimeout(temporizador); temporizador = null; } };
  }, []);
  return l;
}
