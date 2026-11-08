// Interfaccia web del master GDR. Nessuna libreria: solo fetch e DOM.
"use strict";

const $ = (id) => document.getElementById(id);
const STATISTICHE = [["forza", "Forza"], ["agilita", "Agilità"], ["intelletto", "Intelletto"]];

let occupato = false;
let utente = null;        // nome dell'utente collegato
let sonoAdmin = false;    // può vedere il debug
let avventuraId = null;   // avventura in corso
const partita = (azione) => `/api/partite/${encodeURIComponent(avventuraId)}/${azione}`;

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
  if (r.status === 401 && percorso !== "/api/accedi") { utente = null; mostra("accesso"); }  // sessione scaduta
  if (!r.ok) throw new Error(typeof dati.detail === "string" ? dati.detail : `Errore ${r.status}`);
  return dati;
}

// Come api(), ma per le risposte in streaming: una riga JSON alla volta (vedi gdr/web.py, `_flusso`).
// Chiama `suEvento` per ogni riga e restituisce l'esito finale del turno.
async function apiFlusso(percorso, corpo, suEvento) {
  const r = await fetch(percorso, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  if (!r.ok) {  // errori prima dell'inizio dello streaming (login, partita assente, testo vuoto...)
    let dati = {};
    try { dati = await r.json(); } catch (_) { /* non JSON */ }
    if (r.status === 401) { utente = null; mostra("accesso"); }
    throw new Error(typeof dati.detail === "string" ? dati.detail : `Errore ${r.status}`);
  }
  const lettore = r.body.getReader();
  const decodifica = new TextDecoder();
  let resto = "", esito = null;
  const riga = (s) => {
    if (!s.trim()) return;
    const ev = JSON.parse(s);
    if (ev.tipo === "errore") throw new Error(ev.detail);
    if (ev.tipo === "fine") esito = ev.esito;
    else suEvento(ev);
  };
  for (;;) {
    const { done, value } = await lettore.read();
    if (done) break;
    resto += decodifica.decode(value, { stream: true });
    const righe = resto.split("\n");
    resto = righe.pop();  // l'ultima può essere incompleta
    righe.forEach(riga);
  }
  riga(resto);
  if (!esito) throw new Error("Connessione interrotta: riprova.");
  return esito;
}

function mostra(schermata) {
  for (const s of ["accesso", "menu", "creazione", "gioco"]) $(s).hidden = schermata !== s;
  $("orologio").hidden = schermata !== "gioco";
  $("btn-mappa").hidden = schermata !== "gioco";
  $("btn-menu").hidden = !utente || schermata === "menu";
  $("btn-esci").hidden = !utente;
  $("utente").hidden = !utente;
  $("utente").textContent = utente || "";
  $("debug-box").hidden = !(utente && sonoAdmin);
  if (schermata === "accesso" || schermata === "menu") $("titolo").textContent = "Master GDR";
  if (schermata !== "gioco") { $("mappa-popup").hidden = true; $("fine").hidden = true; }
}

// --- Accesso -----------------------------------------------------------------------
let modoRegistra = false;
function impostaModoAccesso(registra) {
  modoRegistra = registra;
  $("accesso-titolo").textContent = registra ? "Crea un account" : "Accedi";
  $("btn-accedi").textContent = registra ? "Registrati" : "Accedi";
  $("acc-codice-riga").hidden = !registra;
  $("acc-password").autocomplete = registra ? "new-password" : "current-password";
  $("cambia-modo").textContent = registra ? "Hai già un account? Accedi" : "Non hai un account? Registrati";
  $("cambia-modo").hidden = registra ? false : !registrazioneAperta;
  $("errore-accesso").textContent = "";
}
let registrazioneAperta = false;
$("cambia-modo").addEventListener("click", (e) => { e.preventDefault(); impostaModoAccesso(!modoRegistra); });

$("form-accesso").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("btn-accedi").disabled = true;
  try {
    const corpo = { nome: $("acc-nome").value, password: $("acc-password").value };
    if (modoRegistra) corpo.codice = $("acc-codice").value;
    await api(modoRegistra ? "/api/registrati" : "/api/accedi", corpo);
    $("acc-password").value = "";
    $("acc-codice").value = "";
    await avvio();
  } catch (err) {
    $("errore-accesso").textContent = err.message;
  } finally {
    $("btn-accedi").disabled = false;
  }
});

$("btn-esci").addEventListener("click", async () => {
  try { await api("/api/esci", {}); } catch (_) { /* esce comunque */ }
  utente = null; avventuraId = null;
  $("chat").innerHTML = "";
  impostaModoAccesso(false);
  mostra("accesso");
});

