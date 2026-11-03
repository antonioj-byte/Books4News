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
export type Nota = components["schemas"]["Nota"];
export type EstadoMemoria = components["schemas"]["EstadoMemoria"];
export type Patron = components["schemas"]["Patron"] & { estado: "propuesta" | "aceptada" | "rechazada" | "aplicada" };
export type EstadoBuffer = components["schemas"]["EstadoBuffer"];
export type Fondo = components["schemas"]["Fondo"];
export type Trabajo = components["schemas"]["Trabajo"];
export type PropuestaDelFondo = components["schemas"]["PropuestaDelFondo"];
// La agencia (3/11): Archivo, Equipo, Marca y créditos de cada pieza
export type PiezaArchivo = components["schemas"]["PiezaArchivo"];
export type Departamento = components["schemas"]["Departamento"];
export type ResumenRol = components["schemas"]["ResumenRol"];
export type DetalleRol = components["schemas"]["DetalleRol"];
export type Marca = components["schemas"]["Marca"];
export type Credito = components["schemas"]["Credito"];
export type Para = "guionista" | "director_arte" | "jefe_cultura";
export type Capa = "oficio" | "marca" | "celda";

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
  // El análisis va en un proceso aparte (2/11: dentro de la petición, la web cortaba a los 5 minutos)
  analizarMemoria: (dias: number) => pedir<EstadoEjecucion>(`/api/memoria/analizar?dias=${dias}`, { method: "POST" }),
  analisisMemoria: () => pedir<EstadoEjecucion | null>("/api/memoria/analisis"),
  decidirPatron: (id: number, estado: Patron["estado"], nota = "", capa?: Capa) =>
    pedir<unknown>(`/api/memoria/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ estado, nota, ...(capa ? { capa } : {}) }) }),
  archivo: () => pedir<PiezaArchivo[]>("/api/archivo"),
  equipo: () => pedir<Departamento[]>("/api/equipo"),
  rol: (id: string) => pedir<DetalleRol>(`/api/equipo/${id}`),
  marca: () => pedir<Marca>("/api/marca"),
  lanzarEjecucion: () => pedir<EstadoEjecucion>("/api/ejecuciones/lanzar", { method: "POST" }),
  // «Proceder»: escribe una propuesta pendiente de la mesa (unos minutos; se sigue con `desarrollo`). Varias a la vez.
  desarrollar: (eid: number, pid: string) =>
    pedir<EstadoEjecucion>(`${pieza(eid, pid)}/desarrollar`, { method: "POST" }),
  desarrollo: (eid: number, pid: string) => pedir<EstadoEjecucion>(`${pieza(eid, pid)}/desarrollo`),
  ejecucionEnMarcha: () => pedir<EstadoEjecucion>("/api/ejecuciones/en-marcha"),
  editarDiapositiva: (eid: number, pid: string, n: number, texto: string, subtitulo?: string | null) =>
    pedir<ResultadoEdicion>(`${pieza(eid, pid)}/diapositivas/${n}`, { method: "PUT", body: JSON.stringify({ texto, subtitulo }) }),
  chat: (eid: number, pid: string) => pedir<MensajeChat[]>(`${pieza(eid, pid)}/chat`),
  temas: () => pedir<Tema[]>("/api/temas"),
  trabajos: () => pedir<Trabajo[]>("/api/trabajos"),
  // El fondo del mes (2/11)
  fondo: () => pedir<Fondo>("/api/fondo"),
  escribirDelFondo: (id: number, ejecucion: number) =>
    pedir<TemaCreado>(`/api/fondo/${id}/escribir`, { method: "POST", body: JSON.stringify({ ejecucion }) }),
  descartarDelFondo: (id: number) => pedir<PropuestaDelFondo>(`/api/fondo/${id}/descartar`, { method: "POST" }),
  lanzarCinco: (fecha: string) => pedir<EstadoEjecucion>(`/api/cinco/${fecha}`, { method: "POST" }),
  estadoCinco: () => pedir<EstadoEjecucion>("/api/cinco"),
  prepararFondo: (tandas: number) => pedir<EstadoEjecucion>("/api/fondo/preparar", { method: "POST", body: JSON.stringify({ tandas }) }),
  proponerTema: (t: TemaNuevo) => pedir<TemaCreado>("/api/temas", { method: "POST", body: JSON.stringify(t) }),
  replicarTema: (id: number, r: { texto: string; ejecucion: number; enfoque?: "elige" | "noticia" }) =>
    pedir<TemaCreado>(`/api/temas/${id}/replica`, { method: "POST", body: JSON.stringify(r) }),
  descartarTema: (id: number) => pedir<Tema>(`/api/temas/${id}`, { method: "DELETE" }),
  // Feedback por agente (2/11): notas de diapositiva (arte o copy) y el motivo de un descarte (jefe de cultura)
  notas: (eid: number, pid: string) => pedir<Nota[]>(`${pieza(eid, pid)}/notas`),
  anadirNota: (eid: number, pid: string, destino: "director_arte" | "guionista", diapositiva: number, texto: string) =>
    pedir<Nota>(`${pieza(eid, pid)}/notas`, { method: "POST", body: JSON.stringify({ destino, diapositiva, texto }) }),
  borrarNota: (eid: number, pid: string, nid: number) =>
    pedir<{ borrada: number }>(`${pieza(eid, pid)}/notas/${nid}`, { method: "DELETE" }),
  verificarDeNuevo: (eid: number, pid: string) => pedir<PiezaDetalle>(`${pieza(eid, pid)}/verificar`, { method: "POST" }),
  motivosDescarte: () => pedir<string[]>("/api/motivos-descarte"),
  descartar: (eid: number, pid: string, etiquetas: string[], texto: string) =>
    pedir<Nota | null>(`${pieza(eid, pid)}/descartar`, { method: "POST", body: JSON.stringify({ etiquetas, texto }) }),
  materiales: (eid: number, pid: string) => pedir<Material[]>(`/api/ejecuciones/${eid}/piezas/${pid}/materiales`),
  subirMaterial: (eid: number, pid: string, archivo: File, credito: string, nota: string) =>
    pedir<Material>(`/api/ejecuciones/${eid}/piezas/${pid}/materiales?${new URLSearchParams({ nombre: archivo.name, credito, nota })}`,
      { method: "POST", body: archivo, headers: { "Content-Type": archivo.type || "application/octet-stream" } }),
  subirFotoPersona: (eid: number, pid: string, archivo: File, credito: string, modificable: boolean, tratamiento: string) =>
    pedir<{ version: number | null; nota: string }>(`/api/ejecuciones/${eid}/piezas/${pid}/foto-persona?${new URLSearchParams({ nombre: archivo.name, credito, modificable: String(modificable), tratamiento })}`,
      { method: "POST", body: archivo, headers: { "Content-Type": archivo.type || "application/octet-stream" } }),
  borrarMaterial: (eid: number, pid: string, mid: string) =>
    pedir<unknown>(`/api/ejecuciones/${eid}/piezas/${pid}/materiales/${mid}`, { method: "DELETE" }),
  urlMaterial: (eid: number, pid: string, mid: string) => `/api/ejecuciones/${eid}/piezas/${pid}/materiales/${mid}`,
  enviarChat: (eid: number, pid: string, mensaje: string, para?: Para | null) =>
    pedir<RespuestaChat>(`${pieza(eid, pid)}/chat`, { method: "POST", body: JSON.stringify({ mensaje, ...(para ? { para } : {}) }) }),
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
