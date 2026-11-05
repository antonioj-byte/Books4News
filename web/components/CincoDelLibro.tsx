"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ListaCinco } from "@/lib/api";
import { useTrabajo } from "@/lib/useTrabajo";
import { Boton } from "@/components/Boton";
import { FalloTrabajo, PASOS_CINCO, Trabajando } from "@/components/Trabajando";

const N = 5;

// «Cinco del libro» en la mesa. Desde el 5/11 (a petición del usuario: «me haga una propuesta de noticias; yo elijo las
// más importantes y finalmente monta el post»), la madrugada deja una lista de unas diez noticias con las cinco del jefe
// ya marcadas: si valen, un clic; si no, se marcan otras. El número es el orden del post (la 1 abre) y ↑ la sube.
// «Montar el post» lanza `folio cinco --elegidas …` en un proceso aparte y lo sigue con la tarjeta de trabajo; las
// ilustraciones solo se pagan de lo elegido. Sin lista (un día anterior, o falló), se prepara aquí en unos segundos.
// Con `cinco.modo: automatico`, como antes: un botón que la escribe entera.
export function CincoDelLibro({ fecha, onHecho }: { fecha: string; onHecho: () => void }) {
  const [lista, setLista] = useState<ListaCinco | null>(null);
  const [orden, setOrden] = useState<string[] | null>(null);       // las elegidas, en orden (null: las del jefe)
  const cargar = useCallback(() => {
    api.listaCinco(fecha).then((l) => { setLista(l); setOrden(null); }).catch(() => setLista({ modo: "automatico", propuesta: null }));
  }, [fecha]);
  useEffect(() => { cargar(); }, [cargar]);

  const candidatas = lista?.propuesta?.candidatas ?? [];
  const delJefe = candidatas.filter((c) => c.marcada).map((c) => c.historia);
  const elegidas = orden ?? delJefe;

  const montar = useTrabajo({
    consultar: () => api.estadoCinco(),
    lanzar: () => api.lanzarCinco(fecha, lista?.propuesta ? elegidas : undefined),
    onHecho: () => onHecho(),
    siFalla: "No se pudo montar «Cinco del libro».",
  });
  const preparar = useTrabajo({
    consultar: () => api.estadoListaCinco(),
    lanzar: () => api.prepararListaCinco(fecha),
    onHecho: (e) => { if (e.codigo === 0) cargar(); },
    siFalla: "No se pudo preparar la lista de noticias.",
  });

  const marcar = (id: string) => setOrden(elegidas.includes(id) ? elegidas.filter((x) => x !== id) : [...elegidas, id]);
  const subir = (id: string) => {
    const i = elegidas.indexOf(id);
    if (i > 0) setOrden([...elegidas.slice(0, i - 1), id, elegidas[i - 1], ...elegidas.slice(i + 1)]);
  };
  const n = elegidas.length;
  const motivo = n < N ? `Marca ${N - n} más: el post lleva ${N} noticias` : n > N ? `Sobran ${n - N}: el post lleva ${N} noticias` : null;
  const cambiada = orden !== null && orden.join() !== delJefe.join();

  return (
    <div className="mt-10 flex flex-col items-start gap-3 rounded-[12px] border border-borde bg-panel p-5">
      <div className="antetitulo">Cinco del libro</div>
      {montar.enMarcha ? (
        <Trabajando etapa={montar.estado?.etapa ?? "Trabajando…"} pasos={PASOS_CINCO} rotulo="Montando el post"
                    inicio={montar.estado?.inicio} tipico={montar.estado?.tipico_s} />
      ) : lista?.propuesta && candidatas.length ? (
        <>
          <p className="max-w-[62ch] text-[14px] text-tinta-suave">
            Elige las cinco noticias del mundo del libro de hoy. Van marcadas las que publicaría el jefe de cultura; el número es
            el orden del post (la 1 abre).
          </p>
          <ol className="flex w-full flex-col divide-y divide-borde rounded-[10px] border border-borde bg-papel">
            {candidatas.map((c) => {
              const pos = elegidas.indexOf(c.historia) + 1;
              return (
                <li key={c.historia} className={`flex items-start gap-3 px-3.5 py-3 ${pos ? "" : "opacity-75"}`}>
                  <input type="checkbox" id={`cinco-${c.historia}`} checked={pos > 0} onChange={() => marcar(c.historia)}
                         className="mt-1 h-4 w-4 flex-none accent-carmesi" />
                  <span aria-hidden className={`mt-0.5 grid h-5 w-5 flex-none place-items-center rounded-full text-[11.5px] font-bold ${pos ? "bg-tinta text-papel" : "border border-borde text-transparent"}`}>
                    {pos || "·"}
                  </span>
                  <label htmlFor={`cinco-${c.historia}`} className="min-w-0 flex-1 cursor-pointer">
                    <span className="block text-[15px] font-semibold leading-snug">{c.titular}</span>
                    <span className="block text-[13.5px] text-tinta-suave">{c.por_que}</span>
                    <span className="dato mt-0.5 block">
                      {c.medio}{c.n_medios > 1 ? ` y ${c.n_medios - 1} más` : ""}
                      {c.url && <> · <a href={c.url} target="_blank" rel="noreferrer" className="underline underline-offset-2" onClick={(e) => e.stopPropagation()}>Leer</a></>}
                    </span>
                  </label>
                  {pos > 1 && (
                    <button className="flex-none rounded-full border border-borde px-2 py-0.5 text-[13px] hover:border-tinta"
                            aria-label={`Subir «${c.titular}» al puesto ${pos - 1}`} onClick={() => subir(c.historia)}>↑</button>
                  )}
                </li>
              );
            })}
          </ol>
          <div className="flex flex-wrap items-start gap-3">
            <Boton onClick={montar.lanzar} motivo={motivo} hecho={null}
                   coste={`~${Math.round((montar.estado?.tipico_s ?? 300) / 60)} min · ~0,15 $ y ~125 créditos`}>
              Montar el post ({Math.min(n, N)}/{N}) →
            </Boton>
            {cambiada && <button className="boton-suave" onClick={() => setOrden(null)}>Volver a las del jefe</button>}
          </div>
        </>
      ) : preparar.enMarcha ? (
        <Trabajando etapa={preparar.estado?.etapa ?? "Trabajando…"} rotulo="Preparando la lista"
                    inicio={preparar.estado?.inicio} tipico={preparar.estado?.tipico_s} />
      ) : lista?.modo === "propuesta" ? (
        <>
          <p className="max-w-[62ch] text-[14px] text-tinta-suave">
            Aún no hay lista de noticias para elegir. Se hace sobre las noticias que ya leyó la madrugada, sin rehacer la mesa.
          </p>
          <div className="flex flex-wrap items-start gap-3">
            <Boton onClick={preparar.lanzar} hecho={null} coste="~30 s · ~0,01 $">Preparar la lista →</Boton>
            <Boton onClick={montar.lanzar} tipo="secundario" hecho={null} coste="sin elegir · ~0,20 $">Escribirla directamente</Boton>
          </div>
        </>
      ) : lista ? (
        <>
          <p className="text-[14px] text-tinta-suave">Las cinco noticias del mundo del libro de hoy, cada una con su ilustración. Se hace sobre las noticias que ya leyó la madrugada, sin rehacer la mesa.</p>
          <Boton onClick={montar.lanzar} hecho={null} coste={`~${Math.round((montar.estado?.tipico_s ?? 300) / 60)} min · ~0,20 $`}>Escribir «Cinco del libro» →</Boton>
        </>
      ) : null}
      {montar.error && !montar.enMarcha && <FalloTrabajo fallo={montar.error} reintentar={montar.lanzar} />}
      {preparar.error && !preparar.enMarcha && <FalloTrabajo fallo={preparar.error} reintentar={preparar.lanzar} />}
    </div>
  );
}
