"""
Aikyam Multi-Agent Pipeline — Developer Agent
Phase 6: Generates source code + unit tests, commits to Git.
"""

from __future__ import annotations

import logging

from src.agents.base_agent import BaseAgent
from src.integrations.github_client import get_github_client
from src.integrations.jira_client import get_jira_client
from src.models.project_state import PhaseState, PipelineState

logger = logging.getLogger(__name__)

DEVELOPER_PROMPT = """You are a Senior Full-Stack Software Engineer. Your job is to implement
a complete, production-ready codebase based on the provided technical specifications.

Guidelines:
1. Write clean, modular, well-documented code following best practices (SOLID, DRY)
2. Follow the architecture, API design, and DB schema exactly as specified
3. Include proper error handling, input validation, and logging
4. Write comprehensive unit tests alongside the code (aim for >80% coverage)
5. Use conventional commit messages (feat:, fix:, test:, docs:)
6. Include all dependency configuration files (requirements.txt / package.json)

Output your code as a series of files. For each file, use this format:
```filepath: path/to/file.py
<file content>
```

Start with the project setup, then core logic, then tests."""


class DeveloperAgent(BaseAgent):
    """Phase 6: Code generation + unit tests + Git operations."""

    agent_name = "developer"
    agent_display_name = "Developer Agent"
    agent_icon = "👨‍💻"

    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        phase.progress = 5
        phase.add_log("info", "Starting code generation...")

        # Build context from design artifacts
        design_context = self._build_context(state)

        # If this is a retry, include review feedback
        retry_context = ""
        if state.review_feedback and state.review_attempt_count > 0:
            retry_context = (
                f"\n\n⚠️ IMPORTANT — This is retry #{state.review_attempt_count}. "
                f"The code reviewer provided this feedback:\n"
                f"---\n{state.review_feedback}\n---\n"
                "Please address ALL the feedback in your updated code."
            )
            phase.add_log("warn", f"Retry #{state.review_attempt_count} — addressing review feedback")

        messages = [
            {"role": "system", "content": DEVELOPER_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {state.project_name}\n\n"
                    f"Technical Specifications:\n{design_context}\n"
                    f"{retry_context}\n\n"
                    "Generate the complete codebase with unit tests."
                ),
            },
        ]

        phase.progress = 15
        response = self.call_llm(
            phase, messages,
            "Generating source code and unit tests",
            max_tokens=8000,
        )
        phase.progress = 60

        # Parse file outputs
        files = self._parse_code_files(response.content)
        state.code_files = list(files.keys())
        phase.add_log("info", f"Generated {len(files)} files")

        # Save files to workspace
        import os
        src_dir = os.path.join(state.workspace_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        for filepath, content in files.items():
            full_path = os.path.join(state.workspace_path, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            phase.add_log("info", f"  📄 {filepath}")

        phase.progress = 75

        # Git operations
        github = get_github_client()
        if github._initialized and state.git_repo:
            branch_name = f"feature/{state.jira_epic_key or 'dev'}-{github.slugify(state.project_name)}"
            state.git_branch = branch_name

            github.create_branch(state.git_repo, branch_name)
            for filepath, content in files.items():
                github.commit_file(
                    state.git_repo, branch_name, filepath, content,
                    f"feat: {filepath.split('/')[-1]}",
                )
            phase.add_log("success", f"Code committed to branch: {branch_name}")
        else:
            phase.add_log("info", "GitHub not configured — code saved locally only")

        phase.progress = 85

        # Log work in Jira
        jira = get_jira_client()
        if jira._initialized and state.jira_epic_key:
            jira.add_comment(
                state.jira_epic_key,
                f"🤖 Developer Agent completed code generation.\n"
                f"Files: {len(files)} | Branch: {state.git_branch or 'local'}",
            )

        phase.progress = 95
        phase.add_log("success", f"Development complete — {len(files)} files generated")

        return state

    def _build_context(self, state: PipelineState) -> str:
        """Build context string from available design artifacts."""
        parts = []
        if state.api_spec:
            parts.append(f"## API Specification\n{state.api_spec[:3000]}")
        if state.db_schema:
            parts.append(f"## Database Schema\n{state.db_schema[:2000]}")
        if state.pdd:
            parts.append(f"## Product Design\n{state.pdd[:3000]}")
        if state.execution_plan:
            parts.append(f"## Execution Plan\n{state.execution_plan[:2000]}")
        if not parts and state.prd:
            parts.append(f"## PRD\n{state.prd[:4000]}")
        return "\n\n".join(parts)

    @staticmethod
    def _parse_code_files(content: str) -> dict[str, str]:
        """Parse LLM output into filename->content pairs."""
        files: dict[str, str] = {}
        current_file = None
        current_lines: list[str] = []
        in_code_block = False

        for line in content.split("\n"):
            if line.strip().startswith("```filepath:") or line.strip().startswith("```file:"):
                # Start of a new file
                if current_file and current_lines:
                    files[current_file] = "\n".join(current_lines)
                filepath = line.split(":", 1)[1].strip().rstrip("`")
                current_file = filepath
                current_lines = []
                in_code_block = True
            elif line.strip() == "```" and in_code_block:
                # End of code block
                if current_file and current_lines:
                    files[current_file] = "\n".join(current_lines)
                current_file = None
                current_lines = []
                in_code_block = False
            elif in_code_block:
                current_lines.append(line)

        # Handle last file
        if current_file and current_lines:
            files[current_file] = "\n".join(current_lines)

        return files
