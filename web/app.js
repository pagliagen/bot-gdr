// Interfaccia web del master GDR. Nessuna libreria: solo fetch e DOM.
"use strict";

const $ = (id) => document.getElementById(id);
const STATISTICHE = [["forza", "Forza"], ["agilita", "Agilità"], ["intelletto", "Intelletto"]];

let occupato = false;

// --- Utilità ---------------------------------------------------------------------
function esc(t) {
  return String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Mini-markdown sicuro: l'HTML è sempre escapato prima; poi **grassetto**, *corsivo*, elenchi e paragrafi.
function renderTesto(testo) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return testo
    .split(/\n{2,}/)
    .map((blocco) => {
      const righe = blocco.split("\n").map((r) => r.replace(/^\s*[-•]\s+/, "• ").replace(/^\s*\d+[.)]\s+/, (m) => m.trim() + " "));
      return "<p>" + righe.map(inline).join("<br>") + "</p>";
    })
    .join("");
}

async function api(percorso, corpo) {
  const opzioni = corpo === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) };
  const r = await fetch(percorso, opzioni);
  let dati = {};
  try { dati = await r.json(); } catch (_) { /* risposta non JSON */ }
  if (!r.ok) throw new Error(dati.detail || `Errore ${r.status}`);
  return dati;
}

function mostra(schermata) {
  $("creazione").hidden = schermata !== "creazione";
  $("gioco").hidden = schermata !== "gioco";
  $("orologio").hidden = schermata !== "gioco";
  $("btn-nuova").hidden = schermata !== "gioco";
}

// --- Creazione personaggio ---------------------------------------------------------
function costruisciCreazione(opz) {
  $("classi").innerHTML = opz.classi
    .map((c, i) => `<label class="classe"><input type="radio" name="classe" value="${esc(c.nome)}" ${i === 0 ? "checked" : ""}><span><strong>${esc(c.nome)}</strong><small>${esc(c.descrizione)}</small></span></label>`)
    .join("");
  const valori = opz.valori;
  $("statistiche").innerHTML = STATISTICHE.map(
    ([chiave, nome], i) =>
      `<div class="stat-riga"><label for="st-${chiave}">${nome}</label>
       <select id="st-${chiave}" data-stat="${chiave}">${valori.map((v) => `<option value="${v}" ${v === valori[i] ? "selected" : ""}>${v}</option>`).join("")}</select>
       <span class="mod" id="mod-${chiave}"></span></div>`
  ).join("");
  document.querySelectorAll("#statistiche select").forEach((s) => s.addEventListener("change", aggiornaStatistiche));
  aggiornaStatistiche();
}

function aggiornaStatistiche() {
  const sel = [...document.querySelectorAll("#statistiche select")];
  const valori = sel.map((s) => Number(s.value));
  sel.forEach((s) => {
    const mod = Math.floor((Number(s.value) - 10) / 2);
    $("mod-" + s.dataset.stat).textContent = (mod >= 0 ? "+" : "") + mod;
  });
  const ok = new Set(valori).size === valori.length;
  $("errore-creazione").textContent = ok ? "" : "Ogni valore va usato una volta sola.";
  $("btn-crea").disabled = !ok;
}

$("form-creazione").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("btn-crea").disabled = true;
  try {
    const valori = {};
    document.querySelectorAll("#statistiche select").forEach((s) => (valori[s.dataset.stat] = Number(s.value)));
    const classe = document.querySelector("input[name=classe]:checked").value;
    const { vista } = await api("/api/nuova", { nome: $("nome").value.trim(), classe, valori });
    $("chat").innerHTML = "";
    entraInPartita(vista);
    await inizia();
  } catch (err) {
    $("errore-creazione").textContent = err.message;
  } finally {
    aggiornaStatistiche();
  }
});

// --- Rendering della partita ---------------------------------------------------------
function entraInPartita(vista) {
  mostra("gioco");
  render(vista);
}

