// Común a las propuestas: reduce el texto de cada caja [data-ajustar] hasta que quepa, sin bajar
// del mínimo de los tokens (--tamanos-cuerpo-minimo). Marca body.dataset.desborda si no cabe.
document.fonts.ready.then(() => {
  const minimo = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--tamanos-cuerpo-minimo")) || 32;
  for (const caja of document.querySelectorAll("[data-ajustar]")) {
    const textos = [...caja.querySelectorAll(".texto, .titular")];
    if (!textos.length) continue;
    let paso = 0;
    while (caja.scrollHeight > caja.clientHeight + 4 && paso < 40) {
      paso++;
      let algo = false;
      for (const t of textos) {
        const tam = parseFloat(getComputedStyle(t).fontSize);
        if (tam - 2 >= minimo) { t.style.fontSize = (tam - 2) + "px"; algo = true; }
      }
      if (!algo) break;
    }
    if (caja.scrollHeight > caja.clientHeight + 4) document.body.dataset.desborda = "1";
  }
  // [data-encajar]: una sola pieza (la cifra destacada) que se reduce hasta caber a lo ancho
  for (const el of document.querySelectorAll("[data-encajar]")) {
    let tam = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollWidth > el.clientWidth + 1 && tam > 48) { tam -= 4; el.style.fontSize = tam + "px"; }
  }
  document.body.dataset.listo = "1";
});
