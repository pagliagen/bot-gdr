"""Provider Ollama (modelli locali). Traduce dal formato neutro a quello di Ollama."""

from __future__ import annotations

import json

import ollama

from .base import ChiamataTool, LLMProvider, RispostaLLM


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, host: str = "http://localhost:11434", num_ctx: int = 16384):
        self.client = ollama.Client(host=host)
        self.model = model
        self.num_ctx = num_ctx

    @staticmethod
    def _converti_tools(tools: list[dict]) -> list[dict]:
        # Ollama usa lo stile "function" di OpenAI; cambia solo il nome del campo dello schema.
        return [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]

    @staticmethod
    def _converti_messaggi(system: str, messaggi: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        nomi_tool: dict[str, str] = {}  # id -> nome, serve per etichettare i risultati
        for m in messaggi:
            contenuto = m["content"]
            if isinstance(contenuto, str):
                out.append({"role": m["role"], "content": contenuto})
                continue
            if m["role"] == "assistant":
                testo = "".join(b["text"] for b in contenuto if b["type"] == "text")
                chiamate = []
                for b in contenuto:
                    if b["type"] == "tool_use":
                        nomi_tool[b["id"]] = b["name"]
                        chiamate.append({"function": {"name": b["name"], "arguments": b["input"]}})
                msg = {"role": "assistant", "content": testo}
                if chiamate:
                    msg["tool_calls"] = chiamate
                out.append(msg)
            else:  # utente con tool_result: Ollama vuole un messaggio "tool" per ciascuno
                for b in contenuto:
                    if b["type"] == "tool_result":
                        out.append({"role": "tool", "tool_name": nomi_tool.get(b["tool_use_id"], ""), "content": b["content"]})
        return out

    def chiama(self, system: str, messaggi: list[dict], tools: list[dict]) -> RispostaLLM:
        risposta = self.client.chat(
            model=self.model,
            messages=self._converti_messaggi(system, messaggi),
            tools=self._converti_tools(tools),
            options={"num_ctx": self.num_ctx},
        )
        msg = risposta.message
        # `msg.thinking` (il ragionamento dei modelli "thinking") viene ignorato di proposito.
        chiamate = [
            # Ollama non assegna id alle chiamate: ne inventiamo uno univoco.
            ChiamataTool(id=f"ollama_{i}_{tc.function.name}", nome=tc.function.name, argomenti=dict(tc.function.arguments or {}))
            for i, tc in enumerate(msg.tool_calls or [])
        ]
        return RispostaLLM(testo=(msg.content or "").strip(), chiamate_tool=chiamate)
