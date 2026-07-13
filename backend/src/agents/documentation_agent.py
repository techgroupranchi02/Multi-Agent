"""
Aikyam Multi-Agent Pipeline — Documentation Agent
Phase 13: Generate User Guide, API Docs, CHANGELOG, Runbook
Phase 14: Final summary and project closure
"""

from __future__ import annotations

import logging

from src.agents.base_agent import BaseAgent
from src.integrations.jira_client import get_jira_client
from src.integrations.slack_handler import get_slack_handler
from src.models.project_state import PhaseState, PipelineState

logger = logging.getLogger(__name__)

DOCS_PROMPT = """You are a Technical Writer. Generate professional documentation for this project.

Create the following documents:

## 1. User Guide (user_guide.md)
- Getting Started
- Features Overview
- Usage Examples
- FAQ

## 2. API Documentation (api_docs.md)
- Authentication
- Endpoints (with request/response examples)
- Error Codes
- Rate Limits

## 3. CHANGELOG (CHANGELOG.md)
- Version 1.0.0 — Initial Release
- List all features, improvements, and known issues

## 4. Deployment Runbook (runbook.md)
- Prerequisites
- Deployment Steps
- Rollback Procedure
- Monitoring & Alerts
- Troubleshooting Guide

Mark each document clearly with its filename."""


class DocumentationAgent(BaseAgent):
    """Phase 13: Documentation generation. Phase 14: Final summary."""

    agent_name = "documentation"
    agent_display_name = "Documentation Agent"
    agent_icon = "📚"

    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        if phase.phase_id == 13:
            return self._generate_docs(state, phase)
        elif phase.phase_id == 14:
            return self._finalize_project(state, phase)
        else:
            raise ValueError(f"DocumentationAgent doesn't handle phase {phase.phase_id}")

    def _generate_docs(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        """Phase 13: Generate all documentation."""
        phase.progress = 10
        phase.add_log("info", "Generating project documentation...")

        context_parts = []
        if state.prd:
            context_parts.append(f"PRD:\n{state.prd[:2000]}")
        if state.api_spec:
            context_parts.append(f"API Spec:\n{state.api_spec[:2000]}")
        if state.db_schema:
            context_parts.append(f"DB Schema:\n{state.db_schema[:1500]}")
        context = "\n\n".join(context_parts)

        messages = [
            {"role": "system", "content": DOCS_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {state.project_name}\n\n"
                    f"Context:\n{context}\n\n"
                    f"Production URL: {state.production_url or 'TBD'}\n"
                    f"Staging URL: {state.staging_url or 'TBD'}\n\n"
                    "Generate all four documentation files."
                ),
            },
        ]

        response = self.call_llm(phase, messages, "Generating documentation", max_tokens=6000)
        phase.progress = 70

        # Save as combined doc
        self.save_artifact(state, phase, "documentation", response.content)

        # Split and save individual docs
        docs = self._split_docs(response.content)
        for name, content in docs.items():
            self.save_artifact(state, phase, name, content)
            phase.add_log("info", f"  📄 {name}.md")

        phase.progress = 85

        # Log to Jira
        jira = get_jira_client()
        if jira._initialized and state.jira_epic_key:
            jira.add_comment(
                state.jira_epic_key,
                f"📚 Documentation Agent: Generated {len(docs)} documents",
            )

        phase.progress = 95
        return state

    def _finalize_project(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        """Phase 14: Project completion — summary and closure."""
        from datetime import datetime

        phase.progress = 20
        phase.add_log("info", "Preparing final project summary...")

        state.completed_at = datetime.utcnow()
        duration = "N/A"
        if state.started_at:
            delta = state.completed_at - state.started_at
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                duration = f"{hours}h {minutes}m"
            else:
                duration = f"{minutes}m {seconds}s"

        # Build summary
        summary = (
            f"# ✅ Project Complete: {state.project_name}\n\n"
            f"| Metric | Value |\n"
            f"|:-------|:------|\n"
            f"| Duration | {duration} |\n"
            f"| Total Tokens | {state.total_tokens:,} |\n"
            f"| Total Cost | ${state.total_cost_usd:.3f} |\n"
            f"| Jira Epic | {state.jira_epic_key or 'N/A'} |\n"
            f"| GitHub Repo | {state.git_repo or 'N/A'} |\n"
            f"| Staging URL | {state.staging_url or 'N/A'} |\n"
            f"| Production URL | {state.production_url or 'N/A'} |\n"
            f"| Security | {'PASS ✅' if state.security_passed else 'ISSUES ⚠️'} |\n"
            f"| Test Pass Rate | {state.test_results.get('pass_rate', 'N/A') if state.test_results else 'N/A'}% |\n"
        )

        self.save_artifact(state, phase, "project_summary", summary)
        phase.progress = 50

        # Send to Slack
        slack = get_slack_handler()
        slack.send_completion_summary(
            project_name=state.project_name,
            production_url=state.production_url,
            jira_epic_key=state.jira_epic_key,
            total_tokens=state.total_tokens,
            total_cost=state.total_cost_usd,
            duration=duration,
        )
        phase.add_log("success", "Final summary sent to Slack")
        phase.progress = 70

        # Close Jira epic
        jira = get_jira_client()
        if jira._initialized and state.jira_epic_key:
            jira.transition_issue(state.jira_epic_key, "Done")
            phase.add_log("info", f"Jira Epic {state.jira_epic_key} → Done")

        phase.progress = 95
        phase.add_log("success", f"🎉 Project '{state.project_name}' complete! Duration: {duration}")

        return state

    @staticmethod
    def _split_docs(content: str) -> dict[str, str]:
        """Split combined doc output by filename markers."""
        docs: dict[str, str] = {}
        current_name = None
        current_lines: list[str] = []

        name_map = {
            "user_guide": ["user guide", "user_guide"],
            "api_docs": ["api doc", "api_docs", "api reference"],
            "changelog": ["changelog", "change log"],
            "runbook": ["runbook", "deployment runbook"],
        }

        for line in content.split("\n"):
            lower = line.lower().strip()
            matched = None
            if lower.startswith("#"):
                for key, markers in name_map.items():
                    if any(m in lower for m in markers):
                        matched = key
                        break

            if matched and matched != current_name:
                if current_name and current_lines:
                    docs[current_name] = "\n".join(current_lines)
                current_name = matched
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_name and current_lines:
            docs[current_name] = "\n".join(current_lines)

        return docs
