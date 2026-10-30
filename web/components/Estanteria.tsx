// Estantería del brand kit: lomos sobre una balda de madera. En la portada del día, los libros que
// recomiendan las piezas.
const COLORES = ["var(--noche)", "var(--lomo-malva)", "var(--verde)", "var(--carmesi)", "var(--tinta)"];
const ALTOS = [210, 192, 182, 204, 196, 214];

export function Estanteria({ libros, pie }: { libros: { titulo: string; autor: string }[]; pie?: string }) {
  if (!libros.length) return null;
  return (
    <figure className="flex flex-col gap-2">
      <div className="flex items-end gap-1.5 overflow-x-auto px-1">
        {libros.map((l, i) => (
          <div key={`${l.titulo}-${i}`} title={`${l.titulo} · ${l.autor}`}
               className="flex shrink-0 items-center justify-center rounded-t-[3px] px-1 py-3 text-papel"
               style={{ background: COLORES[i % COLORES.length], height: ALTOS[i % ALTOS.length], width: 54 }}>
            <span className="titular max-h-full overflow-hidden text-[15px] text-papel"
                  style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {l.titulo}
            </span>
          </div>
        ))}
      </div>
      <div className="h-3 rounded-sm bg-madera shadow-[0_6px_10px_-6px_rgb(28_22_24/0.5)]" />
      {pie && <figcaption className="dato uppercase">{pie}</figcaption>}
    </figure>
  );
}
