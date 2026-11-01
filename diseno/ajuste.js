// Común a las propuestas: reduce el texto de cada caja [data-ajustar] hasta que quepa, sin bajar
// del mínimo de los tokens (--tamanos-cuerpo-minimo). Marca body.dataset.desborda si no cabe.
document.fonts.ready.then(() => {
  // Interferencia (M10): las capas llevan siempre el tamaño del titular, también mientras se ajusta
  const igualarCapas = () => {
    for (const capa of document.querySelectorAll(".interferencia")) {
      const titular = capa.parentElement.querySelector(".titular");
      if (titular) capa.style.fontSize = getComputedStyle(titular).fontSize;
    }
  };
  igualarCapas();
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
      igualarCapas();
    }
    if (caja.scrollHeight > caja.clientHeight + 1) document.body.dataset.desborda = "1";
  }
  // La pregunta del buscador va en una línea (para teclearla en el vídeo): si no cabe, se encoge la letra en vez
  // de cortarla (2/11: «por qué dejamos de repararnos con lo…»)
  for (const caja of document.querySelectorAll(".buscador")) {
    const texto = caja.querySelector(".buscador__texto");
    if (!texto) continue;
    let tam = parseFloat(getComputedStyle(caja).fontSize);
    while (texto.scrollWidth > texto.clientWidth + 1 && tam > 18) { tam -= 1; caja.style.fontSize = tam + "px"; }
  }
  // El colofón no tiene .texto: se encoge entero con su escala hasta que quepa en la ficha (2/11: con cinco
  // noticias y los créditos de la ilustración, la última línea se salía por abajo)
  for (const caja of document.querySelectorAll(".diapositiva--colofon .cuerpo")) {
    let escala = 1;
    while (caja.scrollHeight > caja.clientHeight + 1 && escala > 0.62) {
      escala = Math.round((escala - 0.04) * 100) / 100;
      caja.style.setProperty("--colofon-escala", escala);
    }
    if (caja.scrollHeight > caja.clientHeight + 1) document.body.dataset.desborda = "1";
  }
  // [data-encajar]: una sola pieza (la cifra destacada) que se reduce hasta caber a lo ancho
  for (const el of document.querySelectorAll("[data-encajar]")) {
    let tam = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollWidth > el.clientWidth + 1 && tam > 48) { tam -= 4; el.style.fontSize = tam + "px"; }
  }
  igualarCapas();
  document.body.dataset.listo = "1";
});

// Vídeo (folio.render.video llama a esto en cada fotograma, con los milisegundos): la cifra destacada
// cuenta hasta su valor en 2,2 s y frena (M2). Los años cuentan desde sesenta antes. El PNG no lo llama:
// enseña la cifra tal cual.
window.folioFotograma = (ms) => {
  for (const el of document.querySelectorAll("[data-contar]")) {
    const final = el.dataset.final ?? (el.dataset.final = el.textContent);
    const m = final.match(/\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?/);
    if (!m) continue;
    const miles = m[0].includes("."), decimales = (m[0].split(",")[1] || "").length;
    const valor = parseFloat(m[0].replace(/\./g, "").replace(",", "."));
    const anio = !miles && !decimales && valor >= 1000 && valor <= 2100;
    const desde = anio ? valor - 60 : 0;
    const p = Math.min(1, ms / 2200), suave = 1 - Math.pow(1 - p, 3);
    if (p >= 1) { el.textContent = final; continue; }
    let n = (desde + (valor - desde) * suave).toFixed(decimales);
    let [entero, dec] = n.split(".");
    if (miles) entero = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    el.textContent = final.replace(m[0], entero + (dec ? "," + dec : ""));
  }
};
