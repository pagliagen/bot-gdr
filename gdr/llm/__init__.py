"""Factory dei provider: l'unico punto che sa quale classe usare."""

from __future__ import annotations

from ..config import Config
from .base import ChiamataTool, LLMProvider, RispostaLLM

__all__ = ["ChiamataTool", "LLMProvider", "RispostaLLM", "crea_provider"]


def crea_provider(cfg: Config) -> LLMProvider:
    # Import "pigri": serve installato solo l'SDK del provider scelto.
    if cfg.provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=cfg.anthropic_model, api_key=cfg.anthropic_api_key)
    if cfg.provider == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider(model=cfg.ollama_model, host=cfg.ollama_host, num_ctx=cfg.ollama_num_ctx)
    raise ValueError(f"LLM_PROVIDER '{cfg.provider}' sconosciuto. Valori ammessi: anthropic, ollama.")
