"use client";

import { useRef, useState } from "react";

// Edición directa sobre la diapositiva: el mismo HTML del render, con el titular, el subtítulo y el
// texto editables en el sitio. Las cursivas (<em>) vuelven a ser *así* al guardar.
const ANCHO = 1080;
const ALTO = 1350;
const EDITABLES = ".titular, .subtitulo, p.texto";

function aTexto(el: Element): string {
  const copia = el.cloneNode(true) as Element;
  copia.querySelectorAll("em").forEach((em) => em.replaceWith(`*${em.textContent ?? ""}*`));
  return (copia.textContent ?? "").replace(/\s+/g, " ").trim();
}

export function EditorDiapositiva({ src, ancho, onGuardar, onCancelar }: {
  src: string; ancho: number;
  onGuardar: (texto: string, subtitulo: string | null) => Promise<void>;
  onCancelar: () => void;
}) {
  const marco = useRef<HTMLIFrameElement>(null);
  const [guardando, setGuardando] = useState(false);
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
    const titular = doc.querySelector(".titular");
    const subtitulo = doc.querySelector(".subtitulo");
    const texto = titular ? aTexto(titular) : aTexto(doc.querySelector("p.texto") ?? doc.body);
    setGuardando(true);
    try { await onGuardar(texto, subtitulo ? aTexto(subtitulo) : null); }
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
        <button onClick={guardar} disabled={guardando} className="boton">{guardando ? "Guardando…" : "Guardar texto"}</button>
        <button onClick={onCancelar} disabled={guardando} className="boton-suave">Cancelar</button>
      </div>
    </div>
  );
}
