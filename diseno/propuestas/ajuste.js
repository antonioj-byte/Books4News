// Común a las propuestas: reduce el texto de cada caja [data-ajustar] hasta que quepa, sin bajar
// del mínimo de los tokens (--tamanos-cuerpo-minimo). Marca body.dataset.desborda si no cabe.
document.fonts.ready.then(() => {
  const minimo = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--tamanos-cuerpo-minimo")) || 32;
  for (const caja of document.querySelectorAll("[data-ajustar]")) {
    const textos = [...caja.querySelectorAll(".texto, .titular")];
    if (!textos.length) continue;
    let paso = 0;
    while (caja.scrollHeight > caja.clientHeight + 1 && paso < 40) {
      paso++;
      let algo = false;
      for (const t of textos) {
        const tam = parseFloat(getComputedStyle(t).fontSize);
        if (tam - 2 >= minimo) { t.style.fontSize = (tam - 2) + "px"; algo = true; }
      }
      if (!algo) break;
    }
    if (caja.scrollHeight > caja.clientHeight + 1) document.body.dataset.desborda = "1";
  }
  document.body.dataset.listo = "1";
});
