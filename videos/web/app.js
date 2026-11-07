// Asistente de la beta de vídeos conceptuales. Sin dependencias: estado en memoria, ruta en el hash (#<proyecto>/<paso>).
"use strict";

const PASOS = [
  { id: "libro", n: 1, nombre: "Libro" },
  { id: "conceptos", n: 2, nombre: "Concepto" },
  { id: "guion", n: 3, nombre: "Guion" },
  { id: "estilo", n: 4, nombre: "Estilo" },
  { id: "media", n: 5, nombre: "Voz e imágenes" },
  { id: "montaje", n: 6, nombre: "Montaje y revisión" },
];
const NOTAS = [["sorpresa", "Sorpresa"], ["utilidad", "Utilidad"], ["polemica", "Polémica"], ["visualidad", "Visualidad"]];
const ROLES = { gancho: "Gancho", tension: "Tensión", desarrollo: "Desarrollo", giro: "Giro", cierre: "Cierre" };

const estado = { proyecto: null, paso: "libro", siguiendo: null, ediciones: {} };
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const palabras = (t) => (String(t || "").match(/[\p{L}\p{N}]+(?:[’'-][\p{L}\p{N}]+)*/gu) || []).length;

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, opciones);
  const texto = await r.text();
  let datos = null;
  try { datos = texto ? JSON.parse(texto) : null; } catch { /* texto plano */ }
  if (!r.ok) {
    const d = datos?.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `Error ${r.status}`);
  }
  return datos;
}
const json = (metodo, cuerpo) => ({ method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo ?? {}) });

function avisar(texto, mal = false) {
  const a = $("#aviso");
  a.textContent = texto;
  a.className = mal ? "aviso mal" : "aviso";
  a.hidden = false;
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => { a.hidden = true; }, mal ? 9000 : 4500);
}

// ── Ruta ──────────────────────────────────────────────────────────────────────────────────────────────────────────
function leerHash() {
  const [pid, paso] = location.hash.replace(/^#/, "").split("/");
  return { pid: pid || null, paso: paso || null };
}
function ir(pid, paso) { location.hash = pid ? `${pid}/${paso || "libro"}` : ""; }

async function cargar() {
  const { pid, paso } = leerHash();
  if (!pid) { estado.proyecto = null; estado.paso = "libro"; return pintar(); }
  try {
    estado.proyecto = await api(`/api/proyectos/${pid}`);
  } catch (e) { avisar(e.message, true); return ir(null); }
  estado.paso = paso || pasoNatural();
  pintar();
  engancharTrabajos();
}
window.addEventListener("hashchange", cargar);

function pasoNatural() {
  const p = estado.proyecto, e = p.etapas;
  if (p.montajes?.length) return "montaje";
  if (p.estilo) return "media";
  if (e.guion.estado === "bloqueado") return "estilo";
  if (estado.proyecto.concepto_elegido) return "guion";
  if (estado.proyecto.conceptos.length || e.conceptos.estado === "en_curso") return "conceptos";
  return "libro";
}

// ── Pintado ───────────────────────────────────────────────────────────────────────────────────────────────────────
function pintar() {
  pintarPasos();
  const p = estado.proyecto;
  const conChat = p && (estado.paso === "conceptos" || estado.paso === "guion");
  $("#chat").hidden = !conChat;
  $(".cuerpo").classList.toggle("sin-chat", !conChat);
  const c = $("#contenido");
  if (!p) return pintarInicio(c);
  if (estado.paso === "libro") pintarLibro(c);
  else if (estado.paso === "conceptos") pintarConceptos(c);
  else if (estado.paso === "guion") pintarGuion(c);
  else if (estado.paso === "estilo") pintarEstilo(c);
  else if (estado.paso === "media") pintarMedia(c);
  else if (estado.paso === "montaje") pintarMontaje(c);
  if (conChat) pintarChat();
}

function pintarPasos() {
  const p = estado.proyecto;
  const bloqueado = p?.etapas.guion.estado === "bloqueado";
  const listas = p && Object.keys(p.imagenes || {}).length && Object.values(p.imagenes).every((x) => x.elegida !== null);
  const hecho = {
    libro: !!p, conceptos: !!p?.concepto_elegido, guion: bloqueado, estilo: !!p?.estilo,
    media: !!(p?.voz && listas), montaje: !!p?.montajes?.length,
  };
  const abierto = { libro: true, conceptos: !!p, guion: !!p?.concepto_elegido, estilo: bloqueado,
    media: bloqueado && !!p?.estilo, montaje: !!(p?.voz && listas) || !!p?.montajes?.length };
  $("#pasos").innerHTML = PASOS.map((x) => `<button class="paso ${x.id === estado.paso ? "activo" : ""} ${hecho[x.id] ? "hecho" : ""}"
      data-paso="${x.id}" ${abierto[x.id] ? "" : "disabled"} ${x.id === estado.paso ? 'aria-current="step"' : ""}>
      <b>${hecho[x.id] ? "✓" : x.n}</b>${esc(x.nombre)}</button>`).join("");
  document.querySelectorAll(".paso").forEach((b) => b.addEventListener("click", () => p && ir(p.id, b.dataset.paso)));
}

function tarjetaTrabajo(etapa) {
  const t = estado.siguiendo?.[etapa];
  if (!t) return "";
  const seg = Math.round((Date.now() - new Date(t.inicio).getTime()) / 1000);
  const reloj = seg >= 60 ? `${Math.floor(seg / 60)} min ${seg % 60} s` : `${seg} s`;
  return `<div class="trabajo" role="status"><span class="girando" aria-hidden="true"></span>
    <div><b>${esc(t.paso)}…</b><div class="motivo">${reloj} · puedes salir de la página: el trabajo sigue</div></div></div>`;
}

function errorEtapa(etapa) {
  const e = estado.proyecto.etapas[etapa];
  return e.error && !estado.siguiendo?.[etapa] ? `<p class="error" role="alert">No ha salido bien: ${esc(e.error)}</p>` : "";
}

async function pintarInicio(c) {
  c.innerHTML = `
    <h1>Un libro entra, <em>un vídeo sale</em></h1>
    <p class="entradilla">Sube el libro y la herramienta busca en él cinco conceptos conversacionales: ideas que dan ganas de mandar a alguien con un «mira esto». Eliges uno, apruebas el guion y después vienen el estilo, la voz, las imágenes y el montaje.</p>
    <form id="subida" class="subida">
      <div class="zona-subida">
        <label class="campo" for="archivo">EPUB, PDF o TXT</label>
        <input id="archivo" name="archivo" type="file" accept=".epub,.pdf,.txt" required>
      </div>
      <div class="fila">
        <label class="campo" style="flex:1">Título (si el archivo no lo trae)<input id="titulo" name="titulo" type="text"></label>
        <label class="campo" style="flex:1">Autor<input id="autor" name="autor" type="text"></label>
      </div>
      <div><button class="boton" type="submit">Subir y trocear el libro</button></div>
    </form>
    <div id="proyectos" class="lista-proyectos"></div>`;
  $("#subida").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const b = ev.submitter; b.disabled = true; b.textContent = "Leyendo el libro…";
    try {
      const p = await api("/api/proyectos", { method: "POST", body: new FormData(ev.target) });
      ir(p.id, "libro");
    } catch (e) { avisar(e.message, true); b.disabled = false; b.textContent = "Subir y trocear el libro"; }
  });
  try {
    const ps = await api("/api/proyectos");
    if (ps.length) $("#proyectos").innerHTML = `<p class="rotulo">Proyectos</p>` + ps.map((x) =>
      `<a href="#${esc(x.id)}"><span><b>${esc(x.titulo)}</b> · ${esc(x.autor || "")}</span><span class="motivo">${esc(x.creado.slice(0, 10))}</span></a>`).join("");
  } catch { /* sin lista */ }
}

