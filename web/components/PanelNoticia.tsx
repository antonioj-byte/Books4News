import type { PiezaDetalle } from "@/lib/api";

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-borde pt-4">
      <h3 className="antetitulo mb-2.5">{titulo}</h3>
      {children}
    </section>
  );
}

const ES: Record<string, string> = { si: "sí", no: "no", desconocido: "no consta" };

// Columna izquierda: la noticia, el porqué del jefe, la ficha de los libros y todos los avisos.
export function PanelNoticia({ d }: { d: PiezaDetalle }) {
  const p = d.pieza;
  const e = p.eleccion;
  return (
    <div className="flex min-w-0 flex-col gap-5 text-[13.5px] leading-relaxed [overflow-wrap:anywhere]">
      <div>
        <h2 className="titular text-[25px] leading-[1.1]">{e.titular}</h2>
        <p className="mt-3">{e.de_que_se_habla}</p>
        <p className="mt-2 text-tinta-suave"><b className="text-tinta">Cuestión de fondo.</b> {e.cuestion_de_fondo}</p>
      </div>

      {d.hechos_no_verificados.length > 0 && (
        <Seccion titulo={`Hechos sin comprobar · ${d.hechos_no_verificados.length}`}>
          <ul className="flex flex-col gap-3">
            {d.hechos_no_verificados.map((h, i) => (
              <li key={i} className="rounded-[12px] bg-papel-hondo/60 px-3 py-2.5">
                <div className="dato mb-1 uppercase">{h.diapositiva ? `Diapositiva ${h.diapositiva}` : "Pie"} · {h.hecho.tipo}</div>
                {h.frase && <p className="font-titular text-[15px] italic leading-snug">«{h.frase}»</p>}
                <p className="mt-1"><span className="subrayado font-semibold">{h.hecho.afirmacion}</span>{h.hecho.nota ? ` — ${h.hecho.nota}` : ""}</p>
              </li>
            ))}
          </ul>
        </Seccion>
      )}

      {(p.revision_humana.length > 0 || p.discrepancias_edicion.length > 0 || d.aviso_jefe || p.error) && (
        <Seccion titulo="Para mirar antes de publicar">
          <ul className="flex list-disc flex-col gap-1.5 pl-4">
            {p.error && <li className="text-carmesi">{p.error}</li>}
            {d.aviso_jefe && <li>Aviso del jefe de cultura: {d.aviso_jefe}</li>}
            {p.revision_humana.map((r) => <li key={r}>{r}</li>)}
            {p.discrepancias_edicion.map((x, i) => (
              <li key={i}>Revisar edición: <i>{x.libro}</i>, {x.campo}. Guionista: {x.modelo}; fuente: {x.api}.</li>
            ))}
          </ul>
        </Seccion>
      )}

      <Seccion titulo="Por qué esta historia">
        <p>{e.por_que}</p>
        <p className="dato mt-1.5">{p.n_medios} MEDIOS{p.reserva ? " · RESERVA" : ""}</p>
      </Seccion>

      <Seccion titulo="Fuentes">
        <ul className="flex flex-col gap-2">
          {p.fuentes.map((f) => (
            <li key={f.url}>
              <a href={f.url} target="_blank" rel="noreferrer"
                 className="font-semibold underline decoration-borde decoration-2 underline-offset-4 hover:text-carmesi hover:decoration-carmesi">
                {f.medio}
              </a>{" "}
              <span className="dato">· {f.acceso}{f.texto_completo ? "" : " · solo titular"}</span>
              <div className="text-tinta-suave">{f.titulo}</div>
            </li>
          ))}
        </ul>
      </Seccion>

      <Seccion titulo="Libros · ficha verificada">
        <ul className="flex flex-col gap-4">
          {p.libros.map((l) => {
            const dd = l.edicion_es_detalle;
            return (
              <li key={l.titulo}>
                <div className="font-titular text-[16px] font-semibold leading-snug"><i>{l.titulo_propuesto}</i>, {l.autores.join(", ")}</div>
                <div className="text-tinta-suave">
                  1.ª edición: {[l.idioma_original, l.editorial_original, l.anio_primera_edicion].filter(Boolean).join(", ") || "no consta"}
                </div>
                <div>
                  Edición española: <b>{ES[l.edicion_es]}</b>
                  {dd && ` — ${[dd.editorial, dd.anio, dd.traductor && `trad. ${dd.traductor}`, dd.isbn && `ISBN ${dd.isbn}`].filter(Boolean).join(", ")}`}
                </div>
                {l.url_ficha && (
                  <a href={l.url_ficha} target="_blank" rel="noreferrer" className="dato underline underline-offset-2">
                    {l.fuentes_verificacion.join(" + ")} · confianza {l.confianza}
                  </a>
                )}
              </li>
            );
          })}
          {p.libros_descartados.map((l) => (
            <li key={l.titulo} className="text-tinta-suave line-through decoration-1">{l.titulo} — {l.motivo}</li>
          ))}
        </ul>
      </Seccion>

      {p.arte && (
        <Seccion titulo="Arte">
          <p className="text-tinta-suave">
            Portada «{p.arte.portada}»{p.arte.acento ? ` en ${p.arte.acento}` : ""} · tono {p.arte.tono}
          </p>
          {(p.arte.retrato || p.arte.credito) && (
            <p className="mt-2">
              <b>Para el pie:</b> {[p.arte.retrato && `Retrato: ${p.arte.retrato}`, p.arte.credito && `Imagen: ${p.arte.credito}`]
                .filter(Boolean).join(". ")}.
            </p>
          )}
          {p.arte.avisos.length > 0 && (
            <ul className="mt-2 flex list-disc flex-col gap-1 pl-4 text-tinta-suave">
              {p.arte.avisos.map((a) => <li key={a}>{a}</li>)}
            </ul>
          )}
        </Seccion>
      )}

      {p.avisos.length > 0 && (
        <Seccion titulo="Avisos del pipeline">
          <ul className="flex list-disc flex-col gap-1 pl-4 text-tinta-suave">
            {p.avisos.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </Seccion>
      )}
    </div>
  );
}
