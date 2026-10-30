// Isotipo de Tapablanda: cuadrado carmesí con dos tomos apoyados que forman una «A».
// Versión plana dibujada a partir del brand kit; sustituir por el SVG oficial cuando llegue.
export function Isotipo({ tamano = 30 }: { tamano?: number }) {
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 40 40" role="img" aria-label="Tapablanda" className="shrink-0">
      <rect width="40" height="40" rx="7" fill="var(--carmesi)" />
      <path d="M17.2 9.5 L22.4 9.5 L14.6 31 L9.4 31 Z" fill="var(--papel)" />
      <path d="M21.8 14.2 L25.8 13.4 L30.6 31 L26.4 31 Z" fill="var(--papel)" />
    </svg>
  );
}
