"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { EstadoEjecucion } from "@/lib/api";
import { fraseDeFallo, mensajeError, yaEnMarcha, type Fallo } from "@/lib/errores";
import { mirarTrabajos } from "@/lib/trabajos";

// Seguir un trabajo en segundo plano (4/11, usabilidad: «todo lo lento es un trabajo»). Lo mismo para «Proceder»,
// «Cinco del libro», la newsletter, los temas, la tanda del fondo o la Memoria:
// - al montar se engancha si ya está en marcha (antes «Proceder» volvía a enseñar su botón tras recargar);
// - lanzar: si responde «ya se está…», se engancha en vez de dar error;
// - aguanta cortes de red (seis consultas fallidas antes de rendirse);
// - si falla, el motivo en una frase con el registro aparte.
export function useTrabajo({ consultar, lanzar, onHecho, onProgreso, pausa = 4000, siFalla = "No ha salido bien." }: {
  consultar: () => Promise<EstadoEjecucion | null>;
  lanzar: () => Promise<unknown>;
  onHecho?: (e: EstadoEjecucion) => void;
  onProgreso?: (e: EstadoEjecucion) => void;
  pausa?: number;
  siFalla?: string;
}) {
  const [estado, setEstado] = useState<EstadoEjecucion | null>(null);
  const [siguiendo, setSiguiendo] = useState(false);
  const [error, setError] = useState<Fallo | null>(null);
  const ref = useRef({ consultar, onHecho, onProgreso });
  useEffect(() => { ref.current = { consultar, onHecho, onProgreso }; });
  const vivo = useRef(true);
  useEffect(() => () => { vivo.current = false; }, []);

  const vigilar = useCallback(() => {
    setSiguiendo(true);
    let fallos = 0;
    const paso = async () => {
      if (!vivo.current) return;
      let e: EstadoEjecucion | null;
      try { e = await ref.current.consultar(); fallos = 0; } catch {
        if (++fallos < 6) { setTimeout(paso, 5000); return; }
        setSiguiendo(false);
        setError({ titulo: "Se perdió el seguimiento (sin conexión con Folio). Recarga la página para ver cómo acabó." });
        return;
      }
      if (!vivo.current) return;
      setEstado(e);
      if (e?.en_marcha) { ref.current.onProgreso?.(e); setTimeout(paso, pausa); return; }
      setSiguiendo(false);
      if (e && e.codigo !== 0 && e.codigo != null) setError(fraseDeFallo(e.ultimas_lineas, siFalla));
      if (e) ref.current.onHecho?.(e);
    };
    setTimeout(paso, 1500);
  }, [pausa, siFalla]);

  // Al montar: si ya está en marcha (se recargó la página, o se lanzó desde otra pestaña), se engancha
  useEffect(() => {
    ref.current.consultar().then((e) => {
      if (!vivo.current || !e) return;
      setEstado(e);
      if (e.en_marcha) vigilar();
    }).catch(() => {});
  }, [vigilar]);

  const empezar = useCallback(async () => {
    setError(null);
    try { await lanzar(); } catch (err) {
      if (!yaEnMarcha(err)) { setError({ titulo: mensajeError(err, "No se pudo lanzar.") }); return; }
    }
    mirarTrabajos();                 // la bandeja y los avisos lo ven ya, no en la siguiente vuelta
    setEstado((e) => ({ ...(e ?? { ultimas_lineas: [] }), en_marcha: true, inicio: new Date().toISOString(), etapa: "Empezando…", codigo: null } as EstadoEjecucion));
    vigilar();
  }, [lanzar, vigilar]);

  const enMarcha = siguiendo || !!estado?.en_marcha;
  return { estado, enMarcha, error, lanzar: empezar, limpiarError: () => setError(null) };
}
