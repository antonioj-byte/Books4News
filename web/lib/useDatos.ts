"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Carga datos de la API: datos, error y una función para recargar. `clave` identifica la petición
// (cuando cambia, se vuelve a cargar); mientras llega la nueva respuesta se mantienen los datos
// anteriores, para que la pantalla no parpadee al cambiar de día o de pieza.
export function useDatos<T>(clave: string, cargar: () => Promise<T>) {
  const cargarActual = useRef(cargar);
  useEffect(() => { cargarActual.current = cargar; });
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState("");

  const recargar = useCallback(() => {
    cargarActual.current()
      .then((d) => { setDatos(d); setError(""); })
      .catch((e) => setError(String(e)));
  }, [clave]); // eslint-disable-line react-hooks/exhaustive-deps -- la clave es la que decide cuándo recargar

  useEffect(recargar, [recargar]);
  return { datos, error, recargar };
}