// --- Scelta dell'avventura -----------------------------------------------------------
async function vaiMenu() {
  avventuraId = null;
  mostra("menu");
  $("avventure").innerHTML = '<p class="piccolo">Carico le avventure…</p>';
  try {
    const { avventure } = await api("/api/avventure");
    $("avventure").innerHTML = avventure.map(cardAvventura).join("");
    document.querySelectorAll("[data-continua]").forEach((b) => b.addEventListener("click", () => continua(b.dataset.continua)));
    document.querySelectorAll("[data-nuova]").forEach((b) => b.addEventListener("click", () => nuovaPartita(b.dataset.nuova, b.dataset.titolo, b.dataset.conferma === "1")));
  } catch (err) {
    $("avventure").innerHTML = `<p class="errore">${esc(err.message)}</p>`;
  }
}

function cardAvventura(a) {
  const s = a.salvataggio;
  let stato = "", azioni = "";
  const nuova = (testo, secondario, conferma) =>
    `<button type="button" class="${secondario ? "secondario" : ""}" data-nuova="${esc(a.id)}" data-titolo="${esc(a.titolo)}" data-conferma="${conferma ? 1 : 0}">${testo}</button>`;
  if (s && !s.conclusa) {
    stato = `Partita in corso: ${esc(s.personaggio)} il ${esc(s.classe)} · giorno ${s.giorno} di ${a.giorni}, ${String(s.ora).padStart(2, "0")}:00 · ${esc(s.luogo)}`;
    azioni = `<button type="button" data-continua="${esc(a.id)}">Continua</button>${nuova("Nuova partita", true, true)}`;
  } else if (s) {
    stato = `Conclusa: ${esc(s.personaggio)} · ${esc(s.esito || "")}`;
    azioni = nuova("Nuova partita", false, false);
  } else {
    azioni = nuova("Inizia l'avventura", false, false);
  }
  return `<article class="avventura"><h3>${esc(a.titolo)}</h3><p>${esc(a.presentazione)}</p>
    <p class="piccolo">${a.giorni} giorni di gioco · ${esc(a.mondo)}</p>
    ${stato ? `<p class="salvataggio">${stato}</p>` : ""}<div class="azioni">${azioni}</div></article>`;
}

async function continua(id) {
  avventuraId = id;
  try {
    const { vista } = await api(partita("continua"), {});
    $("chat").innerHTML = "";
    entraInPartita(vista);
    for (const m of vista.cronologia) aggiungiMsg(m.ruolo, renderTesto(m.testo));
    if (vista.cronologia.length === 0) await inizia();  // partita creata ma mai avviata
  } catch (err) {
    await vaiMenu();
    alert(err.message);
  }
}

function nuovaPartita(id, titolo, conferma) {
  if (conferma && !confirm("Iniziare una nuova partita? Il salvataggio di questa avventura verrà sostituito.")) return;
  avventuraId = id;
  $("nome").value = "";
  $("creazione-avventura").textContent = `— ${titolo}`;
  mostra("creazione");
}

// --- Mappa in popup ---------------------------------------------------------------
function mappa(aperta) {
  $("mappa-popup").hidden = !aperta;
  if (aperta) $("btn-mappa-chiudi").focus(); else if (!$("gioco").hidden) $("btn-mappa").focus();
}
$("btn-mappa").addEventListener("click", () => mappa($("mappa-popup").hidden));
$("btn-mappa-chiudi").addEventListener("click", () => mappa(false));
$("mappa-popup").addEventListener("click", (e) => { if (e.target === $("mappa-popup")) mappa(false); });  // clic sullo sfondo
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("mappa-popup").hidden) mappa(false); });

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
    const { vista } = await api(partita("nuova"), { nome: $("nome").value.trim(), classe, valori });
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
  $("titolo").textContent = vista.avventura.titolo;
  render(vista);
}

