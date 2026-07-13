"""
Aikyam Multi-Agent Pipeline — Code Review Agent
Phase 7: Static analysis + LLM-powered code review.
"""

from __future__ import annotations

import logging
import os

from src.agents.base_agent import BaseAgent
from src.models.project_state import PhaseState, PipelineState

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """You are a Strict Code Reviewer and Security Auditor at a FAANG-level company.
Review the provided codebase carefully and provide a detailed verdict.

Check for:
1. **Code Quality**: SOLID principles, DRY, clean code, proper naming
2. **Security**: SQL injection, XSS, hardcoded secrets, missing input validation, auth issues
3. **Performance**: N+1 queries, memory leaks, inefficient algorithms
4. **Error Handling**: Missing try/catch, unhandled edge cases, poor error messages
5. **Testing**: Test coverage adequacy, missing edge case tests
6. **Architecture**: Separation of concerns, dependency management

Output your review as:
## Summary
One paragraph overall assessment.

## Issues Found
For each issue:
- **[SEVERITY]** (CRITICAL / HIGH / MEDIUM / LOW)
- **File**: filename
- **Line/Area**: description
- **Issue**: what's wrong
- **Fix**: how to fix it

## Verdict
State exactly one of:
- `VERDICT: APPROVED` — if the code is production-ready
- `VERDICT: CHANGES_REQUESTED` — if changes are needed (list required changes)

Be strict but fair. Minor style issues alone should not block approval."""


class CodeReviewAgent(BaseAgent):
    """Phase 7: Reviews generated code for quality, security, and architecture."""

    agent_name = "code_review"
    agent_display_name = "Code Review Agent"
    agent_icon = "🔍"

    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        phase.progress = 10
        phase.add_log("info", "Starting code review...")

        # Collect code files from workspace
        code_content = self._collect_code(state)
        if not code_content:
            phase.add_log("warn", "No code files found to review")
            state.review_verdict = "APPROVED"
            return state

        phase.add_log("info", f"Reviewing {len(state.code_files)} files...")
        phase.progress = 20

        # LLM review
        messages = [
            {"role": "system", "content": REVIEW_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {state.project_name}\n\n"
                    f"Code to review:\n{code_content}\n\n"
                    "Provide your detailed code review with a verdict."
                ),
            },
        ]

        response = self.call_llm(phase, messages, "LLM code review analysis")
        phase.progress = 75

        # Parse verdict
        review_text = response.content
        self.save_artifact(state, phase, "code_review", review_text)

        if "VERDICT: APPROVED" in review_text.upper():
            state.review_verdict = "APPROVED"
            phase.add_log("success", "Code review: APPROVED ✅")
        elif "VERDICT: CHANGES_REQUESTED" in review_text.upper():
            state.review_verdict = "CHANGES_REQUESTED"
            state.review_feedback = review_text
            state.review_attempt_count += 1
            phase.add_log("warn", f"Code review: CHANGES REQUESTED (attempt {state.review_attempt_count}/3)")
        else:
            # Default to approved if verdict unclear
            state.review_verdict = "APPROVED"
            phase.add_log("info", "No clear verdict found — defaulting to APPROVED")

        phase.progress = 95
        return state

    def _collect_code(self, state: PipelineState) -> str:
        """Collect all code files from workspace into a single string."""
        parts = []
        for filepath in state.code_files:
            full_path = os.path.join(state.workspace_path, filepath)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    parts.append(f"### File: {filepath}\n```\n{content}\n```\n")
                except Exception:
                    pass

        # Limit total size to avoid token limits
        combined = "\n".join(parts)
        if len(combined) > 20000:
            combined = combined[:20000] + "\n\n... (truncated for review)"
        return combined
