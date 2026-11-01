// Cliente de la API local. Los tipos salen del OpenAPI de FastAPI (`npm run tipos`).
import type { components } from "./tipos";

export type Dia = components["schemas"]["Dia"];
export type DiaDetalle = components["schemas"]["DiaDetalle"];
export type PiezaResumen = components["schemas"]["PiezaResumen"];
export type PiezaDetalle = components["schemas"]["PiezaDetalle"];
export type Pieza = components["schemas"]["Pieza"];
export type Evaluacion = components["schemas"]["Evaluacion-Output"];
export type ResumenDia = components["schemas"]["ResumenDia"];
export type Estado = components["schemas"]["CambioEstado"]["estado"];
export type EstadoEjecucion = components["schemas"]["EstadoEjecucion"];
export type ResultadoEdicion = components["schemas"]["ResultadoEdicion"];
export type MensajeChat = components["schemas"]["MensajeChat"];
export type RespuestaChat = components["schemas"]["RespuestaChat"];
export type PanelGasto = components["schemas"]["PanelGasto"];
export type Tema = components["schemas"]["Tema"];
export type TemaNuevo = components["schemas"]["TemaNuevo"];
export type TemaCreado = components["schemas"]["TemaCreado"];
export type Material = components["schemas"]["Material"];
export type EstadoMemoria = components["schemas"]["EstadoMemoria"];
export type Patron = components["schemas"]["Patron"] & { estado: "propuesta" | "aceptada" | "rechazada" | "aplicada" };
export type ResultadoMemoria = components["schemas"]["ResultadoMemoria"];
export type EstadoBuffer = components["schemas"]["EstadoBuffer"];

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const r = await fetch(ruta, { cache: "no-store", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!r.ok) {
    const cuerpo = await r.text();
    // La API explica el error en «detail»: es lo que se enseña, no el JSON entero
    let detalle = cuerpo.slice(0, 300);
    try { const d = JSON.parse(cuerpo).detail; if (typeof d === "string") detalle = d; } catch { /* no era JSON */ }
    throw new Error(`${r.status} ${ruta}: ${detalle}`);
  }
  return r.json() as Promise<T>;
}

const pieza = (eid: number, pid: string) => `/api/ejecuciones/${eid}/piezas/${pid}`;

export const api = {
  dias: () => pedir<Dia[]>("/api/dias"),
  dia: (fecha: string, ejecucion?: number) =>
    pedir<DiaDetalle>(`/api/dias/${fecha}${ejecucion ? `?ejecucion=${ejecucion}` : ""}`),
  pieza: (eid: number, pid: string) => pedir<PiezaDetalle>(pieza(eid, pid)),
  estado: (eid: number, pid: string, estado: Estado) =>
    pedir(`${pieza(eid, pid)}/estado`, { method: "PATCH", body: JSON.stringify({ estado }) }),
  guardarEvaluacion: (eid: number, pid: string, ev: Evaluacion) =>
    pedir<Evaluacion>(`${pieza(eid, pid)}/evaluacion`, { method: "PUT", body: JSON.stringify(ev) }),
  resumen: () => pedir<ResumenDia[]>("/api/evaluaciones/resumen"),
  gastos: (dias: number) => pedir<PanelGasto>(`/api/gastos?dias=${dias}`),
  memoria: () => pedir<Patron[]>("/api/memoria"),
  estadoMemoria: () => pedir<EstadoMemoria>("/api/memoria/estado"),
  analizarMemoria: (dias: number) => pedir<ResultadoMemoria>(`/api/memoria/analizar?dias=${dias}`, { method: "POST" }),
  decidirPatron: (id: number, estado: Patron["estado"], nota = "") =>
    pedir<unknown>(`/api/memoria/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ estado, nota }) }),
  lanzarEjecucion: () => pedir<EstadoEjecucion>("/api/ejecuciones/lanzar", { method: "POST" }),
  // «Proceder»: escribe una propuesta pendiente de la mesa (unos minutos; se sigue con ejecucionEnMarcha)
  desarrollar: (eid: number, pid: string) =>
    pedir<EstadoEjecucion>(`${pieza(eid, pid)}/desarrollar`, { method: "POST" }),
  ejecucionEnMarcha: () => pedir<EstadoEjecucion>("/api/ejecuciones/en-marcha"),
  editarDiapositiva: (eid: number, pid: string, n: number, texto: string, subtitulo?: string | null) =>
    pedir<ResultadoEdicion>(`${pieza(eid, pid)}/diapositivas/${n}`, { method: "PUT", body: JSON.stringify({ texto, subtitulo }) }),
  chat: (eid: number, pid: string) => pedir<MensajeChat[]>(`${pieza(eid, pid)}/chat`),
  temas: () => pedir<Tema[]>("/api/temas"),
  proponerTema: (t: TemaNuevo) => pedir<TemaCreado>("/api/temas", { method: "POST", body: JSON.stringify(t) }),
  descartarTema: (id: number) => pedir<Tema>(`/api/temas/${id}`, { method: "DELETE" }),
  materiales: (eid: number, pid: string) => pedir<Material[]>(`/api/ejecuciones/${eid}/piezas/${pid}/materiales`),
  subirMaterial: (eid: number, pid: string, archivo: File, credito: string, nota: string) =>
    pedir<Material>(`/api/ejecuciones/${eid}/piezas/${pid}/materiales?${new URLSearchParams({ nombre: archivo.name, credito, nota })}`,
      { method: "POST", body: archivo, headers: { "Content-Type": archivo.type || "application/octet-stream" } }),
  borrarMaterial: (eid: number, pid: string, mid: string) =>
    pedir<unknown>(`/api/ejecuciones/${eid}/piezas/${pid}/materiales/${mid}`, { method: "DELETE" }),
  urlMaterial: (eid: number, pid: string, mid: string) => `/api/ejecuciones/${eid}/piezas/${pid}/materiales/${mid}`,
  enviarChat: (eid: number, pid: string, mensaje: string) =>
    pedir<RespuestaChat>(`${pieza(eid, pid)}/chat`, { method: "POST", body: JSON.stringify({ mensaje }) }),
  // Programar en Buffer la pieza aprobada (a una hora, a la cola o como borrador)
  buffer: (eid: number, pid: string) => pedir<EstadoBuffer>(`${pieza(eid, pid)}/buffer`),
  programarBuffer: (eid: number, pid: string, cuerpo: { hora: string | null; borrador: boolean; reemplazar: boolean }) =>
    pedir<EstadoBuffer>(`${pieza(eid, pid)}/buffer`, { method: "POST", body: JSON.stringify(cuerpo) }),
  // El carrusel listo para publicar (JPEG, vídeo de portada y pie), de la versión actual
  urlDescarga: (eid: number, pid: string) => `${pieza(eid, pid)}/descarga.zip`,
  urlDiapositiva: (eid: number, pid: string, n: number, version: number) =>
    `${pieza(eid, pid)}/diapositivas/${n}.html?version=${version}`,
};

export const ESTADOS: { valor: Estado; texto: string }[] = [
  { valor: "propuesta", texto: "Propuesta" },
  { valor: "en_edicion", texto: "En edición" },
  { valor: "aprobada", texto: "Aprobada" },
  { valor: "descartada", texto: "Descartada" },
];
