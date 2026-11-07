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
  const e = estado.proyecto.etapas;
  if (e.guion.estado === "bloqueado") return "guion";
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
  else c.innerHTML = `<h1>${esc(PASOS.find((x) => x.id === estado.paso).nombre)}</h1><p class="entradilla">Este paso llega después de aprobar el guion: biblia de estilo, voz con ElevenLabs, imágenes con Magnific y montaje.</p>`;
  if (conChat) pintarChat();
}

function pintarPasos() {
  const p = estado.proyecto;
  const hecho = {
    libro: !!p, conceptos: !!p?.concepto_elegido, guion: p?.etapas.guion.estado === "bloqueado",
  };
  const abierto = { libro: true, conceptos: !!p, guion: !!p?.concepto_elegido, estilo: false, media: false, montaje: false };
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
    ${bloqueado ? `<div class="bloqueado">Guion aprobado y bloqueado. Lo siguiente es la biblia de estilo.</div>` : ""}
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
    if (t.estado === "hecho") avisar(etapa === "conceptos" ? "Listo: conceptos al día." : "Listo: guion al día.");
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
