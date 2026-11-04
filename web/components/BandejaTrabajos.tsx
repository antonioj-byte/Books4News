"use client";

import { useEffect, useRef, useState } from "react";
import { useTrabajos } from "@/lib/trabajos";
import { reloj } from "@/components/Trabajando";
import { fraseDeFallo } from "@/lib/errores";

// La bandeja de trabajos (4/11, usabilidad: «saber qué pasa sin estar mirando»). En el menú, una pastilla con los
// trabajos en marcha; al pulsarla, cada uno con su paso y su reloj real, y los últimos que acabaron. Dentro, el permiso
// para las notificaciones del sistema (antes era un botón fijo abajo a la derecha que tapaba el de enviar del chat).
function permisoInicial(): NotificationPermission | "no" {
  try { return typeof Notification === "undefined" ? "no" : Notification.permission; } catch { return "no"; }
}

export function BandejaTrabajos({ estrecho = false }: { estrecho?: boolean }) {
  const trabajos = useTrabajos();
  const [abierta, setAbierta] = useState(false);
  const [permiso, setPermiso] = useState<NotificationPermission | "no">("default");
  const [ahora, setAhora] = useState(() => Date.now());
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = setTimeout(() => setPermiso(permisoInicial()), 0); return () => clearTimeout(t); }, []);
  const enMarcha = trabajos.filter((t) => t.en_marcha);
  useEffect(() => {
    if (!abierta && !enMarcha.length) return;
    const t = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(t);
  }, [abierta, enMarcha.length]);
  useEffect(() => {
    const fuera = (e: MouseEvent) => { if (abierta && !ref.current?.contains(e.target as Node)) setAbierta(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setAbierta(false); };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", fuera); document.removeEventListener("keydown", escape); };
  }, [abierta]);

  const acabados = trabajos.filter((t) => !t.en_marcha && t.fin).sort((a, b) => (b.fin ?? "").localeCompare(a.fin ?? "")).slice(0, 4);
  if (!trabajos.length && permiso !== "default") return null;
  const segundos = (inicio?: string | null) => inicio ? Math.max(0, (ahora - new Date(inicio).getTime()) / 1000) : 0;
  const pedirPermiso = async () => { try { setPermiso(await Notification.requestPermission()); } catch { setPermiso("no"); } };

  return (
    <div ref={ref} className="relative lg:px-1">
      <button onClick={() => setAbierta((x) => !x)} aria-expanded={abierta} aria-haspopup="dialog"
              title={enMarcha.length ? `${enMarcha.length} en marcha` : "Trabajos"}
              className={`flex w-full items-center gap-2 rounded-[10px] px-2.5 py-1.5 text-left text-[13px] hover:bg-papel-hondo ${enMarcha.length ? "font-semibold" : "text-tinta-suave"}`}>
        <span aria-hidden className={`h-2 w-2 flex-none rounded-full ${enMarcha.length ? "trabajando__punto bg-carmesi" : "bg-borde"}`} />
        <span className={estrecho ? "lg:hidden lg:group-hover/menu:inline" : ""}>
          {enMarcha.length ? `${enMarcha.length} en marcha` : "Trabajos"}
        </span>
      </button>
      {abierta && (
        <div role="dialog" aria-label="Trabajos en segundo plano"
             className="absolute left-0 top-full z-40 mt-1.5 flex w-[300px] flex-col gap-1 rounded-[12px] border border-borde bg-panel p-2 text-[13px] shadow-lg lg:left-1">
          {enMarcha.length === 0 && <p className="px-2 py-1.5 text-tinta-suave">Nada en marcha ahora.</p>}
          {enMarcha.map((t) => (
            <div key={t.clave} className="rounded-[8px] px-2 py-1.5">
              <div className="flex items-baseline justify-between gap-2"><b className="min-w-0 truncate">{t.nombre}</b><span className="font-mono text-[11.5px] text-tinta-suave">{reloj(segundos(t.inicio))}</span></div>
              <div className="dato truncate">{t.etapa ?? "Trabajando"}<span className="puntos-vivos" aria-hidden /></div>
              {t.tipico_s ? <span className="barra-trabajo mt-1"><i style={{ width: `${Math.min(96, (segundos(t.inicio) / t.tipico_s) * 100)}%` }} /></span> : null}
            </div>
          ))}
          {acabados.length > 0 && <span className="dato mt-1 px-2 uppercase">Acabaron</span>}
          {acabados.map((t) => (
            <div key={`${t.clave}|${t.fin}`} className="px-2 py-1">
              <span className={t.codigo === 0 ? "" : "text-carmesi"}>{t.codigo === 0 ? "✓" : "!"} {t.nombre}</span>
              {t.codigo !== 0 && <span className="block text-[12px] text-tinta-suave">{fraseDeFallo([t.ultima_linea]).titulo}</span>}
            </div>
          ))}
          {permiso === "default" && (
            <button className="boton-suave mt-1 self-start" onClick={pedirPermiso}>Avisarme también con notificaciones del sistema</button>
          )}
        </div>
      )}
    </div>
  );
}
