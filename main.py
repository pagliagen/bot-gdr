"""Punto d'ingresso: python main.py [--web] [--debug] [--nuova]"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Master di gioco di ruolo con LLM")
    parser.add_argument("--web", action="store_true", help="avvia l'interfaccia web locale invece del terminale")
    parser.add_argument("--porta", type=int, default=8000, help="porta dell'interfaccia web (default 8000)")
    parser.add_argument("--debug", action="store_true", help="(terminale) mostra i tool chiamati e i loro esiti")
    parser.add_argument("--nuova", action="store_true", help="(terminale) ignora il salvataggio e inizia una nuova partita")
    parser.add_argument("--provider", choices=["anthropic", "ollama"], help="sovrascrive LLM_PROVIDER del .env")
    args = parser.parse_args()

    from dataclasses import replace

    from gdr.config import carica_config

    cfg = carica_config()
    if args.provider:
        cfg = replace(cfg, provider=args.provider)

    if args.web:
        import threading
        import webbrowser

        import uvicorn

        from gdr.web import crea_app

        url = f"http://127.0.0.1:{args.porta}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        print(f"Interfaccia web su {url}  (Ctrl+C per fermare)")
        uvicorn.run(crea_app(cfg), host="127.0.0.1", port=args.porta, log_level="warning")
    else:
        from gdr.cli import avvia

        avvia(cfg, nuova=args.nuova, debug=args.debug)


if __name__ == "__main__":
    main()