function render(v) {
  const p = v.personaggio, t = v.tempo, l = v.luogo;

  $("orologio-testo").textContent = `Giorno ${t.giorno} di ${t.giorni_totali} · ${String(t.ora).padStart(2, "0")}:00`;
  $("barra-giorni").style.width = `${Math.min(100, ((t.giorno - 1) * 24 + t.ora) / ((t.giorni_totali - 1) * 24 + 20) * 100)}%`;

  // Scena
  const img = $("img-luogo");
  const sorgente = v.scena ? v.scena.url : l.immagine;  // l'illustrazione di scena ha la precedenza sul luogo
  if (sorgente) {
    if (img.getAttribute("src") !== sorgente) img.src = sorgente;  // evita sfarfallii quando la pagina si aggiorna
    img.alt = l.nome;
    img.hidden = false;
  } else { img.hidden = true; img.removeAttribute("src"); }
  $("nome-luogo").textContent = (l.zona ? `${l.zona} · ${l.luogo_nome}` : l.nome) + (v.scena && v.scena.didascalia ? " — " + v.scena.didascalia : "");
  $("badge-img").hidden = !(v.immagini && v.immagini.in_corso > 0);
  const nota = $("nota-immagini");
  nota.hidden = !(v.immagini && v.immagini.errore);
  nota.textContent = v.immagini && v.immagini.errore ? "Immagini non disponibili: " + v.immagini.errore : "";
  programmaAggiornamento(v);

  // Zone del luogo (le chiuse sono segnate: provarci è lecito, ma il gioco rifiuta)
  $("zone-lista").innerHTML = l.zone
    .map((z) => {
      const info = z.stato === "chiusa" ? ` 🔒 ${esc(z.orari)}` : z.orari ? ` <small>${esc(z.orari)}</small>` : "";
      return `<button type="button" class="zona ${z.stato}" data-nome="${esc(z.nome)}" data-stato="${z.stato}" title="${esc(z.motivo || z.nome)}"${z.stato === "corrente" ? " disabled" : ""}>${esc(z.nome)}${info}</button>`;
    })
    .join("");
  document.querySelectorAll(".zona").forEach((b) => {
    b.addEventListener("click", () => inserisci(b.dataset.stato === "chiusa" ? `Provo a entrare: ${b.dataset.nome}. ` : `Vado: ${b.dataset.nome}. `));
  });

  // PNG presenti
  $("png-qui").innerHTML = l.png.length
    ? ""
    : '<p class="piccolo">Nessuno di importante è qui, ora.</p>';
  $("png-qui").innerHTML += l.png
    .map((n) => {
      const volto = n.immagine ? `<img src="${esc(n.immagine)}" alt="${esc(n.nome)}" loading="lazy">` : `<div class="iniziali">${esc(n.nome.trim()[0] || "?")}</div>`;
      return `<div class="png-card" role="button" tabindex="0" data-nome="${esc(n.nome)}" title="${esc(n.ruolo)}">${volto}${esc(n.nome.split(" ")[0])}<small>${esc(n.ruolo)}</small></div>`;
    })
    .join("");
  document.querySelectorAll(".png-card").forEach((c) => {
    const azione = () => inserisci(`Parlo con ${c.dataset.nome}. `);
    c.addEventListener("click", azione);
    c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); azione(); } });
  });

  $("collegamenti").textContent = "Da qui: " + l.collegamenti.map((c) => `${c.nome === "?" ? "luogo ignoto" : c.nome} (${c.ore} h)`).join(" · ");

  // Mappa
  const mappa = $("img-mappa");
  if (v.mappa.immagine) { mappa.src = v.mappa.immagine; mappa.hidden = false; }
  $("pins").innerHTML = v.mappa.pins
    .map((pin) => `<div class="pin ${pin.stato}" style="left:${pin.x * 100}%;top:${pin.y * 100}%" data-nome="${esc(pin.nome)}" title="${esc(pin.nome)}"><div class="punto"></div>${pin.stato !== "vicino" ? `<div class="etichetta">${esc(pin.nome)}</div>` : ""}</div>`)
    .join("");
  document.querySelectorAll(".pin.visitato").forEach((el) => el.addEventListener("click", () => inserisci(`Vado a ${el.dataset.nome}. `)));

  // Scheda
  $("s-nome").textContent = p.nome;
  $("s-classe").textContent = p.classe;
  const perc = Math.max(0, (p.pf / p.pf_max) * 100);
  $("pf-barra").style.width = perc + "%";
  $("pf-barra").style.background = perc > 50 ? "var(--verde)" : perc > 25 ? "var(--accento)" : "var(--rosso)";
  $("pf-testo").textContent = `PF ${p.pf}/${p.pf_max}`;
  $("s-stat").innerHTML = STATISTICHE.map(([k, nome]) => `<span>${nome} <b>${p.statistiche[k].valore}</b> (${p.statistiche[k].mod >= 0 ? "+" : ""}${p.statistiche[k].mod})</span>`).join("");
  $("s-inv").innerHTML = p.inventario.length ? p.inventario.map((o) => `<li>${esc(o)}</li>`).join("") : "<li>vuoto</li>";
  $("s-diario").innerHTML = v.diario.length ? v.diario.map((d) => `<li>${esc(d)}</li>`).join("") : "<li>vuoto</li>";

  // Fine partita
  if (v.fine) {
    $("fine-titolo").textContent = v.fine.titolo;
    $("fine-esito").textContent = v.fine.esito;
    $("fine").hidden = false;
  } else {
    $("fine").hidden = true;
  }
}

// Se ci sono illustrazioni in preparazione, ricarica lo stato ogni 3 secondi finché non sono pronte.
let timerImmagini = null;
function programmaAggiornamento(v) {
  if (timerImmagini || !v.immagini || v.immagini.in_corso === 0) return;
  timerImmagini = setTimeout(async () => {
    timerImmagini = null;
    if (!occupato) {
      try { const s = await api("/api/stato"); if (s.vista) render(s.vista); } catch (_) { /* riproverà al prossimo giro */ }
    } else {
      programmaAggiornamento({ immagini: { in_corso: 1 } });
    }
  }, 3000);
}

