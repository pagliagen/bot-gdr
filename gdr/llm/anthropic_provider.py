"""Provider Anthropic Claude (SDK ufficiale `anthropic`)."""

from __future__ import annotations

import anthropic

from .base import ChiamataTool, LLMProvider, RispostaLLM


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 4096):
        # Se api_key è None l'SDK la cerca da solo (ANTHROPIC_API_KEY nell'ambiente).
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def chiama(self, system: str, messaggi: list[dict], tools: list[dict]) -> RispostaLLM:
        # Il nostro formato neutro è già quello di Anthropic: si passa com'è.
        risposta = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messaggi,
            tools=tools,
        )
        testo, chiamate = [], []
        for blocco in risposta.content:
            if blocco.type == "text":
                testo.append(blocco.text)
            elif blocco.type == "tool_use":
                chiamate.append(ChiamataTool(id=blocco.id, nome=blocco.name, argomenti=dict(blocco.input)))
            # Gli altri tipi (es. "thinking") non ci servono: li ignoriamo.

        if risposta.stop_reason == "refusal" and not chiamate and not testo:
            testo.append("(Il modello ha rifiutato di continuare questa scena. Prova a riformulare l'azione.)")
        return RispostaLLM(testo="".join(testo).strip(), chiamate_tool=chiamate)
