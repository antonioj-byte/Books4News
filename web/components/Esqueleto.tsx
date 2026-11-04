// Esqueletos de carga (4/11, usabilidad, fase 3): la forma de la página mientras llegan los datos, en vez de un
// «Cargando…» suelto. Respeta «menos movimiento» (la animación se apaga en marca.css).
export function EsqueletoPagina({ tarjetas = 3, rejilla = false }: { tarjetas?: number; rejilla?: boolean }) {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6" aria-busy="true" aria-label="Cargando">
      <div className="esqueleto mb-3 h-4 w-40" />
      <div className="esqueleto mb-8 h-10 w-2/3" />
      <div className={rejilla ? "grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3" : "flex flex-col gap-4"}>
        {Array.from({ length: tarjetas }, (_, i) => <div key={i} className={`esqueleto w-full ${rejilla ? "aspect-[4/5]" : "h-28"}`} />)}
      </div>
    </div>
  );
}

export function EsqueletoTarjetas({ n = 3, rejilla = false }: { n?: number; rejilla?: boolean }) {
  return (
    <div className={rejilla ? "grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3" : "flex flex-col gap-3"} aria-busy="true" aria-label="Cargando">
      {Array.from({ length: n }, (_, i) => <div key={i} className={`esqueleto w-full ${rejilla ? "aspect-[4/5]" : "h-16"}`} />)}
    </div>
  );
}
