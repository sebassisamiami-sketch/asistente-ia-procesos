// copiloto.js — graba audio en el navegador y lo envía al servidor

let mediaRecorder = null;
let chunks = [];

const btnGrabar = document.getElementById("btnGrabar");
const btnParar = document.getElementById("btnParar");
const estado = document.getElementById("estado");
const modo = document.getElementById("modo");
const resultado = document.getElementById("resultado");
const preguntaEl = document.getElementById("pregunta");
const respuestaEl = document.getElementById("respuesta");

function escapar(t){return (t||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function formatear(t){
  let s = escapar(t).replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
  return s.split(/\n{2,}/).map(b=>"<p>"+b.replace(/\n/g,"<br>")+"</p>").join("");
}

btnGrabar.addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    chunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    mediaRecorder.onstop = enviar;
    mediaRecorder.start();
    btnGrabar.disabled = true;
    btnParar.disabled = false;
    estado.textContent = "🔴 Grabando… habla tu pregunta.";
  } catch (e) {
    estado.textContent = "No se pudo acceder al micrófono: " + e;
  }
});

btnParar.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
  }
  btnGrabar.disabled = false;
  btnParar.disabled = true;
  estado.textContent = "⏳ Transcribiendo y generando respuesta…";
});

async function enviar() {
  const blob = new Blob(chunks, { type: "audio/webm" });
  const fd = new FormData();
  fd.append("audio", blob, "pregunta.webm");
  fd.append("modo", modo.value);
  try {
    const resp = await fetch(window.URLS.copiloto, { method: "POST", body: fd });
    const data = await resp.json();
    if (data.error) { estado.textContent = "Error: " + data.error; return; }
    resultado.style.display = "block";
    preguntaEl.textContent = data.pregunta || "(sin texto)";
    respuestaEl.innerHTML = formatear(data.respuesta || "");
    estado.textContent = "Listo.";
  } catch (e) {
    estado.textContent = "Error de conexión: " + e;
  }
}