function pintarLibro(c) {
  const p = estado.proyecto, l = p.libro;
  const tokens = Math.round(l.caracteres / 3.6);
  const enMarcha = !!estado.siguiendo?.conceptos;
  c.innerHTML = `
    <p class="rotulo">Paso 1 · Libro</p>
    <h1>${esc(l.titulo)} <em>${esc(l.autor)}</em></h1>
    <p class="entradilla">${l.capitulos.length} capítulos · ${l.caracteres.toLocaleString("es-ES")} caracteres (unos ${tokens.toLocaleString("es-ES")} tokens) · ${esc(l.formato.toUpperCase())}</p>
    ${tarjetaTrabajo("conceptos")}
    <div class="fila" style="margin-bottom:20px">
      <button id="buscar" class="boton" ${enMarcha ? "disabled" : ""}>${p.conceptos.length ? "Ver los conceptos →" : "Buscar conceptos"}<span class="coste">${p.conceptos.length ? "" : "~1–3 min · ~0,60–1,20 $"}</span></button>
    </div>
    <details><summary>Capítulos detectados</summary>
      <table><thead><tr><th>#</th><th>Capítulo</th><th>Páginas</th><th class="num">Caracteres</th></tr></thead><tbody>
      ${l.capitulos.map((x) => `<tr><td class="num">${x.n}</td><td>${esc(x.titulo)}</td><td>${esc(x.paginas || "—")}</td><td class="num">${x.caracteres.toLocaleString("es-ES")}</td></tr>`).join("")}
      </tbody></table></details>`;
  $("#buscar").addEventListener("click", async () => {
    if (p.conceptos.length) return ir(p.id, "conceptos");
    await lanzar(`/api/proyectos/${p.id}/conceptos`, json("POST", {}), "conceptos");
    ir(p.id, "conceptos");
  });
}

function barra(nombre, valor, critico) {
  return `<div class="nota-barra">${nombre} <b>${valor}</b>${critico != null ? ` · crítico ${critico}` : ""}
    <div class="barra"><i style="width:${valor * 10}%"></i>${critico != null ? `<s style="left:calc(${critico * 10}% - 1px)"></s>` : ""}</div></div>`;
}

