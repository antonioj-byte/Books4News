"use client";

// Avisos de la página (4/11, usabilidad): cualquier componente puede avisar (`avisar`) y el componente Avisos los
// enseña abajo. Los buenos se cierran solos; los malos se quedan. `conDeshacer` hace las acciones destructivas al
// momento en la pantalla pero las manda a la API unos segundos después, con «Deshacer» mientras tanto («deshacer antes
// que confirmar»); si se cierra la página antes, se mandan igual.

export type AvisoPagina = {
  id?: string;
  tipo: "ok" | "mal" | "info";
  texto: string;
  enlace?: { texto: string; href: string };
  accion?: { texto: string; hacer: () => void };
  duracion?: number;               // ms; por defecto 6 s los buenos y sin cierre los malos
};

const EVENTO = "folio:aviso";

export function avisar(a: AvisoPagina) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<AvisoPagina>(EVENTO, { detail: { id: `${Date.now()}-${Math.random()}`, ...a } }));
}

export function escucharAvisos(fn: (a: AvisoPagina) => void): () => void {
  const h = (e: Event) => fn((e as CustomEvent<AvisoPagina>).detail);
  window.addEventListener(EVENTO, h);
  return () => window.removeEventListener(EVENTO, h);
}

const pendientes = new Map<string, () => Promise<unknown>>();
let escuchandoSalida = false;

/** Hace `hacer` dentro de `segundos` salvo que se pulse «Deshacer». `alDeshacer` devuelve la pantalla a como estaba. */
export function conDeshacer({ texto, hacer, alDeshacer, alFallar, segundos = 7 }: {
  texto: string; hacer: () => Promise<unknown>; alDeshacer: () => void; alFallar?: (e: unknown) => void; segundos?: number;
}) {
  const id = `${Date.now()}-${Math.random()}`;
  const mandar = () => {
    const f = pendientes.get(id);
    if (!f) return;
    pendientes.delete(id);
    f().catch((e) => { alDeshacer(); alFallar?.(e); });
  };
  pendientes.set(id, hacer);
  if (!escuchandoSalida && typeof window !== "undefined") {
    escuchandoSalida = true;
    window.addEventListener("pagehide", () => { for (const k of [...pendientes.keys()]) { const f = pendientes.get(k); pendientes.delete(k); f?.(); } });
  }
  const t = setTimeout(mandar, segundos * 1000);
  avisar({ id, tipo: "info", texto, duracion: segundos * 1000,
           accion: { texto: "Deshacer", hacer: () => { clearTimeout(t); pendientes.delete(id); alDeshacer(); } } });
}
