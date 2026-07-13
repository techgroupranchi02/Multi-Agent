"""
Aikyam Multi-Agent Pipeline — Multi-LLM Provider Manager
Supports: Google Gemini, OpenAI, vLLM (DGX Spark), Ollama, Groq
Each agent can be configured to use a different provider.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import OpenAI
import httpx

from src.config import LLMProvider, Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    raw_response: Optional[Any] = None


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    base_url: Optional[str] = None
    api_key: str = "not-needed"
    model: str = ""
    max_input_tokens: int = 32768
    max_output_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = False
    temperature: float = 0.3
    # Cost per 1K tokens (approximate)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


class LLMProviderManager:
    """
    Manages multiple LLM providers and routes requests to the
    configured provider for each agent.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._clients: dict[str, OpenAI] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Set up all configured providers."""

        # ── Google Gemini (via OpenAI-compatible endpoint) ──
        if self.settings.gemini_api_key:
            self._configs["gemini"] = ProviderConfig(
                name="Google Gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=self.settings.gemini_api_key,
                model=self.settings.gemini_model,
                max_input_tokens=1048576,
                max_output_tokens=65536,
                supports_tools=True,
                supports_vision=True,
                cost_per_1k_input=0.00125,
                cost_per_1k_output=0.005,
            )
            self._clients["gemini"] = OpenAI(
                api_key=self.settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=httpx.Timeout(300.0, connect=30.0),
            )
            logger.info("✓ Gemini provider initialized (model: %s)", self.settings.gemini_model)

        # ── OpenAI ──
        if self.settings.openai_api_key:
            self._configs["openai"] = ProviderConfig(
                name="OpenAI",
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_model,
                max_input_tokens=128000,
                max_output_tokens=16384,
                supports_tools=True,
                supports_vision=True,
                cost_per_1k_input=0.0025,
                cost_per_1k_output=0.01,
            )
            self._clients["openai"] = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=httpx.Timeout(300.0, connect=30.0),
            )
            logger.info("✓ OpenAI provider initialized (model: %s)", self.settings.openai_model)

        # ── vLLM (DGX Spark — Qwen 2.5 72B Instruct AWQ) ──
        self._configs["vllm"] = ProviderConfig(
            name="vLLM (DGX Spark)",
            base_url=self.settings.vllm_base_url,
            api_key=self.settings.vllm_api_key,
            model=self.settings.vllm_model,
            max_input_tokens=32768,
            max_output_tokens=4096,
            supports_tools=True,
            supports_vision=False,
            cost_per_1k_input=0.0,  # Self-hosted = free
            cost_per_1k_output=0.0,
        )
        self._clients["vllm"] = OpenAI(
            api_key=self.settings.vllm_api_key,
            base_url=self.settings.vllm_base_url,
            timeout=httpx.Timeout(300.0, connect=30.0),
        )
        logger.info(
            "✓ vLLM provider initialized (model: %s, url: %s)",
            self.settings.vllm_model,
            self.settings.vllm_base_url,
        )

        # ── Ollama (OpenAI-compatible) ──
        # Detect Qwen3 thinking models — they need larger output budget
        ollama_model_lower = self.settings.ollama_model.lower()
        is_thinking_model = "qwen3" in ollama_model_lower or "qwq" in ollama_model_lower
        ollama_max_output = 16384 if is_thinking_model else 8192

        self._configs["ollama"] = ProviderConfig(
            name="Ollama (Local)",
            base_url=f"{self.settings.ollama_base_url}/v1",
            api_key="ollama",
            model=self.settings.ollama_model,
            max_input_tokens=32768,
            max_output_tokens=ollama_max_output,
            supports_tools=True,
            supports_vision=False,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )
        self._clients["ollama"] = OpenAI(
            api_key="ollama",
            base_url=f"{self.settings.ollama_base_url}/v1",
            timeout=httpx.Timeout(600.0, connect=30.0),  # Longer timeout for local models
        )
        if is_thinking_model:
            logger.info(
                "✓ Ollama provider initialized (model: %s) — thinking model detected, "
                "will use /no_think to disable extended reasoning",
                self.settings.ollama_model,
            )
        else:
            logger.info("✓ Ollama provider initialized (model: %s)", self.settings.ollama_model)

        # ── Groq ──
        if self.settings.groq_api_key:
            self._configs["groq"] = ProviderConfig(
                name="Groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=self.settings.groq_api_key,
                model=self.settings.groq_model,
                max_input_tokens=131072,
                max_output_tokens=32768,
                supports_tools=True,
                supports_vision=False,
                cost_per_1k_input=0.00059,
                cost_per_1k_output=0.00079,
            )
            self._clients["groq"] = OpenAI(
                api_key=self.settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=httpx.Timeout(300.0, connect=30.0),
            )
            logger.info("✓ Groq provider initialized (model: %s)", self.settings.groq_model)

    def get_client_for_agent(self, agent_name: str) -> tuple[OpenAI, ProviderConfig]:
        """
        Get the OpenAI-compatible client and config for a specific agent.
        Falls back to default provider if configured one is unavailable.
        """
        provider = self.settings.get_agent_llm_provider(agent_name)
        provider_key = provider.value

        if provider_key not in self._clients:
            logger.warning(
                "Provider '%s' not available for agent '%s', falling back to default",
                provider_key, agent_name,
            )
            provider_key = self.settings.default_llm_provider.value

        if provider_key not in self._clients:
            # Last resort: use whatever is available
            available = list(self._clients.keys())
            if not available:
                raise RuntimeError("No LLM providers configured! Check your .env file.")
            provider_key = available[0]
            logger.warning("Using fallback provider: %s", provider_key)

        return self._clients[provider_key], self._configs[provider_key]

    def chat(
        self,
        agent_name: str,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        """
        Send a chat completion request using the provider configured for this agent.
        All providers use the OpenAI-compatible API format.
        """
        client, config = self.get_client_for_agent(agent_name)

        # For Qwen3 thinking models on Ollama, disable thinking mode by
        # appending /no_think to the last user message. This prevents the
        # model from spending minutes on internal chain-of-thought reasoning
        # and dramatically speeds up responses.
        is_ollama_thinking = (
            "ollama" in config.name.lower()
            and ("qwen3" in config.model.lower() or "qwq" in config.model.lower())
        )

        effective_messages = messages
        if is_ollama_thinking:
            effective_messages = list(messages)  # shallow copy
            # Append /no_think to the last user message
            for i in range(len(effective_messages) - 1, -1, -1):
                if effective_messages[i].get("role") == "user":
                    effective_messages[i] = {
                        **effective_messages[i],
                        "content": effective_messages[i]["content"] + " /no_think",
                    }
                    break
            logger.info(
                "[%s] Qwen3 thinking model detected — appended /no_think for faster response",
                agent_name,
            )

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": effective_messages,
            "temperature": temperature if temperature is not None else config.temperature,
        }

        if max_tokens:
            kwargs["max_tokens"] = min(max_tokens, config.max_output_tokens)
        else:
            kwargs["max_tokens"] = config.max_output_tokens

        if tools and config.supports_tools:
            kwargs["tools"] = tools

        if response_format:
            kwargs["response_format"] = response_format

        start = time.time()
        try:
            response = client.chat.completions.create(**kwargs)
            latency = time.time() - start

            choice = response.choices[0]
            content = choice.message.content or ""
            usage = response.usage

            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else 0

            cost = (
                (prompt_tokens / 1000) * config.cost_per_1k_input
                + (completion_tokens / 1000) * config.cost_per_1k_output
            )

            result = LLMResponse(
                content=content,
                model=config.model,
                provider=config.name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                latency_seconds=round(latency, 2),
                raw_response=response,
            )

            logger.info(
                "[%s] %s → %s | tokens: %d | cost: $%.4f | latency: %.1fs",
                agent_name, config.name, config.model,
                total_tokens, cost, latency,
            )

            return result

        except Exception as e:
            latency = time.time() - start
            logger.error(
                "[%s] %s → %s FAILED after %.1fs: %s",
                agent_name, config.name, config.model, latency, str(e),
            )
            raise

    def list_providers(self) -> list[dict[str, Any]]:
        """List all configured providers and their status."""
        result = []
        for key, config in self._configs.items():
            result.append({
                "key": key,
                "name": config.name,
                "model": config.model,
                "base_url": config.base_url,
                "supports_tools": config.supports_tools,
                "supports_vision": config.supports_vision,
                "available": key in self._clients,
            })
        return result

    def health_check(self, provider_key: str) -> dict[str, Any]:
        """Quick health check for a specific provider."""
        if provider_key not in self._clients:
            return {"provider": provider_key, "status": "not_configured"}

        client = self._clients[provider_key]
        config = self._configs[provider_key]

        try:
            start = time.time()
            response = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            latency = time.time() - start
            return {
                "provider": provider_key,
                "name": config.name,
                "model": config.model,
                "status": "healthy",
                "latency_ms": round(latency * 1000),
            }
        except Exception as e:
            return {
                "provider": provider_key,
                "name": config.name,
                "status": "error",
                "error": str(e),
            }


# ── Singleton ──
_llm_manager: Optional[LLMProviderManager] = None


def get_llm_manager() -> LLMProviderManager:
    """Get the singleton LLM provider manager."""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMProviderManager()
    return _llm_manager
