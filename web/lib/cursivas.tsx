import { Fragment } from "react";

// Texto del guion con *cursivas* (como en las diapositivas): devuelve nodos con <em>.
export function conCursivas(texto: string) {
  return texto.split(/(\*[^*\n]+\*)/g).map((trozo, i) =>
    trozo.startsWith("*") && trozo.endsWith("*") && trozo.length > 2
      ? <em key={i}>{trozo.slice(1, -1)}</em>
      : <Fragment key={i}>{trozo}</Fragment>,
  );
}
