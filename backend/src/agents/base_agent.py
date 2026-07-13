"""
Aikyam Multi-Agent Pipeline — Base Agent
Abstract base class for all agents with logging, cost tracking,
and LLM provider integration.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from src.integrations.llm_provider import LLMResponse, get_llm_manager
from src.models.project_state import PhaseLog, PhaseState, PipelineState

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all pipeline agents.
    Provides:
    - LLM calling (routed to the correct provider)
    - Phase state management (logs, progress, status)
    - Cost and token tracking
    """

    # Subclasses must set these
    agent_name: str = "base"
    agent_display_name: str = "Base Agent"
    agent_icon: str = "🤖"

    def __init__(self):
        self.llm = get_llm_manager()

    # ── Abstract method: subclasses implement the actual work ──
    @abstractmethod
    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        """
        Execute this agent's work for the given phase.
        Must update state and phase, then return the updated state.
        """
        ...

    # ── Runner: wraps execute with logging and error handling ──
    def run(self, state: PipelineState, phase_id: int) -> PipelineState:
        """
        Run this agent with full lifecycle management:
        1. Mark phase as running
        2. Execute agent logic
        3. Mark phase as success/error
        4. Track costs
        """
        phase = state.get_phase(phase_id)
        phase.status = "running"
        phase.started_at = datetime.utcnow()
        phase.progress = 5
        phase.add_log("info", f"{self.agent_display_name} starting...")

        logger.info("[Phase %d] %s %s starting", phase_id, self.agent_icon, self.agent_display_name)

        try:
            state = self.execute(state, phase)

            # Mark success
            phase.status = "success"
            phase.progress = 100
            phase.completed_at = datetime.utcnow()
            phase.duration_seconds = (phase.completed_at - phase.started_at).total_seconds()
            phase.add_log(
                "success",
                f"✓ Phase complete — tokens: {phase.tokens_used:,} | cost: ${phase.cost_usd:.4f}",
            )

            # Update pipeline totals
            state.total_tokens += phase.tokens_used
            state.total_cost_usd += phase.cost_usd

            logger.info(
                "[Phase %d] %s completed in %s (tokens: %d, cost: $%.4f)",
                phase_id, self.agent_display_name,
                phase.duration_display, phase.tokens_used, phase.cost_usd,
            )

        except Exception as e:
            phase.status = "error"
            phase.error_message = str(e)
            phase.completed_at = datetime.utcnow()
            if phase.started_at:
                phase.duration_seconds = (phase.completed_at - phase.started_at).total_seconds()
            phase.add_log("error", f"Phase failed: {str(e)}")
            logger.exception("[Phase %d] %s FAILED: %s", phase_id, self.agent_display_name, e)

        return state

    # ── LLM Helper: call LLM with proper tracking ──
    def call_llm(
        self,
        phase: PhaseState,
        messages: list[dict[str, str]],
        task_description: str = "LLM call",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        """
        Call the LLM configured for this agent and track costs.
        """
        phase.add_log("info", f"LLM: {task_description}...")

        response = self.llm.chat(
            agent_name=self.agent_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        # Track
        phase.tokens_used += response.total_tokens
        phase.cost_usd += response.cost_usd

        phase.add_log(
            "info",
            f"LLM response received ({response.provider} / {response.model}) — "
            f"{response.total_tokens} tokens, ${response.cost_usd:.4f}, {response.latency_seconds}s",
        )

        return response

    # ── File helper ──
    def save_artifact(
        self,
        state: PipelineState,
        phase: PhaseState,
        name: str,
        content: str,
        extension: str = "md",
    ) -> str:
        """Save an artifact to the workspace and track it. Also publishes to Google Docs."""
        import os
        state_dir = os.path.join(state.workspace_path, ".state")
        os.makedirs(state_dir, exist_ok=True)

        filename = f"{name}.{extension}"
        filepath = os.path.join(state_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        phase.output_artifacts[name] = filepath
        phase.add_log("info", f"Saved artifact: {filename}")
        logger.info("Saved artifact %s → %s", name, filepath)

        # Skip publishing PRD and Open Questions directly in save_artifact
        # (PRD is published versioned via review loop; Open Questions are replaced by the questionnaire)
        if name in ("prd", "open_questions"):
            return filepath

        # Auto-publish to Google Docs for document artifacts
        if extension in ("md", "txt", "yaml", "sql"):
            try:
                from src.integrations.google_docs_client import get_google_docs_client
                gdocs = get_google_docs_client()
                
                # Map artifact names to user-friendly Tab Titles
                tab_title_map = {
                    "pdd": "PDD",
                    "execution_plan": "Execution Plan",
                    "api_spec": "API Spec",
                    "db_schema": "Database",
                }
                
                if name in tab_title_map:
                    tab_title = tab_title_map[name]
                    doc_url = gdocs.create_or_update_tab(
                        project_id=state.project_id,
                        project_name=state.project_name,
                        tab_title=tab_title,
                        content=content,
                        workspace_path=state.workspace_path,
                    )
                else:
                    doc_url = gdocs.create_doc(
                        title=filename,
                        content=content,
                        project_name=state.project_name,
                        artifact_type=name,
                    )
                
                if doc_url:
                    phase.output_artifacts[f"{name}_gdoc_url"] = doc_url
                    phase.add_log("info", f"📄 Published to Google Docs tab: {doc_url}")
                    logger.info("Published %s to Google Docs: %s", name, doc_url)
            except Exception as e:
                logger.warning("Google Docs publish failed for %s: %s", name, e)
                phase.add_log("warn", f"Google Docs publish failed: {e}")

        return filepath