function pintarConceptos(c) {
  const p = estado.proyecto;
  const rondas = [...new Set(p.conceptos.map((x) => x.ronda))].sort((a, b) => b - a);
  const enMarcha = !!estado.siguiendo?.conceptos;
  c.innerHTML = `
    <p class="rotulo">Paso 2 · Concepto · aprobación 1</p>
    <h1>Elige <em>la idea</em></h1>
    <p class="entradilla">Cada concepto trae el pasaje del libro que lo sostiene, comprobado letra por letra. La barra es la nota de la editora de ideas; la raya roja, la del crítico. El gancho ya lo ha revisado un juez aparte.</p>
    ${tarjetaTrabajo("conceptos")}${errorEtapa("conceptos")}
    <div class="fila" style="margin-bottom:18px">
      <input id="indicaciones" type="text" placeholder="Opcional: qué tienen que tener los nuevos (más polémicos, para padres, del capítulo 3…)" style="flex:1;min-width:240px" ${enMarcha ? "disabled" : ""}>
      <button id="otros" class="boton-suave" ${enMarcha ? "disabled" : ""}>${p.conceptos.length ? "Pedir otros cinco" : "Buscar conceptos"}<span class="coste">${p.conceptos.length ? "~1–2 min · ~0,40 $" : "~1–3 min · ~0,60–1,20 $"}</span></button>
    </div>
    ${rondas.map((r) => `<p class="rotulo" style="margin-top:20px">Ronda ${r}</p><div class="rejilla">${p.conceptos.filter((x) => x.ronda === r).map(tarjetaConcepto).join("")}</div>`).join("")}`;
  $("#otros").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/conceptos`, json("POST", { indicaciones: $("#indicaciones").value }), "conceptos"));
  c.querySelectorAll("[data-elegir]").forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/api/proyectos/${p.id}/conceptos/elegir`, json("POST", { concepto: b.dataset.elegir }));
      estado.proyecto = await api(`/api/proyectos/${p.id}`);
      ir(p.id, "guion");
    } catch (e) { avisar(e.message, true); }
  }));
}

function tarjetaConcepto(x) {
  const p = estado.proyecto;
  const elegido = p.concepto_elegido === x.id;
  const j = x.juicio_gancho;
  const ref = `cap. ${x.pasaje.capitulo}${x.pasaje.titulo_capitulo ? ` («${x.pasaje.titulo_capitulo}»)` : ""}${x.pasaje.pagina ? `, pág. ${x.pasaje.pagina}` : ""}`;
  const bloqueado = p.etapas.guion.estado === "bloqueado" && !elegido;
  return `<article class="tarjeta concepto ${elegido ? "elegido" : ""}">
    <div class="titulo-concepto">${esc(x.titulo)}</div>
    <div class="gancho">«${esc(x.gancho)}»</div>
    ${j ? `<div class="gancho-nota">Juez del gancho: ${j.nota}/10 · ${esc(j.motivo)}${j.original !== x.gancho ? ` · reescrito (antes: «${esc(j.original)}»)` : ""}</div>` : ""}
    <p style="margin:0"><b>La idea.</b> ${esc(x.idea)}</p>
    <p style="margin:0"><b>Por qué genera conversación.</b> ${esc(x.por_que)}</p>
    <blockquote class="pasaje" style="margin:0">«${esc(x.pasaje.texto)}»<span class="ref">${esc(ref)} · literal ✓</span></blockquote>
    <div class="notas">${NOTAS.map(([k, n]) => barra(n, x.notas[k], x.notas_critico?.[k])).join("")}</div>
    ${x.motivo_critico ? `<div class="motivo">Crítico: ${esc(x.motivo_critico)}</div>` : ""}
    <div class="fila"><button class="${elegido ? "boton-suave" : "boton"}" data-elegir="${esc(x.id)}" ${elegido || bloqueado ? "disabled" : ""}>${elegido ? "Elegido ✓" : "Elegir este concepto"}</button></div>
  </article>`;
}

