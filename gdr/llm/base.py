"""Interfaccia comune a tutti i provider LLM.

Il resto del programma parla SOLO con questa interfaccia e con questi tipi
neutri. Per cambiare provider (Anthropic -> Ollama -> altro) si scrive una
nuova classe che traduce da/verso il formato del provider: l'agente non cambia.

Formato neutro dei messaggi (coincide con quello di Anthropic, il più semplice):
    {"role": "user",      "content": "testo"}
    {"role": "assistant", "content": [{"type": "text", "text": "..."},
                                      {"type": "tool_use", "id": "x", "name": "tira_dadi", "input": {...}}]}
    {"role": "user",      "content": [{"type": "tool_result", "tool_use_id": "x", "content": "json...", "is_error": False}]}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChiamataTool:
    """Una richiesta di esecuzione tool fatta dal modello."""

    id: str
    nome: str
    argomenti: dict[str, Any]


@dataclass
class RispostaLLM:
    testo: str = ""  # eventuale testo narrativo
    chiamate_tool: list[ChiamataTool] = field(default_factory=list)  # tool richiesti (vuoto = risposta finale)


class LLMProvider(ABC):
    @abstractmethod
    def chiama(self, system: str, messaggi: list[dict], tools: list[dict]) -> RispostaLLM:
        """Una singola chiamata al modello. `tools` è la lista di TOOL_SCHEMAS."""
