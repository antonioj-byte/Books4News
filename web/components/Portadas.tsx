// Dos portadas de libro como en el brand kit: la apuesta segura (tinta) y la sorpresa (verde, −2,5°).
export function Portadas() {
  const libro = "flex h-[168px] w-[118px] flex-col justify-between rounded-[4px] p-3 text-papel shadow-[var(--sombra-libro)]";
  return (
    <div className="flex items-end gap-5" aria-hidden>
      <div className={`${libro} bg-tinta`}>
        <span className="titular text-[17px] text-papel">Ficciones</span>
        <span className="font-titular text-[11px] italic">Jorge Luis Borges</span>
      </div>
      <div className={`${libro} bg-verde`} style={{ transform: "rotate(-2.5deg)" }}>
        <span className="titular text-[17px] leading-tight text-papel">Pedro Páramo</span>
        <span className="font-titular text-[11px] italic">Juan Rulfo</span>
      </div>
    </div>
  );
}