function pintarGuion(c) {
  const p = estado.proyecto;
  const v = p.guion_actual;
  const concepto = p.conceptos.find((x) => x.id === p.concepto_elegido);
  const bloqueado = p.etapas.guion.estado === "bloqueado";
  const enMarcha = !!estado.siguiendo?.guion;
  estado.ediciones = {};
  if (!v) {
    c.innerHTML = `<p class="rotulo">Paso 3 · Guion</p><h1>${esc(concepto?.titulo || "")}</h1>
      <p class="entradilla">Gancho: «${esc(concepto?.gancho || "")}»</p>
      ${tarjetaTrabajo("guion")}${errorEtapa("guion")}
      <button id="escribir" class="boton" ${enMarcha ? "disabled" : ""}>Escribir el guion<span class="coste">~1 min · ~0,20 $</span></button>`;
    $("#escribir").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/guion`, json("POST"), "guion"));
    return;
  }
  const total = v.planos.reduce((s, x) => s + palabras(x.locucion), 0);
  c.innerHTML = `
    <p class="rotulo">Paso 3 · Guion · aprobación 2 · versión ${v.n} (${esc(v.origen)})</p>
    <h1>${esc(v.titulo)}</h1>
    <p class="entradilla">${v.planos.length} planos · ${total} palabras · unos ${Math.round(total / 2.5)} s de voz. Los tiempos definitivos los dará la locución.</p>
    ${tarjetaTrabajo("guion")}${errorEtapa("guion")}
    ${bloqueado ? `<div class="bloqueado">Guion aprobado y bloqueado. <a href="#${esc(p.id)}/estilo">Siguiente: la biblia de estilo →</a></div>` : ""}
    ${v.avisos.length ? `<div class="avisos"><b>Antes de aprobarlo:</b><ul>${v.avisos.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}
    <div class="fila" style="margin-bottom:8px">
      ${bloqueado ? `<button id="desbloquear" class="boton-suave">Desbloquear para editar</button>`
        : `<button id="aprobar" class="boton" ${v.avisos.length || enMarcha ? "disabled" : ""}>Aprobar y bloquear el guion</button>
           <button id="guardar" class="boton-suave" disabled>Guardar los cambios</button>
           <button id="rehacer" class="boton-suave" ${enMarcha ? "disabled" : ""}>Rehacer desde cero<span class="coste">~0,20 $</span></button>`}
    </div>
    ${!bloqueado && v.avisos.length ? `<div class="motivo">Arregla los avisos por chat o editando los planos para poder aprobarlo.</div>` : ""}
    <div id="planos">${v.planos.map((x) => filaPlano(x, bloqueado)).join("")}</div>`;
  if (bloqueado) {
    $("#desbloquear").addEventListener("click", async () => {
      try { await api(`/api/proyectos/${p.id}/guion/desbloquear`, json("POST")); await recargar(); } catch (e) { avisar(e.message, true); }
    });
    return;
  }
  $("#aprobar").addEventListener("click", async () => {
    try { await api(`/api/proyectos/${p.id}/guion/aprobar`, json("POST")); avisar("Guion aprobado y bloqueado."); await recargar(); }
    catch (e) { avisar(e.message, true); }
  });
  $("#rehacer").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/guion`, json("POST"), "guion"));
  $("#guardar").addEventListener("click", () => guardarEdicion({ cambios: estado.ediciones }));
  c.querySelectorAll("[data-campo]").forEach((el) => el.addEventListener("input", () => {
    const { plano, campo } = el.dataset;
    (estado.ediciones[plano] ||= {})[campo] = el.value;
    $("#guardar").disabled = false;
    if (campo === "locucion") el.closest(".plano").querySelector(".cuenta").textContent = `${palabras(el.value)} palabras`;
  }));
  c.querySelectorAll("[data-quitar]").forEach((b) => b.addEventListener("click", () => guardarEdicion({ cambios: estado.ediciones, quitar: [b.dataset.quitar] })));
  c.querySelectorAll("[data-anadir]").forEach((b) => b.addEventListener("click", () => guardarEdicion({ cambios: estado.ediciones, anadir_tras: b.dataset.anadir })));
}

function filaPlano(x, bloqueado) {
  const ro = bloqueado ? "readonly" : "";
  const campo = (nombre, valor, filas, cls = "") => `<textarea class="${cls}" rows="${filas}" data-plano="${x.id}" data-campo="${nombre}" ${ro} aria-label="${nombre} de ${x.id}">${esc(valor)}</textarea>`;
  return `<div class="plano">
    <div><span class="chip rol-${x.rol}">${ROLES[x.rol]}</span><div class="meta" style="margin-top:6px">${x.id}<br>~${x.duracion_estimada} s</div></div>
    <div class="rejilla" style="gap:6px">
      <label class="campo">Locución <span class="cuenta">${palabras(x.locucion)} palabras</span>${campo("locucion", x.locucion, 2, "voz")}</label>
      <label class="campo">Texto en pantalla${campo("pantalla", x.pantalla, 1)}</label>
      <label class="campo">Cita literal del libro${campo("cita", x.cita?.texto || "", 1)}${x.cita ? `<span class="meta">cap. ${x.cita.capitulo}${x.cita.pagina ? `, pág. ${x.cita.pagina}` : ""}</span>` : ""}</label>
    </div>
    <div class="rejilla" style="gap:6px">
      <label class="campo">Lo que se ve${campo("visual", x.visual, 3)}</label>
      <label class="campo">Movimiento${campo("movimiento", x.movimiento, 1)}</label>
      ${bloqueado ? "" : `<div class="fila"><button class="boton-suave" style="padding:4px 12px;font-size:12.5px" data-anadir="${x.id}">+ Plano después</button>
        <button class="boton-suave" style="padding:4px 12px;font-size:12.5px" data-quitar="${x.id}">Quitar</button></div>`}
    </div>
  </div>`;
}

// ── Paso 4: estilo ────────────────────────────────────────────────────────────────────────────────────────────────
const archivo = (ruta) => `/api/proyectos/${estado.proyecto.id}/archivo/${ruta}?v=${encodeURIComponent(estado.proyecto.etapas.imagenes.actualizado || "")}`;
let ESTILOS = null;

async function pintarEstilo(c) {
  const p = estado.proyecto;
  ESTILOS ||= await api("/api/estilos");
  const enMarcha = !!estado.siguiendo?.estilo;
  const e = p.estilo;
  c.innerHTML = `
    <p class="rotulo">Paso 4 · Biblia de estilo</p>
    <h1>Que todos los planos sean <em>la misma obra</em></h1>
    <p class="entradilla">La biblia fija técnica, paleta, luz, encuadres y lo prohibido, y va en todos los prompts de imagen. Las muestras son el primer plano de tu guion dibujado en cada estilo.</p>
    ${tarjetaTrabajo("estilo")}${errorEtapa("estilo")}
    ${e ? `<div class="tarjeta" style="margin-bottom:18px"><p class="rotulo">Estilo elegido</p><h2>${esc(e.nombre)}</h2>
      <p style="margin:0 0 6px">${esc(e.tecnica)}. ${esc(e.luz)}. ${esc(e.encuadres)}.</p>
      <div class="fila">${e.paleta.map((h) => `<span title="${esc(h)}" style="width:28px;height:28px;border-radius:50%;background:${esc(h)};border:1px solid var(--borde)"></span>`).join("")}</div>
      <p class="motivo">Prohibido: ${esc(e.prohibido.join(" · "))}</p>
      <a class="boton" href="#${esc(p.id)}/media" style="display:inline-block;text-decoration:none;margin-top:6px">Siguiente: voz e imágenes →</a></div>` : ""}
    <div class="fila" style="margin-bottom:14px">
      <button id="muestras" class="boton-suave" ${enMarcha ? "disabled" : ""}>${p.muestras.length ? "Rehacer las muestras" : "Ver muestras de los tres estilos"}<span class="coste">3 imágenes · ~75 créditos</span></button>
    </div>
    <div class="rejilla" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
      ${Object.entries(ESTILOS).map(([k, x]) => `<article class="tarjeta concepto ${e?.id === k ? "elegido" : ""}">
        ${p.muestras.includes(k) ? `<img src="/api/proyectos/${esc(p.id)}/archivo/muestras/${k}.jpg?t=${Date.now()}" alt="Muestra del estilo ${esc(x.nombre)}" style="width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:10px">`
          : `<div style="aspect-ratio:9/16;border-radius:10px;background:${esc(x.paleta[0])};display:grid;place-items:center;color:${esc(x.paleta[1])};font-size:13px">sin muestra</div>`}
        <h2 style="margin:4px 0 0">${esc(x.nombre)}</h2><p class="motivo" style="margin:0">${esc(x.descripcion)}</p>
        <button class="${e?.id === k ? "boton-suave" : "boton"}" data-preset="${k}" ${e?.id === k ? "disabled" : ""}>${e?.id === k ? "Elegido ✓" : "Usar este estilo"}</button>
      </article>`).join("")}
    </div>
    <div class="tarjeta" style="margin-top:16px"><h2>O define el tuyo</h2>
      <textarea id="peticion" rows="2" placeholder="P. ej.: linograbado en tinta azul sobre papel kraft, con mucho aire" ${enMarcha ? "disabled" : ""}></textarea>
      <div class="fila" style="margin-top:8px"><button id="propio" class="boton-suave" ${enMarcha ? "disabled" : ""}>Crear mi estilo<span class="coste">~0,03 $</span></button></div></div>`;
  $("#muestras").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/estilo/muestras`, json("POST"), "estilo"));
  $("#propio").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/estilo`, json("POST", { peticion: $("#peticion").value }), "estilo"));
  c.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/proyectos/${p.id}/estilo`, json("POST", { preset: b.dataset.preset })); await recargar(); avisar("Estilo elegido."); }
    catch (x) { avisar(x.message, true); }
  }));
}

