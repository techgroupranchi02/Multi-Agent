"""
Aikyam Multi-Agent Pipeline — Configuration
Loads environment variables and provides typed settings.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional, Any

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Load .env from backend root
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OPENAI = "openai"
    VLLM = "vllm"
    OLLAMA = "ollama"
    GROQ = "groq"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── App ──
    app_env: str = Field(default="development")
    app_port: int = Field(default=8000)
    app_host: str = Field(default="0.0.0.0")
    log_level: str = Field(default="INFO")

    # ── LLM: Gemini ──
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-pro")

    # ── LLM: OpenAI ──
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o")

    # ── LLM: vLLM (DGX Spark — Qwen 2.5 72B) ──
    vllm_base_url: str = Field(default="https://api-32b.aikyamarea51.in/v1")
    vllm_model: str = Field(default="Qwen/Qwen2.5-72B-Instruct-AWQ")
    vllm_api_key: str = Field(default="not-needed")

    # ── LLM: Ollama ──
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1:70b")

    # ── LLM: Groq ──
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.1-70b-versatile")

    # ── Per-Agent LLM Assignment ──
    default_llm_provider: LLMProvider = Field(default=LLMProvider.GEMINI)
    requirements_agent_llm: LLMProvider = Field(default=LLMProvider.GEMINI)
    developer_agent_llm: LLMProvider = Field(default=LLMProvider.VLLM)
    code_review_agent_llm: LLMProvider = Field(default=LLMProvider.GEMINI)
    qa_agent_llm: LLMProvider = Field(default=LLMProvider.VLLM)
    security_agent_llm: LLMProvider = Field(default=LLMProvider.GEMINI)
    deployment_agent_llm: LLMProvider = Field(default=LLMProvider.VLLM)
    documentation_agent_llm: LLMProvider = Field(default=LLMProvider.VLLM)

    # ── Slack ──
    slack_bot_token: str = Field(default="")
    slack_app_token: str = Field(default="")
    slack_channel_id: str = Field(default="")
    slack_signing_secret: str = Field(default="")

    # ── Jira ──
    jira_url: str = Field(default="https://freecomerscore.atlassian.net")
    jira_username: str = Field(default="")
    jira_api_token: str = Field(default="")
    jira_project_key: str = Field(default="MAT")

    # ── GitHub ──
    github_token: str = Field(default="")
    github_org: str = Field(default="aikyam")
    github_default_branch: str = Field(default="main")

    # ── Database ──
    database_url: str = Field(default="postgresql+asyncpg://postgres:password@localhost:5432/aikyam")
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── Docker ──
    docker_host: str = Field(default="unix:///var/run/docker.sock")

    # ── Deployment ──
    deploy_host: str = Field(default="")
    deploy_user: str = Field(default="deploy")
    deploy_key_path: str = Field(default="~/.ssh/deploy_key")

    # ── Google Docs ──
    google_service_account_key_path: str = Field(default="./google_service_account.json")
    google_docs_share_email: str = Field(default="")
    google_docs_folder_id: str = Field(default="")

    # ── RAG Knowledge Base ──
    rag_collection_name: str = Field(default="aikyam_prd")
    rag_persist_dir: str = Field(default="./rag_data")
    rag_chunk_size: int = Field(default=1000)
    rag_chunk_overlap: int = Field(default=200)

    # ── Review Tokens ──
    review_token_secret: str = Field(default="aikyam-review-secret-change-me")
    review_token_expiry_hours: int = Field(default=72)

    # ── Paths ──
    workspace_dir: Path = Field(default=_backend_dir / "workspace")
    prompts_dir: Path = Field(default=_backend_dir / "prompts")

    class Config:
        env_file = str(_backend_dir / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

    @field_validator(
        "default_llm_provider",
        "requirements_agent_llm",
        "developer_agent_llm",
        "code_review_agent_llm",
        "qa_agent_llm",
        "security_agent_llm",
        "deployment_agent_llm",
        "documentation_agent_llm",
        mode="before"
    )
    @classmethod
    def convert_to_lowercase_provider(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    def get_agent_llm_provider(self, agent_name: str) -> LLMProvider:
        """Get the configured LLM provider for a specific agent."""
        mapping = {
            "requirements": self.requirements_agent_llm,
            "developer": self.developer_agent_llm,
            "code_review": self.code_review_agent_llm,
            "qa": self.qa_agent_llm,
            "security": self.security_agent_llm,
            "deployment": self.deployment_agent_llm,
            "documentation": self.documentation_agent_llm,
        }
        return mapping.get(agent_name, self.default_llm_provider)


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
