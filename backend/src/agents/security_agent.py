"""
Aikyam Multi-Agent Pipeline — Security Scan Agent
Phase 9: SAST analysis + dependency audit + LLM security review.
"""

from __future__ import annotations

import logging
import os

from src.agents.base_agent import BaseAgent
from src.models.project_state import PhaseState, PipelineState

logger = logging.getLogger(__name__)

SECURITY_PROMPT = """You are a Senior Application Security Engineer specializing in SAST and code auditing.
Review the provided codebase and generate a security assessment report.

Check for:
1. **OWASP Top 10** vulnerabilities (injection, XSS, CSRF, broken auth, etc.)
2. **Hardcoded secrets** (API keys, passwords, tokens in source code)
3. **Dependency vulnerabilities** (known CVEs in libraries)
4. **Input validation** gaps
5. **Authentication/Authorization** weaknesses
6. **Data exposure** risks (PII leakage, verbose error messages)
7. **Cryptographic** issues (weak hashing, insecure random)

Output format:
## Security Assessment Summary
Brief overall risk level: LOW / MEDIUM / HIGH / CRITICAL

## Vulnerabilities Found
For each finding:
- **[SEVERITY]** CRITICAL / HIGH / MEDIUM / LOW
- **Type**: OWASP category
- **Location**: file and area
- **Description**: what's wrong
- **Remediation**: how to fix

## Dependency Audit
List any known vulnerable dependencies.

## Verdict
- `SECURITY: PASS` — if no CRITICAL or HIGH issues found
- `SECURITY: FAIL` — if CRITICAL or HIGH issues exist (list blocking issues)"""


class SecurityAgent(BaseAgent):
    """Phase 9: Security scan and vulnerability assessment."""

    agent_name = "security"
    agent_display_name = "Security Scan Agent"
    agent_icon = "🔒"

    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        phase.progress = 10
        phase.add_log("info", "Starting security scan...")

        # Collect code
        code_content = self._collect_code(state)

        messages = [
            {"role": "system", "content": SECURITY_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {state.project_name}\n\n"
                    f"Code to audit:\n{code_content}\n\n"
                    "Perform a comprehensive security assessment."
                ),
            },
        ]

        phase.progress = 20
        response = self.call_llm(phase, messages, "Security vulnerability analysis")
        phase.progress = 75

        report = response.content
        self.save_artifact(state, phase, "security_report", report)

        # Parse verdict
        if "SECURITY: PASS" in report.upper():
            state.security_passed = True
            phase.add_log("success", "Security scan: PASS ✅ — No critical issues found")
        else:
            state.security_passed = False
            phase.add_log("warn", "Security scan: ISSUES FOUND — review recommended")

        state.security_report = {
            "verdict": "PASS" if state.security_passed else "FAIL",
            "report": report,
        }

        phase.progress = 95
        return state

    def _collect_code(self, state: PipelineState) -> str:
        """Collect code files for security review."""
        parts = []
        for filepath in state.code_files:
            full_path = os.path.join(state.workspace_path, filepath)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    parts.append(f"### {filepath}\n```\n{content}\n```\n")
                except Exception:
                    pass

        combined = "\n".join(parts)
        if len(combined) > 15000:
            combined = combined[:15000] + "\n\n... (truncated)"
        return combined or "No code files available for review."