function inserisci(testo) {
  const campo = $("azione");
  campo.value = testo;
  campo.focus();
}

// --- Chat ---------------------------------------------------------------------------
function scorri() { const c = $("chat"); c.scrollTop = c.scrollHeight; }

function aggiungiMsg(ruolo, htmlInterno, classeExtra = "") {
  const d = document.createElement("div");
  d.className = `msg ${ruolo} ${classeExtra}`.trim();
  d.innerHTML = htmlInterno;
  $("chat").appendChild(d);
  scorri();
  return d;
}

function righeTool(tool) {
  return tool
    .map((e) => {
      if (e.tipo === "tool_call") return `🔧 ${esc(e.nome)}(${esc(JSON.stringify(e.argomenti))})`;
      const ko = e.risultato && e.risultato.ok === false;
      return `<span class="${ko ? "ko" : ""}">   ↳ ${esc(JSON.stringify(e.risultato))}</span>`;
    })
    .join("\n");
}

function aggiungiNarrazione(esito) {
  let extra = "";
  if (esito.eventi_mondo && esito.eventi_mondo.length)
    extra += `<div class="eventi">${esito.eventi_mondo.map((t) => `<span class="chip">📜 ${esc(t)}</span>`).join("")}</div>`;
  if (esito.tool && esito.tool.length) extra += `<div class="tool-log">${righeTool(esito.tool)}</div>`;
  aggiungiMsg("narratore", renderTesto(esito.narrazione) + extra);
}

function impostaOccupato(si) {
  occupato = si;
  $("btn-invia").disabled = si;
  $("azione").disabled = si;
  if (!si) $("azione").focus();
}

async function eseguiTurno(chiamata, ripristinaTesto) {
  impostaOccupato(true);
  const attesa = aggiungiMsg("sistema", 'Il narratore scrive<span class="pensando"> <span>.</span><span>.</span><span>.</span></span>');
  try {
    const esito = await chiamata();
    attesa.remove();
    aggiungiNarrazione(esito);
    render(esito.vista);
  } catch (err) {
    attesa.remove();
    aggiungiMsg("sistema", esc(err.message), "errore-msg");
    if (ripristinaTesto !== undefined) $("azione").value = ripristinaTesto;
  } finally {
    impostaOccupato(false);
  }
}

function inizia() {
  return eseguiTurno(() => api("/api/inizia", {}));
}

$("form-azione").addEventListener("submit", (e) => {
  e.preventDefault();
  const testo = $("azione").value.trim();
  if (!testo || occupato) return;
  $("azione").value = "";
  const mio = aggiungiMsg("giocatore", renderTesto(testo));
  eseguiTurno(() => api("/api/turno", { testo }), testo).then(() => {
    // se il turno è fallito la risposta d'errore resta nella chat: il messaggio del giocatore non è stato registrato
    if ($("chat").lastElementChild && $("chat").lastElementChild.classList.contains("errore-msg")) mio.remove();
  });
});

// --- Comandi dell'header --------------------------------------------------------------
let opzioniCreazione = null;
function nuovaPartita() {
  if (!confirm("Iniziare una nuova partita? Il salvataggio attuale verrà sostituito.")) return;
  $("fine").hidden = true;
  $("nome").value = "";
  mostra("creazione");
}
$("btn-nuova").addEventListener("click", nuovaPartita);
$("btn-fine-nuova").addEventListener("click", () => { $("fine").hidden = true; mostra("creazione"); });

$("debug").addEventListener("change", (e) => {
  document.body.classList.toggle("debug-on", e.target.checked);
  try { localStorage.setItem("gdr-debug", e.target.checked ? "1" : "0"); } catch (_) { /* storage non disponibile */ }
});

// --- Avvio -----------------------------------------------------------------------------
async function avvio() {
  try {
    if (localStorage.getItem("gdr-debug") === "1") { $("debug").checked = true; document.body.classList.add("debug-on"); }
  } catch (_) { /* ignora */ }
  try {
    const s = await api("/api/stato");
    opzioniCreazione = s.creazione;
    costruisciCreazione(s.creazione);
    if (!s.in_corso) { mostra("creazione"); return; }
    entraInPartita(s.vista);
    // Ripristina la chat dalla cronologia salvata
    for (const m of s.vista.cronologia) aggiungiMsg(m.ruolo, renderTesto(m.testo));
    if (s.vista.cronologia.length === 0) await inizia(); // partita creata ma mai avviata
  } catch (err) {
    mostra("creazione");
    $("errore-creazione").textContent = "Impossibile contattare il server: " + err.message;
  }
}
avvio();