function render(v) {
  const p = v.personaggio, t = v.tempo, l = v.luogo;

  $("orologio-testo").textContent = `Giorno ${t.giorno} di ${t.giorni_totali} · ${String(t.ora).padStart(2, "0")}:00`;
  $("barra-giorni").style.width = `${Math.min(100, ((t.giorno - 1) * 24 + t.ora) / (t.ore_finali) * 100)}%`;

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
  const imgMappa = $("img-mappa");
  if (v.mappa.immagine) { imgMappa.src = v.mappa.immagine; imgMappa.hidden = false; }
  $("pins").innerHTML = v.mappa.pins
    .map((pin) => `<div class="pin ${pin.stato}" style="left:${pin.x * 100}%;top:${pin.y * 100}%" data-nome="${esc(pin.nome)}" title="${esc(pin.nome)}"><div class="punto"></div>${pin.stato !== "vicino" ? `<div class="etichetta">${esc(pin.nome)}</div>` : ""}</div>`)
    .join("");
  document.querySelectorAll(".pin.visitato").forEach((el) => el.addEventListener("click", () => { mappa(false); inserisci(`Vado a ${el.dataset.nome}. `); }));

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

  // Annulla: solo se c'è un turno da annullare
  $("btn-annulla").hidden = !v.puo_annullare;
  $("btn-fine-annulla").hidden = !v.puo_annullare;

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
      try { const s = await api(partita("stato")); if (s.vista) render(s.vista); } catch (_) { /* riproverà al prossimo giro */ }
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
  $("btn-annulla").disabled = si;
  $("azione").disabled = si;
  if (!si) $("azione").focus();
}

// Esegue un turno in streaming: il testo del narratore compare man mano in una "bolla provvisoria",
// che alla fine viene sostituita dalla narrazione definitiva (con eventi e log dei tool).
async function eseguiTurno(percorso, corpo, ripristinaTesto) {
  impostaOccupato(true);
  const attesa = aggiungiMsg("sistema", 'Il narratore scrive<span class="pensando"> <span>.</span><span>.</span><span>.</span></span>');
  let bolla = null, testo = "";
  const togliBolla = () => { if (bolla) { bolla.remove(); bolla = null; } testo = ""; attesa.hidden = false; };
  try {
    const esito = await apiFlusso(percorso, corpo, (ev) => {
      if (ev.tipo === "testo") {
        testo += ev.t;
        attesa.hidden = true;
        if (!bolla) bolla = aggiungiMsg("narratore", "");
        bolla.innerHTML = renderTesto(testo);
        scorri();
      } else if (ev.tipo === "scarta") {
        togliBolla();  // il testo era un preambolo prima di un tool: non è la narrazione
      }
    });
    togliBolla();
    attesa.remove();
    aggiungiNarrazione(esito);
    render(esito.vista);
  } catch (err) {
    togliBolla();
    attesa.remove();
    aggiungiMsg("sistema", esc(err.message), "errore-msg");
    if (ripristinaTesto !== undefined) $("azione").value = ripristinaTesto;
  } finally {
    impostaOccupato(false);
  }
}

function inizia() {
  return eseguiTurno(partita("inizia-stream"), {});
}

$("form-azione").addEventListener("submit", (e) => {
  e.preventDefault();
  const testo = $("azione").value.trim();
  if (!testo || occupato) return;
  $("azione").value = "";
  const mio = aggiungiMsg("giocatore", renderTesto(testo));
  eseguiTurno(partita("turno-stream"), { testo }, testo).then(() => {
    // se il turno è fallito la risposta d'errore resta nella chat: il messaggio del giocatore non è stato registrato
    if ($("chat").lastElementChild && $("chat").lastElementChild.classList.contains("errore-msg")) mio.remove();
  });
});

// Annulla l'ultimo turno: la chat si ricostruisce dal salvataggio e il testo scritto torna nella casella.
async function annulla() {
  if (occupato) return;
  impostaOccupato(true);
  try {
    const { vista, testo } = await api(partita("annulla"), {});
    $("chat").innerHTML = "";
    for (const m of vista.cronologia) aggiungiMsg(m.ruolo, renderTesto(m.testo));
    render(vista);
    $("azione").value = testo;
  } catch (err) {
    aggiungiMsg("sistema", esc(err.message), "errore-msg");
  } finally {
    impostaOccupato(false);
  }
}
$("btn-annulla").addEventListener("click", annulla);
$("btn-fine-annulla").addEventListener("click", annulla);

// --- Comandi dell'header --------------------------------------------------------------
$("btn-menu").addEventListener("click", vaiMenu);
$("btn-fine-nuova").addEventListener("click", vaiMenu);

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
    const io = await api("/api/io");
    costruisciCreazione(io.creazione);
    utente = io.utente;
    sonoAdmin = io.admin;
    registrazioneAperta = io.registrazione_aperta;
    if (!utente) { impostaModoAccesso(false); mostra("accesso"); return; }
    await vaiMenu();
  } catch (err) {
    mostra("accesso");
    $("errore-accesso").textContent = "Impossibile contattare il server: " + err.message;
  }
}
avvio();
