"""
Aikyam Multi-Agent Pipeline — Requirements Agent
Phase 1: Generate PRD with open questions
Phase 3: Generate PDD, Execution Plan, API Spec, DB Schema
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agents.base_agent import BaseAgent
from src.models.project_state import PhaseState, PipelineState

logger = logging.getLogger(__name__)

PRD_SYSTEM_PROMPT = """You are a Lead Product Manager and Business Analyst at a top-tier software company.
Your job is to take raw, ambiguous software requirements and transform them into a professional, 
comprehensive Product Requirements Document (PRD).

Structure your PRD with these sections:
1. **Executive Summary** — One paragraph summarizing the product
2. **User Personas** — 2-3 target user personas with pain points
3. **Functional Requirements** — Prioritized as P0 (must-have), P1 (important), P2 (nice-to-have)
4. **Non-Functional Requirements** — Performance, security, scalability, accessibility
5. **User Stories** — In the format: "As a [persona], I want [feature] so that [benefit]"
6. **Out of Scope** — Explicitly call out what is NOT included
7. **Open Questions** — List questions that need human clarification before proceeding
8. **Success Metrics** — How to measure if the product is successful
9. **Assumptions & Constraints** — Technical or business assumptions

Be thorough, precise, and focus on edge cases. Do NOT assume technical frameworks yet."""

DESIGN_SYSTEM_PROMPT = """You are a Principal Software Architect and System Designer.
Given an approved PRD, create the following technical design documents:

1. **Product Design Document (PDD)**:
   - Core user journeys (step-by-step flows)
   - UI layout descriptions and key screens
   - Information architecture
   
2. **Execution Plan**:
   - Phased delivery plan with milestones
   - Task breakdown with dependencies
   - Estimated effort per task (story points)

3. **API Design** (OpenAPI 3.0 format):
   - All REST endpoints with methods, paths, request/response schemas
   - Authentication strategy
   - Error response format
   
4. **Database Schema**:
   - Entity-Relationship description
   - Table definitions with columns, types, constraints
   - SQL CREATE TABLE statements (PostgreSQL)
   - Index strategy

