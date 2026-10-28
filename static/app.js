// app.js — chat del Asistente IA de Procesos (sin dependencias externas)

const log = document.getElementById("log");
const form = document.getElementById("chatForm");
const input = document.getElementById("input");
const modoExperto = document.getElementById("modoExperto");

// --- Markdown mínimo y seguro (negritas, listas, saltos de línea) ---
function escapar(t) {
  return (t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function formatear(texto) {
  let t = escapar(texto);
  t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // divide en párrafos por doble salto de línea
  const bloques = t.split(/\n{2,}/).map(b => "<p>" + b.replace(/\n/g, "<br>") + "</p>");
  return bloques.join("");
}
// Formatea todo lo que ya venía renderizado del servidor
document.querySelectorAll(".md").forEach(el => {
  el.innerHTML = formatear(el.textContent);
});

function scrollAbajo() { log.scrollTop = log.scrollHeight; }
scrollAbajo();

function burbuja(tipo, texto, { tag, raw } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + tipo;
  const md = document.createElement("div");
  md.className = "md";
  md.innerHTML = raw ? texto : formatear(texto);
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.appendChild(md);
  if (tag) {
    const sp = document.createElement("span");
    sp.className = "tag"; sp.textContent = tag;
    bubble.appendChild(sp);
  }
  wrap.appendChild(bubble);
  log.appendChild(wrap);
  scrollAbajo();
  return bubble;
}

function fuentes(bubble, sources) {
  (sources || []).forEach(s => {
    const det = document.createElement("details");
    det.className = "fuente";
    const titulo = (s.metadata && s.metadata.titulo) ? s.metadata.titulo : s.archivo;
    det.innerHTML = "<summary>📄 Fuente: " + escapar(titulo) + "</summary>";
    const pre = document.createElement("pre");
    pre.textContent = s.contenido || "";
    det.appendChild(pre);
    bubble.appendChild(det);
  });
}

async function enviar(mensaje) {
  burbuja("user", mensaje);
  const pensando = burbuja("assistant", "Pensando…");
  pensando.querySelector(".md").classList.add("typing");
  try {
    const resp = await fetch(window.URLS.chat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje, modo_experto: modoExperto && modoExperto.checked })
    });
    const data = await resp.json();
    const cont = pensando.querySelector(".md");
    cont.classList.remove("typing");
    cont.innerHTML = formatear(data.respuesta || "Sin respuesta");
    if (data.modo) {
      const sp = document.createElement("span");
      sp.className = "tag"; sp.textContent = data.modo;
      pensando.appendChild(sp);
    }
    fuentes(pensando, data.sources);
  } catch (e) {
    pensando.querySelector(".md").textContent = "Error de conexión: " + e;
  }
  scrollAbajo();
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const txt = input.value.trim();
  if (!txt) return;
  input.value = "";
  enviar(txt);
});

// Enter envía, Shift+Enter nueva línea
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// --- Análisis de imagen ---
const imgInput = document.getElementById("imgInput");
const btnImg = document.getElementById("btnImg");
btnImg.addEventListener("click", async () => {
  if (!imgInput.files || !imgInput.files[0]) {
    alert("Selecciona una imagen primero.");
    return;
  }
  const archivo = imgInput.files[0];
  const pregunta = input.value.trim();
  burbuja("user", "🖼️ Imagen adjunta" + (pregunta ? (": " + pregunta) : ""));
  input.value = "";
  const pensando = burbuja("assistant", "Analizando la imagen…");
  pensando.querySelector(".md").classList.add("typing");
  const fd = new FormData();
  fd.append("imagen", archivo);
  fd.append("pregunta", pregunta);
  try {
    const resp = await fetch(window.URLS.imagen, { method: "POST", body: fd });
    const data = await resp.json();
    const cont = pensando.querySelector(".md");
    cont.classList.remove("typing");
    cont.innerHTML = formatear(data.respuesta || "Sin respuesta");
  } catch (e) {
    pensando.querySelector(".md").textContent = "Error: " + e;
  }
  imgInput.value = "";
  scrollAbajo();
});
