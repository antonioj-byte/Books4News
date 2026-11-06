// Errores en una frase (4/11, usabilidad: «un error es una frase y un siguiente paso, nunca un traceback»). Antes había
// cuatro maneras de enseñarlos y algunas pegaban el texto de la API tal cual («Error: 409 /api/…: …»).

export type Fallo = { titulo: string; detalle?: string };

// Lo que la API valida y cómo decirlo
const VALIDACION: [RegExp, string][] = [
  [/string_too_long/, "El texto es demasiado largo."],
  [/string_too_short/, "Escribe un poco más: al menos una frase."],
  [/missing/, "Falta un dato obligatorio."],
];

/** El mensaje de un error de la API o de la red, en una frase y sin el «409 /api/…:» delante. */
export function mensajeError(e: unknown, siNoHayNada = "No se ha podido hacer."): string {
  const crudo = e instanceof Error ? e.message : typeof e === "string" ? e : "";
  if (!crudo) return siNoHayNada;
  if (/Failed to fetch|NetworkError|Load failed|fetch failed/i.test(crudo))
    return "No hay conexión con Folio. Comprueba la red y vuelve a intentarlo.";
  const codigo = Number(crudo.match(/^(\d{3}) /)?.[1] ?? 0);
  let m = crudo.replace(/^Error:\s*/, "").replace(/^\d{3} \S+: /, "").trim();
  for (const [re, frase] of VALIDACION) if (re.test(m)) return frase;
  if (m.startsWith("[") || m.startsWith("{")) m = "";                 // un JSON de la API no es una frase
  if (!m || /^(Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)$/i.test(m)) {
    if (codigo >= 500) return "El servidor de Folio ha fallado. Vuelve a intentarlo en un momento.";
    return siNoHayNada;
  }
  m = m.charAt(0).toUpperCase() + m.slice(1);
  if (!/[.!?…»)]$/.test(m)) m += ".";
  return m.length > 280 ? m.slice(0, 280) + "…" : m;
}

/** Si el error es que ese trabajo ya está en marcha (un 409 de «ya se está…»). */
export function yaEnMarcha(e: unknown): boolean {
  const m = e instanceof Error ? e.message : "";
  return m.startsWith("409") && /ya se est[áa]/i.test(m);
}

// Las últimas líneas del registro de un trabajo que falló, en una frase y con el detalle aparte
const PATRONES: [RegExp, string][] = [
  [/Cancelado por la redacción/i, "Cancelado."],
  [/Interrumpido/i, "Se cortó porque la API se reinició (un despliegue). Vuelve a lanzarlo."],
  [/Magnific[^\n]*(40[13]|429)|bloquead/i, "Magnific ha bloqueado las peticiones por hoy: las ilustraciones quedan para mañana."],
  [/Magnific|La tarea \S+ (falló|no terminó)/i, "Magnific no pudo dibujar. Suele ser pasajero: vuelve a intentarlo."],
  [/fallo pasajero de Anthropic|Error code: 5\d\d|overloaded|529/i, "Anthropic no respondió (un fallo pasajero). Vuelve a intentarlo."],
  [/429|rate.?limit|límite/i, "Un servicio ha pedido que esperemos (límite de uso). Prueba más tarde."],
  [/\b403\b/, "Un servicio ha bloqueado la petición y Folio se ha parado, como pide la casa."],
  [/No hay ejecución del/i, ""],
];

/** Por qué falló un trabajo, de sus últimas líneas de registro. */
export function fraseDeFallo(lineas: string[] | undefined, siNoHayNada = "No ha salido bien."): Fallo {
  const todas = (lineas ?? []).filter(Boolean);
  const detalle = todas.join("\n") || undefined;
  const texto = todas.join("\n");
  for (const [re, frase] of PATRONES) {
    if (re.test(texto)) {
      const linea = todas.findLast((l) => re.test(l)) ?? "";
      return { titulo: frase || mensajeError(linea, siNoHayNada), detalle };
    }
  }
  // La última línea que se lee como una frase (no una línea de traza ni un nombre de excepción de Python)
  const frase = todas.findLast((l) => /^[A-ZÁÉÍÓÚÑ«¿¡]/.test(l) && !/^(Traceback|File |\s|[A-Z]\w*(Error|Exception)\b)/.test(l));
  return { titulo: frase ? mensajeError(frase, siNoHayNada) : siNoHayNada, detalle };
}
