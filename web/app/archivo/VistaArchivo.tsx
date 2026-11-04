"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { FormatoChip } from "@/components/Marcas";
import { api, type PiezaArchivo } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { EsqueletoTarjetas } from "@/components/Esqueleto";

// El Archivo (3/11, a petición del usuario: «¿cómo puedo ver el histórico? Puede interesar publicar o editar contenidos
// ya hechos, pero que se quedan en nevera»): todas las piezas de todos los días, en qué punto están y si siguen vigentes.
const CATEGORIAS: { clave: string; texto: string }[] = [
  { clave: "nevera", texto: "En nevera" }, { clave: "aprobada", texto: "Aprobadas" }, { clave: "programada", texto: "Programadas" },
  { clave: "publicada", texto: "Publicadas" }, { clave: "pendiente", texto: "Pendientes" }, { clave: "descartada", texto: "Descartadas" },
  { clave: "todas", texto: "Todas" },
];
const VIGENCIA: Record<string, string> = {
  atemporal: "bg-[#dfeae4] text-verde", vigente: "bg-[#dfeae4] text-verde",
  revisar: "bg-[#fff6c2] text-[#6b5a00]", caducada: "bg-[#fbe1ea] text-carmesi",
};
const fechaCorta = (f: string) => new Date(`${f}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "short" });

export function VistaArchivo() {
  const router = useRouter();
  const busqueda = useSearchParams();
  const ver = busqueda.get("ver") ?? "nevera";
  const { datos, error } = useDatos("archivo", api.archivo);
  const [texto, setTexto] = useState("");
  const [formato, setFormato] = useState("");
  const piezas = useMemo(() => datos ?? [], [datos]);
  const cuenta = useMemo(() => Object.fromEntries(CATEGORIAS.map((c) => [c.clave, c.clave === "todas" ? piezas.length : piezas.filter((p) => p.categoria === c.clave).length])), [piezas]);
  const formatos = [...new Set(piezas.map((p) => p.formato))];
  const q = texto.trim().toLowerCase();
  const lista = piezas.filter((p: PiezaArchivo) => (ver === "todas" || p.categoria === ver) && (!formato || p.formato === formato)
    && (!q || [p.titular, p.libro, p.autor, p.pieza_id].some((x) => x?.toLowerCase().includes(q))));

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="antetitulo">Archivo · todas las piezas{piezas.length ? ` desde el ${fechaCorta(piezas[piezas.length - 1].fecha)}` : ""}</div>
      <h1 className="titular mb-5 mt-2 text-[40px] leading-tight">Lo que <em>ya está hecho</em></h1>

      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="En qué punto están">
        {CATEGORIAS.map((c) => (
          <button key={c.clave} aria-pressed={ver === c.clave} onClick={() => router.replace(`/archivo?ver=${c.clave}`)}
                  className={`rounded-full border px-3.5 py-1.5 text-[13.5px] ${ver === c.clave ? "border-tinta bg-tinta text-papel" : "border-borde bg-panel hover:border-tinta"}`}>
            {c.texto} <span className="opacity-70">· {cuenta[c.clave] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="mb-5 flex flex-wrap gap-2">
        <input id="archivo-buscar" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar por titular, libro o autor…"
               className="min-w-0 flex-1 rounded-[12px] border border-borde bg-panel px-3 py-2 text-[14px] outline-none focus:border-tinta" />
        <select id="archivo-formato" value={formato} onChange={(e) => setFormato(e.target.value)} aria-label="Formato"
                className="rounded-[12px] border border-borde bg-panel px-3 py-2 text-[14px] outline-none focus:border-tinta">
          <option value="">Todos los formatos</option>
          {formatos.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>

      {error && <p className="text-carmesi" role="alert">{error}</p>}
      {!datos && !error && <EsqueletoTarjetas n={8} />}
      {datos && lista.length === 0 && (
        <p className="panel px-5 py-4 text-tinta-suave">{ver === "nevera" ? "No hay nada en la nevera: todas las piezas escritas están aprobadas, publicadas o descartadas." : "No hay piezas con este filtro."}</p>
      )}
      {lista.length > 0 && (
        <div className="panel overflow-x-auto p-0">
          <table className="w-full min-w-[720px] border-collapse text-[14px]">
            <thead>
              <tr className="text-left">
                {["Pieza", "Formato", "Fecha", "Vigencia", ""].map((h) => (
                  <th key={h} className="dato border-b border-borde px-4 py-2.5 font-normal uppercase tracking-[0.12em]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lista.map((p) => (
                <tr key={`${p.ejecucion_id}/${p.pieza_id}`} className="border-b border-borde last:border-b-0 hover:bg-papel-hondo/40">
                  <td className="px-4 py-3">
                    <Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="font-semibold hover:text-carmesi">{p.titular}</Link>
                    <span className="dato mt-0.5 block">
                      {[p.libro && `${p.libro}${p.autor ? ` · ${p.autor}` : ""}`, `v${p.version}`, p.nota != null && `evaluada ${p.nota}`].filter(Boolean).join(" · ")}
                    </span>
                  </td>
                  <td className="px-4 py-3"><FormatoChip formato={p.formato} /></td>
                  <td className="dato whitespace-nowrap px-4 py-3">{fechaCorta(p.fecha)}</td>
                  <td className="px-4 py-3"><span className={`whitespace-nowrap rounded-[6px] px-2 py-0.5 font-mono text-[11.5px] ${VIGENCIA[p.vigencia] ?? ""}`}>{p.vigencia_texto}</span></td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <Link href={`/pieza/${p.ejecucion_id}/${p.pieza_id}`} className="boton-suave">
                      {p.categoria === "pendiente" ? "Escribir" : p.vigencia === "revisar" ? "Revisar" : "Abrir"}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="dato mt-4 max-w-[70ch]">
        En nevera: escritas y sin aprobar, publicar ni descartar. La vigencia cuenta la noticia más reciente de cada pieza: más de una semana, revisar las fechas (el chat puede ponerlas al día); más de un mes, caducada. Las historias editoriales y los recomendados no caducan.
      </p>
    </div>
  );
}
