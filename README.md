# Master di gioco di ruolo con LLM (progetto di studio)

Partita in solitaria da terminale, in italiano, ambientata in un fantasy medievale.
L'LLM fa da **narratore**; il codice fa da **arbitro**: tiri di dado, punti vita, inventario e mappa sono gestiti da *tool* Python, mai inventati dal modello.
Regole ispirate al D&D 5e / d20 SRD, semplificate (tre statistiche: Forza, Agilità, Intelletto).

## Installazione

Serve Python 3.11+ e [Ollama](https://ollama.com) avviato in locale con almeno un modello che supporti i *tools* (es. `ollama pull qwen3.5:9b`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # poi modifica .env (scegli OLLAMA_MODEL)
```

## Configurazione (`.env`)

| Variabile | Significato |
|---|---|
| `LLM_PROVIDER` | `ollama` (predefinito). `anthropic` è opzionale e richiede `pip install anthropic` e `ANTHROPIC_API_KEY` |
| `OLLAMA_MODEL`, `OLLAMA_HOST`, `OLLAMA_NUM_CTX` | modello locale (serve un modello con supporto *tools*, es. `qwen3.5:9b`), indirizzo e contesto |
| `MAX_ITERAZIONI`, `SOGLIA_MESSAGGI`, `MESSAGGI_RECENTI` | limiti del ciclo e della memoria (opzionali) |
| `CODICE_INVITO` | **serve per giocare dal web**: è il codice che chi si registra deve scrivere. Senza, nessuno può creare un account |
| `ADMIN` | nomi utente (separati da virgola) che vedono la casella *debug*; per tutti gli altri i tool non vengono mai inviati al browser |
| `COOKIE_SICURO` | `on` se il sito è dietro HTTPS: il cookie di login viaggia solo su connessioni cifrate |
| `MAX_TURNI_CONTEMPORANEI` | quanti turni del narratore girano insieme (default 1: la GPU è una, gli altri giocatori aspettano in coda) |

## Avvio

```bash
python main.py --web        # interfaccia web su http://127.0.0.1:8000 (consigliata)
python main.py --web --host 0.0.0.0 --porta 8000   # raggiungibile da altri PC della rete
python main.py              # versione da terminale: riprende la partita salvata o ne crea una nuova
python main.py --avventura acquaverde   # terminale: sceglie l'avventura (default la prima)
python main.py --nuova      # ignora il salvataggio
python main.py --debug      # mostra i tool chiamati, con argomenti ed esiti
```

**Accesso e avventure (web).** Si entra con nome utente e password; la registrazione richiede il `CODICE_INVITO`. Dopo il login si sceglie l'avventura: per ognuna si può **continuare** la propria partita (se c'è) o **iniziarne una nuova**. Ogni utente ha un salvataggio per avventura in `saves/<utente>/<avventura>.json`. Le password sono salvate con scrypt e un sale, il login è un cookie firmato con scadenza, i tentativi sbagliati vengono rallentati. Se lo metti online: usa HTTPS (un reverse proxy come nginx o Caddy) e metti `COOKIE_SICURO=on`; il modello di testo e quello di immagini girano comunque sul tuo PC, quindi reggono pochi giocatori alla volta.

**Interfaccia web.** Mostra l'immagine del luogo (se esiste in `assets/luoghi/`), i ritratti dei PNG presenti, la mappa con i luoghi scoperti (gli altri restano nella nebbia), scheda, inventario, diario, orologio e chat. Cliccare un PNG o un luogo sulla mappa scrive l'azione nel campo di testo. La casella *debug* mostra i tool chiamati sotto ogni risposta (attenzione: contengono spoiler). La partita si salva a ogni turno e riprende da sola.

Comandi in partita (versione terminale): `/scheda` `/mappa` `/diario` `/debug` `/salva` `/aiuto` `/esci`.
Nel terminale il salvataggio è `saves/terminale/<avventura>.json`, separato da quelli del web (si aggiorna a ogni turno).

Per confrontare modelli Ollama sullo stesso scenario: `python scripts/prova_modelli.py qwen3.5:9b gemma4:12b`.

## Struttura

```
main.py                 punto d'ingresso
avventure/<id>/         UNA CARTELLA PER AVVENTURA: lore (YAML) e assets/ (mappa, ritratti, luoghi, zone)
prompts/master.md       system prompt del narratore (modificabile anche a partita in corso)
gdr/sessione.py         una partita in corso: stato + agente + salvataggio (senza interfaccia)
gdr/gestore.py          una sessione per ogni coppia (utente, avventura); risorse condivise
gdr/avventure.py        il catalogo delle avventure (le cartelle in avventure/)
gdr/utenti.py           utenti, password (scrypt) e cookie di login firmato
gdr/web.py              interfaccia web (FastAPI); la pagina è in web/
gdr/cli.py              interfaccia da terminale (unico file con input/print)
gdr/agent.py            il ciclo dell'agente
gdr/tools.py            schemi e implementazione dei tool
gdr/rules.py            regole pure (dadi, modificatori, prove)
gdr/memory.py           system prompt dinamico + compressione della cronologia
gdr/state.py, models.py stato della partita e salvataggio JSON
gdr/character_creation.py  creazione del personaggio
gdr/immagini.py         generazione di immagini in background (Ollama)
gdr/lore.py             carica e interroga la lore (luoghi, PNG, eventi, finali)
gdr/llm/                provider intercambiabili (Ollama; Anthropic opzionale)
```

## Il mondo: Acquaverde e l'avventura "Il Patto Sciolto"

### Le avventure incluse
| Id | Titolo | Genere | Durata |
|---|---|---|---|
| `acquaverde` | Il Patto Sciolto | fantasy ironico: un fiume che sparisce e un patto antico | 7 giorni |
| `vallombra` | La Veglia di Vallombra | horror / folk horror: un villaggio isolato dalla neve dove l'ospite è l'offerta di un rito | 5 giorni |
| `marenza` | Il Furto della Lanterna Maestra | giallo ironico: la lanterna che tiene lontana la nebbia è sparita | 4 giorni |

Il tono, l'epoca e lo stile delle immagini sono nel `mondo.yaml` di ciascuna: il prompt del narratore è lo stesso per tutte e li legge da lì. Dopo aver modificato una lore, `python scripts/verifica_avventure.py` controlla riferimenti, orari dei PNG, flag e finali raggiungibili.

### Aggiungere un'avventura
Crea `avventure/<id>/` (id: lettere minuscole, numeri e `_`) copiando la struttura di `acquaverde`: i file YAML qui sotto più una cartella `assets/` con `mappa.webp` e le immagini. Nel file `avventura.yaml` ci sono titolo, presentazione, durata in giorni, ora e nome del momento finale. Il catalogo la trova da solo al riavvio. Per generare le immagini mancanti (mappa compresa, se in `mondo.yaml` c'è `prompt_mappa`): `python scripts/genera_immagini.py <id>`; poi controlla le coordinate dei pin in `luoghi.yaml` guardando la mappa.

### La lore di un'avventura (file YAML modificabili a mano, in `avventure/<id>/`)

| File | Contenuto |
|---|---|
| `mondo.yaml` | sintesi, storia, religioni, fazioni, regole del mondo, stile delle immagini |
| `luoghi.yaml` | 7 luoghi, coordinate sulla mappa, collegamenti con le ore di viaggio |
| `zone.yaml` | le zone dentro ogni luogo (piazza, locanda, emporio, archivio...), con orari di apertura e requisiti |
| `png.yaml` | 13 PNG con aspetto, scopo, segreto e routine giornaliera |
| `avventura.yaml` | cronologia di 7 giorni, flag, finali, prove suggerite |
| `immagini_statiche.md` | prompt per generare mappa, ritratti e luoghi |

**Il mondo avanza da solo.** Il codice tiene un orologio (giorno e ora). Quando il tempo passa (spostamenti con `sposta_in`, riposi con `avanza_tempo`), gli eventi della cronologia scattano al loro giorno **qualunque cosa faccia il giocatore**, e i tool li restituiscono al master. Il giocatore cambia come va a finire (i *flag*), non se gli eventi accadono. Il giorno 7 alle 20:00 il tempo si ferma e `valuta_finale` sceglie il finale in base ai flag.

**Il master non può "regalare" i progressi.** `imposta_flag` controlla in codice luogo, requisiti, oggetti e che l'ultima prova di abilità sia riuscita con statistica e CD giuste. **La geografia è vincolata**: si va solo tra luoghi collegati.

**Luoghi e zone.** Ogni luogo della mappa contiene delle zone: muoversi tra zone non costa tempo (`sposta_in`), cambiare luogo sì, e si arriva sempre nella zona d'ingresso. Una zona può avere **orari** (l'emporio apre solo la mattina) o **flag richiesti** (la stanza dei registri si apre solo con il capitano come alleato): se è chiusa, il codice rifiuta l'ingresso e dice quando riapre; per aspettare il giocatore usa `avanza_tempo`. Se il tempo passa mentre si è dentro e la zona chiude, il personaggio viene accompagnato fuori. Anche i **PNG** hanno una routine oraria: se non sono nella zona a quell'ora, non si incontrano. Alcuni flag richiedono una zona precisa (il Contratto si cerca solo nell'archivio).

**La lore non sta tutta nel prompt.** Nel system prompt ci sono un riassunto, il luogo attuale con i PNG presenti, l'orologio e i flag. Per il resto il master usa `consulta_lore`. I segreti sono marcati come riservati.

## Immagini

- **Statiche** (le fai tu, prompt in `avventure/<id>/immagini_statiche.md`): `assets/mappa.webp`, `assets/png/*.webp`, `assets/luoghi/*.webp`, `assets/zone/<luogo>_<zona>.webp`, dentro la cartella dell'avventura. Quelle che mancano si generano in locale con `python scripts/genera_immagini.py <avventura>` (salta i file già presenti).
- **Generate in locale** con un modello di immagini di Ollama (`ollama pull x/z-image-turbo`, circa 12 GB; richiede macOS con Apple Silicon): quando arrivi in una zona senza immagine statica, il codice genera l'illustrazione, la salva in `avventure/<id>/assets/generate/` e la riusa. Il master può inoltre chiamare `illustra_scena` per i momenti chiave (limite: una ogni 3 turni); se nomina un PNG, il codice aggiunge in automatico il suo aspetto per mantenerlo coerente con il ritratto.
- La generazione avviene **in background** (circa 30 secondi) e la pagina mostra l'immagine appena è pronta. Mentre un'immagine si genera, il modello di testo rallenta (usano la stessa GPU e memoria): se il PC fatica, metti `IMMAGINI=off` nel `.env`.
- Vanno solo nell'interfaccia web, non nel terminale.

## Come funziona il ciclo dell'agente

Il modello da solo può solo produrre testo. Con il *tool use* gli diciamo quali funzioni esistono (nome, descrizione, argomenti); a ogni risposta il modello può scegliere se **scrivere testo** oppure **chiedere di eseguire uno o più tool**. Il codice (`Agente._ciclo` in `gdr/agent.py`) fa così:

1. Costruisce il *system prompt*: istruzioni del master + stato attuale (scheda, luogo) + diario.
2. **Chiama il modello** con la cronologia e la lista dei tool.
3. Se la risposta contiene richieste di tool → li **esegue** (`Strumenti.esegui`) e aggiunge i risultati alla cronologia come messaggio `tool_result`.
4. **Torna al punto 1** (il modello legge i risultati e decide: altri tool o narrazione).
5. Se la risposta non contiene tool, è la **narrazione finale** e viene mostrata al giocatore.

Un tetto (`MAX_ITERAZIONI`) evita cicli infiniti. I tool non vanno mai in crash: se gli argomenti sono sbagliati restituiscono `{"ok": false, "errore": "..."}` e il modello può correggersi.

**Memoria.** I messaggi vecchi non si mandano per sempre: sopra `SOGLIA_MESSAGGI` si tengono solo gli ultimi `MESSAGGI_RECENTI` (tagliando sempre all'inizio di un turno, per non separare un tool dal suo risultato). Il filo della storia resta nel **diario** (tool `scrivi_diario`), che viene reinserito nel system prompt a ogni chiamata.

**Provider.** `gdr/llm/base.py` definisce un'interfaccia con `chiama(system, messaggi, tools)` e `chiama_stream(...)`. Ogni provider traduce da/verso il proprio formato; l'agente non sa quale usa. Un provider senza streaming eredita una versione che consegna tutto il testo in un colpo solo.

**Streaming.** Nel web il testo del narratore compare man mano (`/api/partite/<avventura>/turno-stream`, una riga JSON per pezzetto). Se il modello scrive del testo *prima* di chiamare un tool, quel testo non è la narrazione finale: l'agente manda un segnale "scarta" e l'interfaccia lo toglie. La narrazione definitiva (con eventi e log dei tool) sostituisce la bolla provvisoria alla fine del turno.

**Annulla ultimo turno.** Prima di ogni turno si ricorda lo stato com'era (`<avventura>.prev.json` accanto al salvataggio). Il pulsante "↩ Annulla" lo ripristina e rimette nella casella il testo scritto, per riformularlo. Un solo livello; l'apertura dell'avventura non si annulla. Attenzione: i dadi vengono tirati di nuovo, quindi annullare dopo una prova fallita è un modo per ritentare.

## Limiti noti

- I modelli piccoli (locali) a volte "dimenticano" di chiamare un tool e inventano l'esito: succede, ed è il motivo per cui conviene provare più modelli. Il prompt in `prompts/master.md` è il primo posto dove intervenire.
- Se un turno fallisce (rete, API) viene annullato, ma le modifiche già fatte dai tool nello stesso turno non vengono ripristinate.

## Idee per i prossimi passi

1. **Bot Telegram**: un nuovo file gemello di `cli.py` che chiama `agente.turno(testo)`; uno stato per chat.
2. **PNG con memoria**: un'entità per ogni PNG (atteggiamento, cosa sa del giocatore) con tool `parla_con_png` / `aggiorna_png`.
3. **Combattimento strutturato**: iniziativa, CA e attacchi gestiti dal codice, con vantaggio/svantaggio come in 5e.
4. **Immagini**: generare un'illustrazione per ogni nuova località, partendo dal tool `sposta_in`.
5. **Riassunti automatici**: a un certo punto far riassumere la storia al modello stesso, per diari molto lunghi.

## Test

I test girano in locale, senza modello, senza Ollama e senza toccare `saves/` (usano un modello finto e cartelle temporanee):

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Coprono regole e dadi, tool (compresi i flag che il master non può regalare), zone e orari, ciclo dell'agente, sessioni, utenti e login, API web con la sicurezza, e per ognuna delle tre avventure la coerenza dei dati e la raggiungibilità di tutti i finali.

