"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { escucharAvisos, type AvisoPagina } from "@/lib/avisos";
import { fraseDeFallo } from "@/lib/errores";
import { useTrabajos } from "@/lib/trabajos";

// Avisos de la página (2/11, a petición del usuario: «un sistema de notificaciones que permita ver en el navegador
// cuando una tarea se ha acabado»; 4/11, usabilidad: «saber qué pasa sin estar mirando»). Abajo a la derecha:
// - cuando acaba un trabajo en segundo plano (la ejecución del día, «Proceder», un tema, la newsletter…): si salió
//   bien, con un enlace a la mesa y se cierra solo a los 6 s; si falló, el motivo en una frase y se queda;
// - los que manda cualquier componente (`avisar`), como «Pieza descartada · Deshacer».
// Si se ha dado permiso (en la bandeja de trabajos del menú), también una notificación del sistema.
type Visible = AvisoPagina & { id: string };

const avisados = new Set<string>();      // «clave|fin» ya avisados en esta pestaña

export function Avisos() {
  const [avisos, setAvisos] = useState<Visible[]>([]);
  const trabajos = useTrabajos();
  const fines = useRef<Map<string, string | null> | null>(null);   // clave → fin visto la última vez (null: en marcha)

  const poner = (a: AvisoPagina) => {
    const v = { ...a, id: a.id ?? `${Date.now()}-${Math.random()}` } as Visible;
    setAvisos((x) => [...x.filter((y) => y.id !== v.id), v].slice(-4));
    const dura = a.duracion ?? (a.tipo === "mal" ? 0 : 6000);
    if (dura) setTimeout(() => setAvisos((x) => x.filter((y) => y.id !== v.id)), dura);
  };

  useEffect(() => escucharAvisos(poner), []);

  // Un trabajo que acaba entre dos miradas (también si fue tan rápido que no llegó a verse en marcha)
  useEffect(() => {
    const primera = fines.current === null;
    const vistos = fines.current ?? new Map<string, string | null>();
    const nuevos: AvisoPagina[] = [];
    for (const t of trabajos) {
      const fin = t.en_marcha ? null : (t.fin ?? null);
      const antes = vistos.get(t.clave);
      vistos.set(t.clave, fin);
      if (primera || fin === null || antes === fin) continue;
      const id = `${t.clave}|${fin}`;
      if (avisados.has(id)) continue;
      avisados.add(id);
      const ok = t.codigo === 0;
      const texto = ok ? `${t.nombre}: terminado.` : `${t.nombre}: ${fraseDeFallo([t.ultima_linea], "no ha salido bien.").titulo}`;
      nuevos.push({ id, tipo: ok ? "ok" : "mal", texto, enlace: { texto: ok ? "Ver la mesa" : "Ir a la mesa", href: "/" } });
      try {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") new Notification("Folio", { body: texto });
      } catch { /* sin notificaciones del sistema: queda el aviso en la página */ }
    }
    fines.current = vistos;
    if (nuevos.length) setTimeout(() => nuevos.forEach(poner), 0);
  }, [trabajos]);

  const cerrar = (id: string) => setAvisos((x) => x.filter((y) => y.id !== id));
  return (
    <div className="pointer-events-none fixed bottom-4 left-4 right-4 z-50 flex flex-col items-end gap-2 text-[13.5px] sm:left-auto sm:max-w-[400px]" aria-live="polite">
      {avisos.map((a) => (
        <div key={a.id} role={a.tipo === "mal" ? "alert" : "status"}
             className="aviso pointer-events-auto relative flex w-full items-center gap-3 overflow-hidden rounded-[12px] bg-tinta px-4 py-3 text-papel shadow-lg">
          <span aria-hidden className={`grid h-5 w-5 flex-none place-items-center rounded-full text-[12px] font-bold ${a.tipo === "ok" ? "bg-[#2E8B57]" : a.tipo === "mal" ? "bg-carmesi" : "bg-papel/25"}`}>
            {a.tipo === "ok" ? "✓" : a.tipo === "mal" ? "!" : "i"}
          </span>
          <span className="min-w-0 flex-1">{a.texto}</span>
          {a.accion && <button className="rounded-full border border-papel/70 px-3 py-1 font-semibold hover:bg-papel hover:text-tinta"
                               onClick={() => { a.accion!.hacer(); cerrar(a.id); }}>{a.accion.texto}</button>}
          {a.enlace && <Link href={a.enlace.href} onClick={() => cerrar(a.id)} className="whitespace-nowrap font-semibold underline underline-offset-2">{a.enlace.texto}</Link>}
          <button aria-label="Cerrar el aviso" className="text-papel/70 hover:text-papel" onClick={() => cerrar(a.id)}>✕</button>
          {(a.duracion ?? (a.tipo === "mal" ? 0 : 6000)) > 0 && (
            <span aria-hidden className="aviso__cuenta" style={{ animationDuration: `${a.duracion ?? 6000}ms` }} />
          )}
        </div>
      ))}
    </div>
  );
}
