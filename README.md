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

## Avvio

```bash
python main.py              # riprende la partita salvata o ne crea una nuova
python main.py --nuova      # ignora il salvataggio
python main.py --debug      # mostra i tool chiamati, con argomenti ed esiti
```

Comandi in partita: `/scheda` `/mappa` `/diario` `/debug` `/salva` `/aiuto` `/esci`.
Il salvataggio è `saves/partita.json` (si aggiorna a ogni turno).

Per confrontare modelli Ollama sullo stesso scenario: `python scripts/prova_modelli.py qwen3.5:9b gemma4:12b`.

## Struttura

```
main.py                 punto d'ingresso
lore/                   mondo, luoghi, PNG e avventura (YAML)
prompts/master.md       system prompt del narratore (modificabile anche a partita in corso)
gdr/cli.py              interfaccia da terminale (unico file con input/print)
gdr/agent.py            il ciclo dell'agente
gdr/tools.py            schemi e implementazione dei tool
gdr/rules.py            regole pure (dadi, modificatori, prove)
gdr/memory.py           system prompt dinamico + compressione della cronologia
gdr/state.py, models.py stato della partita e salvataggio JSON
gdr/character_creation.py  creazione del personaggio
gdr/lore.py             carica e interroga la lore (luoghi, PNG, eventi, finali)
gdr/llm/                provider intercambiabili (Ollama; Anthropic opzionale)
```

## Il mondo: Acquaverde e l'avventura "Il Patto Sciolto"

La lore è in `lore/` (file YAML modificabili a mano):

| File | Contenuto |
|---|---|
| `mondo.yaml` | sintesi, storia, religioni, fazioni, regole del mondo, stile delle immagini |
| `luoghi.yaml` | 7 luoghi, coordinate sulla mappa, collegamenti con le ore di viaggio |
| `png.yaml` | 10 PNG con aspetto, scopo e segreto |
| `avventura.yaml` | cronologia di 7 giorni, flag, finali, prove suggerite |
| `immagini_statiche.md` | prompt per generare mappa, ritratti e luoghi |

**Il mondo avanza da solo.** Il codice tiene un orologio (giorno e ora). Quando il tempo passa (spostamenti con `sposta_in`, riposi con `avanza_tempo`), gli eventi della cronologia scattano al loro giorno **qualunque cosa faccia il giocatore**, e i tool li restituiscono al master. Il giocatore cambia come va a finire (i *flag*), non se gli eventi accadono. Il giorno 7 alle 20:00 il tempo si ferma e `valuta_finale` sceglie il finale in base ai flag.

**Il master non può "regalare" i progressi.** `imposta_flag` controlla in codice luogo, requisiti, oggetti e che l'ultima prova di abilità sia riuscita con statistica e CD giuste. **La geografia è vincolata**: si va solo tra luoghi collegati.

**La lore non sta tutta nel prompt.** Nel system prompt ci sono un riassunto, il luogo attuale con i PNG presenti, l'orologio e i flag. Per il resto il master usa `consulta_lore`. I segreti sono marcati come riservati.

## Come funziona il ciclo dell'agente

Il modello da solo può solo produrre testo. Con il *tool use* gli diciamo quali funzioni esistono (nome, descrizione, argomenti); a ogni risposta il modello può scegliere se **scrivere testo** oppure **chiedere di eseguire uno o più tool**. Il codice (`Agente._ciclo` in `gdr/agent.py`) fa così:

1. Costruisce il *system prompt*: istruzioni del master + stato attuale (scheda, luogo) + diario.
2. **Chiama il modello** con la cronologia e la lista dei tool.
3. Se la risposta contiene richieste di tool → li **esegue** (`Strumenti.esegui`) e aggiunge i risultati alla cronologia come messaggio `tool_result`.
4. **Torna al punto 1** (il modello legge i risultati e decide: altri tool o narrazione).
5. Se la risposta non contiene tool, è la **narrazione finale** e viene mostrata al giocatore.

Un tetto (`MAX_ITERAZIONI`) evita cicli infiniti. I tool non vanno mai in crash: se gli argomenti sono sbagliati restituiscono `{"ok": false, "errore": "..."}` e il modello può correggersi.

**Memoria.** I messaggi vecchi non si mandano per sempre: sopra `SOGLIA_MESSAGGI` si tengono solo gli ultimi `MESSAGGI_RECENTI` (tagliando sempre all'inizio di un turno, per non separare un tool dal suo risultato). Il filo della storia resta nel **diario** (tool `scrivi_diario`), che viene reinserito nel system prompt a ogni chiamata.

**Provider.** `gdr/llm/base.py` definisce un'interfaccia con un solo metodo, `chiama(system, messaggi, tools)`. Ogni provider traduce da/verso il proprio formato; l'agente non sa quale usa.

## Limiti noti

- I modelli piccoli (locali) a volte "dimenticano" di chiamare un tool e inventano l'esito: succede, ed è il motivo per cui conviene provare più modelli. Il prompt in `prompts/master.md` è il primo posto dove intervenire.
- Se un turno fallisce (rete, API) viene annullato, ma le modifiche già fatte dai tool nello stesso turno non vengono ripristinate.

## Idee per i prossimi passi

1. **Bot Telegram**: un nuovo file gemello di `cli.py` che chiama `agente.turno(testo)`; uno stato per chat.
2. **PNG con memoria**: un'entità per ogni PNG (atteggiamento, cosa sa del giocatore) con tool `parla_con_png` / `aggiorna_png`.
3. **Combattimento strutturato**: iniziativa, CA e attacchi gestiti dal codice, con vantaggio/svantaggio come in 5e.
4. **Immagini**: generare un'illustrazione per ogni nuova località, partendo dal tool `sposta_in`.
5. **Riassunti automatici**: a un certo punto far riassumere la storia al modello stesso, per diari molto lunghi.
