"use client";

import { useEffect, useRef, useState } from "react";
import { mensajeError } from "@/lib/errores";

// El botón de Folio (4/11, usabilidad: «cada botón se explica»). Cuatro tipos con un papel claro y cuatro estados que
// se distinguen sin leer:
// - principal (lo siguiente que toca), secundario, «fuera» (publica fuera de Folio) y peligro (destructivo);
// - normal → trabajando (no admite doble clic) → «Hecho ✓» un momento → normal; y si falla, el motivo debajo;
// - apagado, con su motivo visible debajo (no en un `title`, que en el móvil no se ve).
export type TipoBoton = "principal" | "secundario" | "fuera" | "peligro";

const CLASE: Record<TipoBoton, string> = {
  principal: "boton", secundario: "boton-suave", fuera: "boton boton--fuera", peligro: "boton-suave boton--peligro",
};

export function Boton({ onClick, children, tipo = "principal", motivo, coste, hecho = "Hecho", trabajando = "Trabajando…",
  className = "", titulo }: {
  onClick: () => Promise<unknown> | unknown;
  children: React.ReactNode;
  tipo?: TipoBoton;
  motivo?: string | null;          // si lo hay, el botón está apagado y se dice por qué
  coste?: string;                  // «~2 min · 0,40 $»
  hecho?: string | null;           // lo que dice un momento al acabar (null: nada)
  trabajando?: string;
  className?: string;
  titulo?: string;
}) {
  const [fase, setFase] = useState<"" | "trabajando" | "hecho">("");
  const [error, setError] = useState("");
  const vivo = useRef(true);
  useEffect(() => () => { vivo.current = false; }, []);

  const pulsar = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (motivo || fase === "trabajando") return;
    setError(""); setFase("trabajando");
    try {
      await onClick();
      if (!vivo.current) return;
      if (hecho) { setFase("hecho"); setTimeout(() => vivo.current && setFase(""), 1800); } else setFase("");
    } catch (err) {
      if (!vivo.current) return;
      setFase(""); setError(mensajeError(err));
    }
  };

  return (
    <span className={`inline-flex flex-col items-start gap-1 ${className}`}>
      <button onClick={pulsar} aria-disabled={!!motivo || undefined} aria-busy={fase === "trabajando" || undefined}
              title={titulo} className={`${CLASE[tipo]} ${fase === "hecho" ? "boton--hecho" : ""}`}>
        {fase === "trabajando" ? <><span className="girando" aria-hidden />{trabajando}</>
          : fase === "hecho" ? <>✓ {hecho}</>
          : <>{children}{coste && <span className="boton__coste">{coste}</span>}</>}
      </button>
      {motivo && <span className="motivo">{motivo}</span>}
      {error && <span className="text-[13px] text-carmesi" role="alert">{error}</span>}
    </span>
  );
}