Output each document clearly separated with markdown headers.
Choose the optimal tech stack based on the requirements (default: Python/FastAPI backend, React/Vite frontend, PostgreSQL).
"""


class RequirementsAgent(BaseAgent):
    """
    Phase 1: Generates PRD + Open Questions from raw requirements.
    Phase 3: Generates PDD, Execution Plan, API Spec, DB Schema from approved PRD.
    """

    agent_name = "requirements"
    agent_display_name = "Requirements & Design Agent"
    agent_icon = "📝"

    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        """Route to PRD generation (Phase 1) or Design generation (Phase 3)."""
        if phase.phase_id == 1:
            return self._generate_prd(state, phase)
        elif phase.phase_id == 3:
            return self._generate_design(state, phase)
        else:
            raise ValueError(f"RequirementsAgent doesn't handle phase {phase.phase_id}")

    def _generate_prd(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        """Phase 1: Generate PRD from raw requirements or refine it based on feedback."""
        phase.progress = 15
        
        # Check if we are iterating
        current_version = state.get_current_prd_version()
        is_iteration = current_version is not None and bool(state.human_feedback)

        if is_iteration:
            phase.add_log("info", f"Refining PRD v{current_version.version} based on client feedback...")
            
            locked_sections = state.get_locked_sections()
            locked_context = ""
            if locked_sections:
                locked_context = f"\nLOCKED SECTIONS (Do NOT modify these sections as they are already approved by the client):\n" + "\n".join(f"- {s}" for s in locked_sections)

            system_prompt = (
                f"{PRD_SYSTEM_PROMPT}\n\n"
                "You are revising/updating an existing PRD based on client feedback.\n"
                "CRITICAL RULES:\n"
                "1. Address all questionnaire answers and feedback points.\n"
                "2. Incorporate new requirements, clarifications, and enhancements.\n"
                "3. Do NOT modify sections that are explicitly locked unless the feedback directly requires a dependency change in them.\n"
                "4. Maintain consistent structure, formatting, and numbering."
            )

            user_content = (
                f"Project: '{state.project_name}'\n\n"
                f"PREVIOUS PRD (Version {current_version.version}):\n"
                f"---\n{current_version.content}\n---\n\n"
                f"CLIENT FEEDBACK & VALIDATION RESPONSES:\n"
                f"---\n{state.human_feedback}\n---\n"
                f"{locked_context}\n\n"
                "Generate the updated PRD. Be thorough and make sure all requested additions/clarifications are integrated."
            )
        else:
            phase.add_log("info", "Analyzing raw requirements...")
            system_prompt = PRD_SYSTEM_PROMPT
            user_content = (
                f"Here are the raw requirements for the project '{state.project_name}':\n\n"
                f"---\n{state.raw_requirements}\n---\n\n"
                "Generate a complete PRD following the structure outlined. "
                "Pay special attention to the Open Questions section — identify anything ambiguous."
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        phase.progress = 30
        response = self.call_llm(phase, messages, "Generating PRD" if not is_iteration else "Refining PRD")
        phase.progress = 80

        # Try to extract open questions FIRST
        state.open_questions = self._extract_open_questions(response.content)

        # Strip the Open Questions section from the PRD content
        clean_prd = self._strip_open_questions_section(response.content)
        # Renumber remaining sections (to fix gaps like jumping from 6 to 8)
        clean_prd = self._renumber_prd_sections(clean_prd)

        # Store PRD
        state.prd = clean_prd
        self.save_artifact(state, phase, "prd", clean_prd)

        if state.open_questions:
            phase.add_log(
                "info",
                f"Identified {len(state.open_questions)} open questions",
            )
            # Save open questions as a separate artifact file
            oq_content = "# Open Questions\n\n"
            oq_content += "The following questions need human clarification before proceeding:\n\n"
            for i, q in enumerate(state.open_questions, 1):
                oq_content += f"{i}. {q}\n"
            self.save_artifact(state, phase, "open_questions", oq_content)
        else:
            # Save empty open questions file
            self.save_artifact(
                state, phase, "open_questions",
                "# Open Questions\n\nNo open questions identified — requirements are clear.\n",
            )

        phase.progress = 95
        phase.add_log("success", "PRD generated successfully" if not is_iteration else "PRD refined successfully")

        # Clear human feedback after processing
        state.human_feedback = None

        return state

    @staticmethod
    def _strip_open_questions_section(prd_content: str) -> str:
        """Strip the 'Open Questions' section from the PRD content."""
        import re
        lines = []
        in_questions = False
        for line in prd_content.split("\n"):
            stripped_line = line.strip()
            # Detect starting of Open Questions section
            if "open question" in stripped_line.lower() or "## open" in stripped_line.lower():
                in_questions = True
                continue
            if in_questions:
                # Detect the next section (starts with # or a numbered heading like 8. or 9.)
                is_next_section = (
                    stripped_line.startswith("#") or 
                    re.match(r"^(\*\*?)?[89]\.\s", stripped_line) or
                    "success metrics" in stripped_line.lower() or
                    "assumptions" in stripped_line.lower()
                )
                if is_next_section:
                    in_questions = False
                else:
                    continue  # skip open question list items
            
            lines.append(line)
            
        return "\n".join(lines).rstrip() + "\n"

    def _generate_design(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        """Phase 3: Generate PDD, Execution Plan, API Spec, DB Schema."""
        if not state.prd:
            raise ValueError("Cannot generate design — PRD not available")

        phase.progress = 10
        phase.add_log("info", "Generating technical design from approved PRD...")

        # Include human feedback if any
        feedback_context = ""
        if state.human_feedback:
            feedback_context = f"\n\nHuman feedback from PRD review:\n{state.human_feedback}\n"
            state.human_feedback = None  # Clear after use

        messages = [
            {"role": "system", "content": DESIGN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {state.project_name}\n\n"
                    f"Approved PRD:\n---\n{state.prd}\n---\n"
                    f"{feedback_context}\n"
                    "Generate all four design documents (PDD, Execution Plan, API Design, DB Schema)."
                ),
            },
        ]

        phase.progress = 25
        response = self.call_llm(phase, messages, "Generating design documents", max_tokens=8000)
        phase.progress = 70

        # Parse the combined output into sections
        content = response.content
        state.pdd = content  # Full design doc stored as PDD for now

        # Save individual artifacts
        self.save_artifact(state, phase, "pdd", content)

        # Try to extract specific sections
        sections = self._split_design_sections(content)
        if "api" in sections:
            state.api_spec = sections["api"]
            self.save_artifact(state, phase, "api_spec", sections["api"], "yaml")
            phase.add_log("info", "API Design spec saved")

        if "db" in sections:
            state.db_schema = sections["db"]
            self.save_artifact(state, phase, "db_schema", sections["db"], "sql")
            phase.add_log("info", "Database schema saved")

        if "plan" in sections:
            state.execution_plan = sections["plan"]
            self.save_artifact(state, phase, "execution_plan", sections["plan"])
            phase.add_log("info", "Execution plan saved")

        phase.progress = 95
        phase.add_log("success", "All design documents generated")

        return state

    @staticmethod
    def _extract_open_questions(prd_content: str) -> list[str]:
        """Extract open questions from the PRD content."""
        questions = []
        in_questions = False
        for line in prd_content.split("\n"):
            if "open question" in line.lower() or "## open" in line.lower():
                in_questions = True
                continue
            if in_questions:
                if line.startswith("#"):
                    break  # Next section
                stripped = line.strip().lstrip("0123456789.-) ").strip()
                if stripped and len(stripped) > 5:
                    questions.append(stripped)
        return questions[:10]  # Cap at 10

    @staticmethod
    def _split_design_sections(content: str) -> dict[str, str]:
        """Try to split the design document into sections by header keywords."""
        sections: dict[str, str] = {}
        current_key = None
        current_lines: list[str] = []

        keyword_map = {
            "api": ["api design", "api spec", "openapi", "rest endpoint", "api reference"],
            "db": ["database schema", "db schema", "entity-relationship", "create table", "sql"],
            "plan": ["execution plan", "delivery plan", "task breakdown", "milestones"],
            "pdd": ["product design", "user journey", "ui layout", "information architecture"],
        }

        for line in content.split("\n"):
            lower = line.lower().strip()
            matched_key = None
            if lower.startswith("#"):
                for key, keywords in keyword_map.items():
                    if any(kw in lower for kw in keywords):
                        matched_key = key
                        break

            if matched_key and matched_key != current_key:
                if current_key and current_lines:
                    sections[current_key] = "\n".join(current_lines)
                current_key = matched_key
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_key and current_lines:
            sections[current_key] = "\n".join(current_lines)

        return sections

    @staticmethod
    def _renumber_prd_sections(prd_content: str) -> str:
        """Renumber all sections after section 7 (Open Questions) in the PRD."""
        import re
        pattern = r"^(\s*(?:#+\s+)?(?:\*\*?)?)(\d+)\.(\s*(?:\*\*?)?.*)"
        lines = []
        for line in prd_content.split("\n"):
            match = re.match(pattern, line)
            if match:
                prefix = match.group(1)
                num = int(match.group(2))
                rest = match.group(3)
                if num > 7:
                    line = f"{prefix}{num - 1}.{rest}"
            lines.append(line)
        return "\n".join(lines)
