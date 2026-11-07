"use client";

import { useRef, useState } from "react";
import { mensajeError } from "@/lib/errores";

// Edición directa sobre la diapositiva: el mismo HTML del render, con el titular, el subtítulo y el
// texto editables en el sitio. Las cursivas (<em>) vuelven a ser *así* al guardar.
const ANCHO = 1080;
const ALTO = 1350;
// La firma de la newsletter y la opinión (nombre y cargo) también se edita en el sitio (7/11)
const EDITABLES = ".titular, .subtitulo, p.texto, .nl-firma__nombre, .nl-firma__cargo";

export type Firma = { nombre: string; cargo: string };

function aTexto(el: Element): string {
  const copia = el.cloneNode(true) as Element;
  copia.querySelectorAll("em").forEach((em) => em.replaceWith(`*${em.textContent ?? ""}*`));
  return (copia.textContent ?? "").replace(/\s+/g, " ").trim();
}

export function EditorDiapositiva({ src, ancho, onGuardar, onCancelar }: {
  src: string; ancho: number;
  onGuardar: (texto: string, subtitulo: string | null, firma: Firma | null) => Promise<void>;
  onCancelar: () => void;
}) {
  const marco = useRef<HTMLIFrameElement>(null);
  const [guardando, setGuardando] = useState(false);
  // Si no se guarda, se dice (4/11, usabilidad: antes fallaba en silencio y el editor seguía abierto como si nada)
  const [error, setError] = useState("");
  const escala = ancho / ANCHO;

  const preparar = () => {
    const doc = marco.current?.contentDocument;
    if (!doc) return;
    doc.querySelectorAll(EDITABLES).forEach((el) => {
      (el as HTMLElement).contentEditable = "plaintext-only";
      (el as HTMLElement).spellcheck = true;
    });
    const estilo = doc.createElement("style");
    estilo.textContent = "[contenteditable] { outline: 3px dashed var(--colores-pluma); outline-offset: 10px; cursor: text; }";
    doc.head.appendChild(estilo);
    (doc.querySelector(EDITABLES) as HTMLElement | null)?.focus();
  };

  const guardar = async () => {
    const doc = marco.current?.contentDocument;
    if (!doc) return;
    // La diapositiva de actualidad con «golpe» parte su texto en dos: el principio y la frase final
    // a tamaño de titular (.golpe, que no es el titular de portada)
    const golpe = doc.querySelector(".golpe");
    const titular = doc.querySelector(".titular:not(.golpe)");
    const subtitulo = doc.querySelector(".subtitulo");
    const parrafo = doc.querySelector("p.texto");
    const texto = golpe ? [parrafo ? aTexto(parrafo) : "", aTexto(golpe)].filter(Boolean).join(" ")
      : titular ? aTexto(titular) : aTexto(parrafo ?? doc.body);
    const nombre = doc.querySelector(".nl-firma__nombre");
    const cargo = doc.querySelector(".nl-firma__cargo");
    const firma = nombre ? { nombre: aTexto(nombre), cargo: cargo ? aTexto(cargo) : "" } : null;
    setGuardando(true); setError("");
    try { await onGuardar(texto, subtitulo ? aTexto(subtitulo) : null, firma); }
    catch (e) { setError(`${mensajeError(e, "No se ha guardado.")} Tu texto sigue en la diapositiva: pulsa «Guardar texto» otra vez.`); }
    finally { setGuardando(false); }
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative overflow-hidden rounded-[6px] bg-papel shadow-[var(--sombra-libro)] outline-2 outline-carmesi"
           style={{ width: ancho, height: ALTO * escala }}>
        <iframe ref={marco} src={src} title="Editar diapositiva" width={ANCHO} height={ALTO} onLoad={preparar}
                className="absolute left-0 top-0 origin-top-left border-0" style={{ transform: `scale(${escala})` }} />
      </div>
      <div className="flex gap-2">
        <button onClick={guardar} disabled={guardando} aria-busy={guardando || undefined} className="boton">
          {guardando ? <><span className="girando" aria-hidden />Guardando…</> : "Guardar texto"}
        </button>
        <button onClick={onCancelar} disabled={guardando} className="boton-suave">Cancelar</button>
      </div>
      {error && <p className="max-w-[440px] text-[13px] text-carmesi" role="alert">{error}</p>}
    </div>
  );
}