// ── Paso 5: voz e imágenes ────────────────────────────────────────────────────────────────────────────────────────
function seg(t) { return `${t.toFixed(1)} s`; }

function pintarMedia(c) {
  const p = estado.proyecto, v = p.guion_actual, voz = p.voz;
  const ocupadoVoz = !!estado.siguiendo?.voz, ocupadoImg = !!estado.siguiendo?.imagenes;
  const imgs = p.imagenes || {};
  const hayImgs = Object.values(imgs).some((x) => x.variantes.length);
  const clipsPend = Object.entries(imgs).filter(([, x]) => x.animacion && x.elegida !== null && !x.clip);
  const listas = Object.keys(imgs).length && Object.values(imgs).every((x) => x.elegida !== null);
  c.innerHTML = `
    <p class="rotulo">Paso 5 · Voz e imágenes</p>
    <h1>La voz manda <em>el ritmo</em></h1>
    <p class="entradilla">Los tiempos de la locución deciden cuándo empieza y acaba cada plano. Cada plano trae dos imágenes para elegir; los planos clave pueden animarse.</p>
    <div class="tarjeta" style="margin-bottom:16px">
      <h2>Locución</h2>${tarjetaTrabajo("voz")}${errorEtapa("voz")}
      ${voz ? `<audio controls src="${archivo(voz.audio_mp3)}" style="width:100%"></audio>
        <p class="motivo">${esc(voz.voz_nombre)}${voz.simulada ? " (simulada: pon ELEVENLABS_API_KEY para la de verdad)" : ""} · ${seg(voz.duracion)} · versión ${voz.version}</p>` : ""}
      <div class="fila"><button id="voz" class="${voz ? "boton-suave" : "boton"}" ${ocupadoVoz ? "disabled" : ""}>${voz ? "Rehacer la locución entera" : "Generar la locución"}<span class="coste">~10–20 s · ~0,06 $</span></button>
        ${voz ? `<button id="musica" class="boton-suave" ${ocupadoVoz ? "disabled" : ""}>${p.musica ? "Otra cama musical" : "Añadir cama musical"}<span class="coste">ElevenLabs Music</span></button>` : ""}
        ${p.musica ? `<label class="fila" style="gap:6px;font-size:14px"><input id="musica-activa" type="checkbox" ${p.musica_activa ? "checked" : ""}> Con música</label>` : ""}</div>
      ${p.musica ? `<audio controls src="${archivo(p.musica)}" style="width:100%;margin-top:8px"></audio>` : ""}
    </div>
    <div class="tarjeta">
      <h2>Imágenes · ${esc(p.estilo?.nombre || "")}</h2>${tarjetaTrabajo("imagenes")}${errorEtapa("imagenes")}
      <div class="fila" style="margin-bottom:10px">
        ${hayImgs ? "" : `<button id="imagenes" class="boton" ${ocupadoImg ? "disabled" : ""}>Generar las imágenes<span class="coste">${v.planos.length} planos × 2 · ~${v.planos.length * 50} créditos</span></button>`}
        ${clipsPend.length ? `<button id="clips" class="boton-suave" ${ocupadoImg ? "disabled" : ""}>Animar ${clipsPend.length} plano${clipsPend.length > 1 ? "s" : ""} clave<span class="coste">Kling O1 · 5 s cada uno</span></button>` : ""}
        ${listas && voz ? `<a class="boton" href="#${esc(p.id)}/montaje" style="text-decoration:none">Siguiente: montaje →</a>` : ""}
      </div>
      ${v.planos.map((x) => filaImagen(x, imgs[x.id], voz?.planos?.[x.id], ocupadoImg)).join("")}
    </div>`;
  $("#voz").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/voz`, json("POST"), "voz"));
  $("#musica")?.addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/musica`, json("POST"), "voz"));
  $("#musica-activa")?.addEventListener("change", async (ev) => { await api(`/api/proyectos/${p.id}/musica`, json("PUT", { activa: ev.target.checked })); await recargar(); });
  $("#imagenes")?.addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/imagenes`, json("POST"), "imagenes"));
  $("#clips")?.addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/clips`, json("POST"), "imagenes"));
  c.querySelectorAll("[data-variante]").forEach((b) => b.addEventListener("click", async () => {
    const [plano, i] = b.dataset.variante.split(":");
    try { await api(`/api/proyectos/${p.id}/planos/${plano}/elegir`, json("POST", { indice: Number(i) })); await recargar(); }
    catch (x) { avisar(x.message, true); }
  }));
  c.querySelectorAll("[data-otras]").forEach((b) => b.addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/planos/${b.dataset.otras}/imagenes`, json("POST"), "imagenes")));
}

function filaImagen(x, ip, t, ocupado) {
  const vars = ip?.variantes || [];
  return `<div class="plano" style="grid-template-columns:90px minmax(0,1fr)">
    <div><span class="chip rol-${x.rol}">${ROLES[x.rol]}</span><div class="meta" style="margin-top:6px">${x.id}${t ? `<br>${seg(t.inicio)}–${seg(t.fin)}` : ""}</div>
      ${ip?.animacion ? `<div class="chip" style="margin-top:6px">${ip.clip ? "clip ✓" : "clip"}</div>` : ""}</div>
    <div>
      <div class="voz" style="margin-bottom:6px">${esc(x.locucion)}${x.pantalla ? ` <span class="chip">${esc(x.pantalla)}</span>` : ""}</div>
      ${ip ? `<div class="motivo" style="margin:0 0 8px">${esc(ip.escena)}</div>` : ""}
      <div class="fila" style="align-items:flex-start">
        ${vars.map((va, i) => `<button data-variante="${x.id}:${i}" aria-pressed="${ip.elegida === i}" title="${esc(va.aviso || "")}"
            style="padding:0;border:3px solid ${ip.elegida === i ? "var(--pluma)" : "transparent"};border-radius:10px;background:none;cursor:pointer;position:relative">
            <img src="${archivo(va.archivo)}" alt="Variante ${i + 1} del plano ${x.id}" loading="lazy" style="width:108px;aspect-ratio:9/16;object-fit:cover;border-radius:7px;display:block">
            ${va.aviso ? `<span class="chip" style="position:absolute;left:4px;bottom:4px;background:var(--pluma);color:#fff;border-color:var(--pluma)">letras</span>` : ""}</button>`).join("")}
        ${ip?.error ? `<span class="error">${esc(ip.error)}</span>` : ""}
        ${vars.length ? `<button class="boton-suave" style="padding:4px 12px;font-size:12.5px" data-otras="${x.id}" ${ocupado ? "disabled" : ""}>Otras dos<span class="coste">~50 créditos</span></button>` : ""}
      </div>
    </div></div>`;
}

// ── Paso 6: montaje y revisión ────────────────────────────────────────────────────────────────────────────────────
function pintarMontaje(c) {
  const p = estado.proyecto, v = p.guion_actual, m = p.montajes?.[p.montajes.length - 1];
  const ocupado = !!estado.siguiendo?.montaje || !!estado.siguiendo?.voz || !!estado.siguiendo?.imagenes;
  const desfasado = p.etapas.montaje.estado === "desfasada";
  c.innerHTML = `
    <p class="rotulo">Paso 6 · Montaje y revisión</p>
    <h1>El vídeo <em>${m ? `versión ${m.version}` : ""}</em></h1>
    ${tarjetaTrabajo("montaje")}${tarjetaTrabajo("voz")}${tarjetaTrabajo("imagenes")}${errorEtapa("montaje")}
    <div class="fila" style="margin-bottom:14px">
      <button id="montar" class="${m && !desfasado ? "boton-suave" : "boton"}" ${ocupado ? "disabled" : ""}>${m ? "Volver a montar" : "Montar el vídeo"}<span class="coste">~30–60 s · sin coste</span></button>
      ${m ? `<a class="boton-suave" href="${archivo(m.archivo)}" download style="text-decoration:none">Descargar el MP4</a>
        <a class="boton-suave" href="${archivo(m.srt)}" download style="text-decoration:none">Subtítulos (.srt)</a>` : ""}
    </div>
    ${desfasado ? `<div class="avisos">Has cambiado algo después del último montaje: vuelve a montar para verlo.</div>` : ""}
    <div style="display:grid;grid-template-columns:minmax(0,320px) minmax(0,1fr);gap:20px;align-items:start" class="revision">
      <div>${m ? `<video controls playsinline src="${archivo(m.archivo)}" style="width:100%;aspect-ratio:9/16;background:#000;border-radius:14px"></video>
        <p class="motivo">${seg(m.duracion)} · ${m.con_musica ? "con música" : "sin música"} · 1080×1920</p>` : `<div style="aspect-ratio:9/16;border-radius:14px;background:var(--hueco)"></div>`}</div>
      <div><p class="rotulo">Rehacer un plano</p>
        ${v.planos.map((x) => {
          const ip = p.imagenes[x.id], va = ip?.variantes?.[ip.elegida];
          return `<div class="plano" style="grid-template-columns:70px minmax(0,1fr)">
            <div>${va ? `<img src="${archivo(va.archivo)}" alt="" style="width:64px;aspect-ratio:9/16;object-fit:cover;border-radius:6px">` : ""}<div class="meta">${x.id}</div></div>
            <div class="rejilla" style="gap:6px">
              <label class="campo">Locución<textarea rows="2" data-voz="${x.id}">${esc(x.locucion)}</textarea></label>
              <label class="campo">Texto en pantalla<input type="text" data-pantalla="${x.id}" value="${esc(x.pantalla)}"></label>
              <div class="fila">
                <button class="boton-suave" style="padding:4px 12px;font-size:12.5px" data-rehacer-voz="${x.id}" ${ocupado ? "disabled" : ""}>Rehacer la voz de este plano</button>
                <button class="boton-suave" style="padding:4px 12px;font-size:12.5px" data-guardar-pantalla="${x.id}">Cambiar el texto en pantalla</button>
                <button class="boton-suave" style="padding:4px 12px;font-size:12.5px" data-otras="${x.id}" ${ocupado ? "disabled" : ""}>Otra imagen</button>
              </div></div></div>`; }).join("")}
      </div></div>`;
  $("#montar").addEventListener("click", () => lanzar(`/api/proyectos/${p.id}/montaje`, json("POST"), "montaje"));
  c.querySelectorAll("[data-rehacer-voz]").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.rehacerVoz, texto = c.querySelector(`[data-voz="${id}"]`).value;
    lanzar(`/api/proyectos/${p.id}/planos/${id}/voz`, json("POST", { texto }), "voz");
  }));
  c.querySelectorAll("[data-guardar-pantalla]").forEach((b) => b.addEventListener("click", async () => {
    const id = b.dataset.guardarPantalla, texto = c.querySelector(`[data-pantalla="${id}"]`).value;
    try { await api(`/api/proyectos/${p.id}/planos/${id}/pantalla`, json("PUT", { texto })); avisar("Texto cambiado: vuelve a montar."); await recargar(); }
    catch (x) { avisar(x.message, true); }
  }));
  c.querySelectorAll("[data-otras]").forEach((b) => b.addEventListener("click", async () => {
    if (await lanzar(`/api/proyectos/${p.id}/planos/${b.dataset.otras}/imagenes`, json("POST"), "imagenes")) ir(p.id, "media");
  }));
}

async function guardarEdicion(cuerpo) {
  try {
    await api(`/api/proyectos/${estado.proyecto.id}/guion`, json("PUT", cuerpo));
    avisar("Guardado como versión nueva.");
    await recargar();
  } catch (e) { avisar(e.message, true); }
}

// ── Chat ──────────────────────────────────────────────────────────────────────────────────────────────────────────
function pintarChat() {
  const etapa = estado.paso;
  const ms = estado.proyecto.chat.filter((m) => m.etapa === etapa);
  $("#chat-mensajes").innerHTML = ms.length ? ms.map((m) => `<div class="msg ${m.rol}">${esc(m.texto)}</div>`).join("")
    : `<div class="motivo">${etapa === "conceptos" ? "Pregunta por un concepto o pide otros: «más polémicos», «para lectores jóvenes», «del capítulo 5»."
      : "Pide cambios al guion: «el giro no sorprende», «menos planos en el desarrollo», «otra pregunta de cierre»."}</div>`;
  $("#chat-mensajes").scrollTop = 1e6;
  const bloqueado = etapa === "guion" && (estado.proyecto.etapas.guion.estado === "bloqueado" || !estado.proyecto.guion_actual);
  const ocupado = !!estado.siguiendo?.[etapa];
  $("#chat-texto").disabled = bloqueado || ocupado;
  $("#chat-texto").placeholder = bloqueado ? "Desbloquea el guion para pedir cambios" : ocupado ? "Trabajando…" : "Escribe aquí";
}
$("#chat-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const texto = $("#chat-texto").value.trim();
  if (texto.length < 2) return;
  const etapa = estado.paso;
  const ok = await lanzar(`/api/proyectos/${estado.proyecto.id}/${etapa}/chat`, json("POST", { texto }), etapa);
  if (ok) $("#chat-texto").value = "";
});
$("#chat-texto").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); $("#chat-form").requestSubmit(); }
});

// ── Trabajos ──────────────────────────────────────────────────────────────────────────────────────────────────────
async function lanzar(ruta, opciones, etapa) {
  try {
    const { trabajo } = await api(ruta, opciones);
    seguir(trabajo, etapa);
    return true;
  } catch (e) { avisar(e.message, true); return false; }
}

function engancharTrabajos() {
  for (const [etapa, e] of Object.entries(estado.proyecto.etapas)) {
    if (e.estado === "en_curso" && e.trabajo && !estado.siguiendo?.[etapa]) seguir(e.trabajo, etapa);
  }
}

async function seguir(tid, etapa) {
  estado.siguiendo ||= {};
  estado.siguiendo[etapa] = { paso: "Empezando", inicio: new Date().toISOString() };
  pintar();
  let fallos = 0;
  while (true) {
    let t;
    try { t = await api(`/api/trabajos/${tid}`); fallos = 0; }
    catch (e) { if (++fallos > 6) { avisar(e.message, true); break; } await new Promise((r) => setTimeout(r, 3000)); continue; }
    if (t.estado === "en_curso") {
      estado.siguiendo[etapa] = { paso: t.paso, inicio: t.inicio };
      const tarjeta = document.querySelector(".trabajo");
      if (tarjeta) tarjeta.outerHTML = tarjetaTrabajo(etapa); else pintar();
      await new Promise((r) => setTimeout(r, 2000));
      continue;
    }
    delete estado.siguiendo[etapa];
    const listo = { conceptos: "Listo: conceptos al día.", guion: "Listo: guion al día.", estilo: "Listo: estilo al día.",
      voz: "Listo: audio al día.", imagenes: "Listo: imágenes al día.", montaje: "Listo: vídeo montado." };
    if (t.estado === "hecho") avisar(listo[etapa] || "Listo.");
    else avisar(t.error || "El trabajo no ha terminado bien.", true);
    break;
  }
  await recargar();
}

async function recargar() {
  estado.proyecto = await api(`/api/proyectos/${estado.proyecto.id}`);
  pintar();
}

(async function () {
  try {
    const e = await api("/api/estado");
    const sim = Object.entries(e.simulado).filter(([, v]) => v).map(([k]) => k === "magnific" ? "Magnific" : "ElevenLabs");
    if (sim.length) { $("#simulado").textContent = `Simulado: ${sim.join(" y ")}`; $("#simulado").hidden = false; }
  } catch { /* sin estado */ }
  cargar();
})();
