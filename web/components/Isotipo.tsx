// Isotipo de Folio · Mesa de edición: cuadrado carmesí con una «F» hecha de tres tomos (uno en pie y
// dos apoyados encima). Versión plana provisional; sustituir por el SVG oficial cuando llegue.
export function Isotipo({ tamano = 30 }: { tamano?: number }) {
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 40 40" role="img" aria-label="Folio" className="shrink-0">
      <rect width="40" height="40" rx="7" fill="var(--carmesi)" />
      <rect x="11" y="9" width="5.4" height="22" rx="0.8" fill="var(--papel)" />
      <rect x="16.4" y="9" width="13" height="5" rx="0.8" fill="var(--papel)" />
      <rect x="16.4" y="17.6" width="9.6" height="4.6" rx="0.8" fill="var(--papel)" />
    </svg>
  );
}
