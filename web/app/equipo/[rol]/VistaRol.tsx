"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { CAPA, coste, modeloCorto } from "@/app/equipo/VistaEquipo";
import { api } from "@/lib/api";
import { useDatos } from "@/lib/useDatos";
import { EsqueletoPagina } from "@/components/Esqueleto";

// La ficha de un rol (3/11): lo que sabe, por capas; cómo le va; y lo que se le ha pedido. Responde, rol a rol, a
// «¿se está aprendiendo lo que digo?».
export function VistaRol() {
  const { rol } = useParams<{ rol: string }>();
  const { datos: r, error } = useDatos(`rol:${rol}`, () => api.rol(rol));
  if (error) return <p className="p-6 text-carmesi">{error}</p>;
  if (!r) return <EsqueletoPagina />;
  const enVigor = r.reglas_lista.filter((x) => x.estado !== "propuesta");
  const porDecidir = r.reglas_lista.filter((x) => x.estado === "propuesta");
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Link href="/equipo" className="dato hover:text-carmesi">← EQUIPO</Link>
      <div className="antetitulo mt-4">{r.departamento}</div>
      <h1 className="titular mt-2 text-[40px] leading-tight">{r.nombre}</h1>
      <p className="mt-2 max-w-[66ch] text-[15px]">{r.que_hace}</p>
      <p className="dato mt-2">{modeloCorto(r.modelo)}{r.esfuerzo ? ` · esfuerzo ${r.esfuerzo}` : ""} · {coste(r)} y {r.llamadas_7d} llamadas esta semana{r.nota != null ? ` · nota ${r.nota.toFixed(1)} en la evaluación` : ""}</p>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[1.2fr_1fr]">
        <section className="panel p-5" aria-labelledby="h-sabe">
          <h2 id="h-sabe" className="antetitulo mb-1">Lo que ha aprendido</h2>
          {r.comparte_reglas_con.length > 0 && <p className="dato mb-2">Comparte estas reglas con: {r.comparte_reglas_con.join(", ")}</p>}
          {enVigor.length === 0 && <p className="text-[14px] text-tinta-suave">Todavía no tiene reglas propias en la Memoria: trabaja con su prompt y las reglas de la marca.</p>}
          <ul className="flex flex-col">
            {enVigor.map((x) => (
              <li key={x.id} className="grid grid-cols-[auto_1fr] items-baseline gap-2.5 border-b border-borde py-2.5 text-[14px] last:border-b-0">
                <span className={`whitespace-nowrap rounded-[6px] px-2 py-0.5 font-mono text-[11px] ${CAPA[x.capa]?.clase ?? ""}`}>{CAPA[x.capa]?.texto ?? x.capa}</span>
                <span>{x.propuesta}<span className="dato mt-0.5 block">{x.origen === "conversacion" ? "de una conversación" : "de la Memoria"} · {x.fecha}</span></span>
              </li>
            ))}
          </ul>
        </section>
        <div className="flex flex-col gap-5">
          {porDecidir.length > 0 && (
            <section className="panel p-5" aria-labelledby="h-decidir">
              <h2 id="h-decidir" className="antetitulo mb-2">Por decidir</h2>
              <ul className="flex flex-col gap-2 text-[14px]">
                {porDecidir.map((x) => <li key={x.id} className="rounded-[10px] bg-[#fffbe0] px-3 py-2">{x.propuesta}</li>)}
              </ul>
              <Link href="/como-vamos?ver=memoria" className="boton-suave mt-3 inline-block">Decidir en Memoria</Link>
            </section>
          )}
          <section className="panel p-5" aria-labelledby="h-pedidos">
            <h2 id="h-pedidos" className="antetitulo mb-2">Lo que le has pedido</h2>
            {r.pedidos_lista.length === 0
              ? <p className="text-[14px] text-tinta-suave">Nada dirigido a este rol en el último mes. En el chat de cada pieza, «Para» elige a quién va el mensaje.</p>
              : <ul className="flex flex-col gap-2 text-[14px]">
                  {r.pedidos_lista.map((m, i) => <li key={i}><span className="dato">{m.fecha} · {m.pieza}</span><br />{m.texto}</li>)}
                </ul>}
          </section>
          <p className="dato">Una regla entra en vigor al aceptarla en Memoria; su capa dice a quién alcanza.</p>
        </div>
      </div>
    </div>
  );
}
