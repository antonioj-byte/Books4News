"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Trabajo } from "@/lib/api";

// Avisos de fin de tarea (2/11, a petición del usuario: «un sistema de notificaciones que permita ver en el navegador
// cuando una tarea se ha acabado»): cada 10 s mira los trabajos en segundo plano (ejecución del día, «Proceder»,
// tandas del fondo, Memoria) y, cuando uno termina, enseña un aviso en la página y, si se ha dado permiso, una
// notificación del navegador. Solo avisa de lo que acaba con la página abierta (también lo que dura segundos).
type Aviso = { clave: string; texto: string; ok: boolean };

const avisados = new Set<string>();      // «clave|fin» ya avisados en esta pestaña

function permisoInicial(): NotificationPermission | "no" {
  try { return typeof Notification === "undefined" ? "no" : Notification.permission; } catch { return "no"; }
}

export function Avisos() {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const [permiso, setPermiso] = useState<NotificationPermission | "no">("default");
  const fines = useRef<Map<string, string | null>>(new Map());   // clave → fin visto la última vez (null: en marcha)
  const primera = useRef(true);

  const mirar = useCallback(async () => {
    let lista: Trabajo[];
    try { lista = await api.trabajos(); } catch { return; }
    const nuevos: Aviso[] = [];
    for (const t of lista) {
      const fin = t.en_marcha ? null : (t.fin ?? null);
      const antes = fines.current.get(t.clave);
      fines.current.set(t.clave, fin);
      if (primera.current || fin === null || antes === fin) continue;
      // Acabó desde la última vez que se miró (también si fue tan rápido que no llegó a verse en marcha)
      const id = `${t.clave}|${fin}`;
      if (avisados.has(id)) continue;
      avisados.add(id);
      const ok = t.codigo === 0;
      nuevos.push({ clave: id, ok, texto: `${t.nombre}: ${ok ? "terminado" : `falló (código ${t.codigo ?? "?"})`}${!ok && t.ultima_linea ? ` · ${t.ultima_linea}` : ""}` });
    }
    primera.current = false;
    if (!nuevos.length) return;
    setAvisos((a) => [...a, ...nuevos].slice(-5));
    for (const n of nuevos) {
      try {
        if (typeof Notification !== "undefined" && Notification.permission === "granted") new Notification("Folio", { body: n.texto });
      } catch { /* sin notificaciones del sistema: queda el aviso en la página */ }
    }
  }, []);

  useEffect(() => {
    const t0 = setTimeout(() => { setPermiso(permisoInicial()); mirar(); }, 0);
    const t = setInterval(mirar, 10000);
    return () => { clearTimeout(t0); clearInterval(t); };
  }, [mirar]);

  const pedirPermiso = async () => {
    try { setPermiso(await Notification.requestPermission()); } catch { setPermiso("no"); }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 flex max-w-[360px] flex-col items-end gap-2 text-[13px]" aria-live="polite">
      {avisos.map((a) => (
        <div key={a.clave} className={`flex items-start gap-3 rounded-[10px] border px-4 py-3 shadow-lg ${a.ok ? "border-borde bg-papel" : "border-carmesi bg-papel"}`}>
          <span>{a.texto}</span>
          <button aria-label="Cerrar el aviso" className="text-tinta-suave hover:text-tinta" onClick={() => setAvisos((x) => x.filter((y) => y.clave !== a.clave))}>✕</button>
        </div>
      ))}
      {permiso === "default" && (
        <button className="boton-suave bg-papel shadow" onClick={pedirPermiso}>Avisarme cuando acabe una tarea</button>
      )}
    </div>
  );
}
