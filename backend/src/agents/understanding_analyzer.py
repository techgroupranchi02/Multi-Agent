"""
Aikyam Multi-Agent Pipeline — Understanding Analyzer
AI-powered analysis engine for PRD review flow.

Responsibilities:
1. Compute AI Confidence — before client interaction (how ambiguous is each section?)
2. Generate Dynamic Questionnaire — version-aware, context-aware questions
3. Analyze Responses — compute Understanding Score after client validation
4. Explain Low Scores — "Why is this score low?" with specific reasons
5. Trace Evidence — link every change to its source
6. Preview Impact — summarize expected changes before regeneration
7. Parse Feedback Files — extract text from PDF/DOCX/TXT/MD
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from src.integrations.llm_provider import get_llm_manager

logger = logging.getLogger(__name__)


class UnderstandingAnalyzer:
    """
    AI-powered engine for PRD understanding scoring and dynamic questionnaire generation.
    
    Two-phase scoring model:
    - Phase 1 (AI Confidence): Before client speaks — AI estimates its own ambiguity
    - Phase 2 (Understanding Score): After client answers — actual understanding level
    """

    def __init__(self):
        self.llm = get_llm_manager()

    def compute_ai_confidence(
        self,
        prd_content: str,
        raw_requirements: str,
    ) -> list[dict[str, Any]]:
        """
        Compute initial AI Confidence scores for each PRD section.
        Called immediately after PRD generation, before any client interaction.
        
        Returns list of section scores with why_low explanations.
        """
        sections = self._extract_sections(prd_content)
        if not sections:
            return []

        section_summaries = "\n".join(
            f"- {s['name']}: {s['content'][:200]}..."
            for s in sections
        )

        prompt = f"""Analyze this PRD and rate YOUR OWN CONFIDENCE in how well each section 
captures the original requirements. This is NOT about correctness — it's about 
whether the requirements were specific enough for you to write this section confidently.

ORIGINAL REQUIREMENTS:
{raw_requirements[:3000]}

PRD SECTIONS:
{section_summaries}

For each section, provide:
1. confidence_score (0-100): How confident are you that this section accurately reflects what the client wants?
2. confidence_level: "high" (>85), "medium" (60-85), "low" (<60)
3. why_low: If score < 85, list specific reasons why confidence is low (e.g., "Refund policy unclear", "Currency handling ambiguous")

Respond in this exact JSON format:
{{
    "sections": [
        {{
            "section_name": "Section Name",
            "confidence_score": 85,
            "confidence_level": "high",
            "why_low": []
        }}
    ]
}}

Be honest. If the requirements were vague about something, say so."""

        try:
            response = self.llm.chat(
                agent_name="requirements",
                messages=[
                    {"role": "system", "content": "You are a requirements analysis AI. Respond only in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            result = self._parse_json_response(response.content)
            if result and "sections" in result:
                return result["sections"]

        except Exception as e:
            logger.error("AI Confidence computation failed: %s", e)

        # Fallback: default scores
        return [
            {
                "section_name": s["name"],
                "confidence_score": 75,
                "confidence_level": "medium",
                "why_low": ["Unable to compute — using default score"],
            }
            for s in sections
        ]

    def generate_questionnaire(
        self,
        prd_content: str,
        version: int,
        ai_confidence_scores: list[dict[str, Any]],
        previous_responses: Optional[dict[str, list[dict]]] = None,
        previous_feedback: Optional[str] = None,
        locked_sections: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Generate a dynamic, version-aware questionnaire.
        
        Key design: Questions change based on:
        - Current PRD content and version
        - AI confidence scores (low-confidence sections get more questions)
        - Previous questionnaire responses (don't re-ask answered questions)
        - Previous feedback (ask about new areas of concern)
        - Locked sections (skip sections already approved)
        """
        locked_sections = locked_sections or []
        sections = self._extract_sections(prd_content)
        
        # Build context about what's already been validated
        context_parts = []
        if version > 1:
            context_parts.append(f"This is PRD version {version}. Previous versions have been reviewed.")
        if previous_responses:
            answered_summary = {
                section: len(responses)
                for section, responses in previous_responses.items()
            }
            context_parts.append(
                f"Previously answered questions by section: {json.dumps(answered_summary)}"
            )
        if previous_feedback:
            context_parts.append(
                f"Previous client feedback (summarized): {previous_feedback[:1000]}"
            )
        if locked_sections:
            context_parts.append(
                f"Locked sections (already approved, skip these): {', '.join(locked_sections)}"
            )

        context = "\n".join(context_parts) if context_parts else "This is the first review."

        # Build confidence context
        confidence_info = "\n".join(
            f"- {s['section_name']}: {s['confidence_score']}% confidence"
            + (f" (Low because: {', '.join(s.get('why_low', []))})" if s.get('why_low') else "")
            for s in ai_confidence_scores
        )

        prompt = f"""Generate a validation questionnaire for this PRD. The goal is to check 
whether WE (the AI) correctly understood what the CLIENT wants — NOT whether the PRD is correct.

PRD CONTENT:
{prd_content[:6000]}

AI CONFIDENCE SCORES:
{confidence_info}

CONTEXT:
{context}

RULES:
1. Do NOT generate questions for locked sections: {locked_sections}
2. Low-confidence sections should get MORE questions (6-10)
3. High-confidence sections should get FEWER questions (2-4)
4. Questions should be answerable in under 30 seconds each
5. Include a mix of: Yes/No confirmations, Multiple choice, Short text
6. Do NOT repeat questions that were already answered in previous versions
7. Focus questions on areas where AI confidence is low
8. Each question must have a unique id like "q_sectionname_1"
9. Either/or questions (e.g. choice between Option A or Option B) MUST be of type "multiple_choice" with explicit options in the "options" array. Do NOT use "yes_no" type for either/or questions.
10. Use "yes_no" type ONLY for direct binary yes/no questions where "Yes" or "No" is the natural, grammatically correct answer.

Respond in this exact JSON format:
{{
    "sections": [
        {{
            "section_name": "Authentication",
            "question_count": 5,
            "estimated_minutes": 2,
            "questions": [
                {{
                    "id": "q_auth_1",
                    "text": "Should users be able to log in with social accounts (Google, GitHub)?",
                    "type": "yes_no",
                    "options": null,
                    "context": "The PRD assumes email/password only."
                }},
                {{
                    "id": "q_auth_2", 
                    "text": "What should happen when a user enters the wrong password 5 times?",
                    "type": "multiple_choice",
                    "options": ["Lock account for 30 minutes", "Send email alert", "Require CAPTCHA", "Other"],
                    "context": "The PRD does not specify a lockout policy."
                }},
                {{
                    "id": "q_auth_3",
                    "text": "Any additional authentication requirements we missed?",
                    "type": "short_text",
                    "options": null,
                    "context": "Open-ended to catch anything we overlooked."
                }}
            ]
        }}
    ]
}}"""

        try:
            response = self.llm.chat(
                agent_name="requirements",
                messages=[
                    {"role": "system", "content": "You are a requirements validation specialist. Respond only in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=4000,
            )

            result = self._parse_json_response(response.content)
            if result and "sections" in result:
                return result["sections"]

        except Exception as e:
            logger.error("Questionnaire generation failed: %s", e)

        return []

    def analyze_responses(
        self,
        prd_content: str,
        questionnaire_responses: dict[str, list[dict[str, Any]]],
        feedback_text: Optional[str] = None,
        feedback_file_contents: Optional[list[dict[str, str]]] = None,
    ) -> dict[str, Any]:
        """
        Analyze client responses to compute Requirement Understanding Scores.
        
        Returns:
        - Overall understanding score
        - Per-section scores with why_low explanations
        - Categorized feedback: new_requirements, clarifications, conflicts, enhancements
        """
        # Compile all feedback
        all_feedback_parts = []

        if questionnaire_responses:
            for section, responses in questionnaire_responses.items():
                for resp in responses:
                    all_feedback_parts.append(
                        f"[{section}] Q: {resp.get('question', '')} → A: {resp.get('answer', '')}"
                    )

        if feedback_text:
            all_feedback_parts.append(f"[Client Text Feedback]: {feedback_text}")

        if feedback_file_contents:
            for file_info in feedback_file_contents:
                all_feedback_parts.append(
                    f"[Uploaded File: {file_info.get('filename', 'unknown')}]: "
                    f"{file_info.get('content', '')[:2000]}"
                )

        combined_feedback = "\n".join(all_feedback_parts)

        prompt = f"""Analyze the client's feedback against the current PRD to compute 
Requirement Understanding Scores. The score measures: "How well do we understand 
what the client wants for this section?"

PRD CONTENT:
{prd_content[:4000]}

CLIENT FEEDBACK:
{combined_feedback[:4000]}

For each PRD section, provide:
1. understanding_score (0-100): How well we now understand what the client wants
2. why_low: If score < 85, explain SPECIFICALLY what's still unclear
3. Categorize all feedback items as: new_requirement, clarification, conflict, or enhancement

Respond in this exact JSON format:
{{
    "overall_score": 85,
    "sections": [
        {{
            "section_name": "Authentication",
            "understanding_score": 96,
            "why_low": [],
            "confidence_level": "high"
        }},
        {{
            "section_name": "Payments",
            "understanding_score": 71,
            "why_low": ["Refund policy still unclear", "Currency handling ambiguous"],
            "confidence_level": "low"
        }}
    ],
    "feedback_categories": {{
        "new_requirements": [
            {{"description": "Add refund workflow", "section": "Payments", "source": "Questionnaire #14"}}
        ],
        "clarifications": [
            {{"description": "Permissions should be role-based", "section": "User Management", "source": "Feedback Document"}}
        ],
        "conflicts": [
            {{"description": "Client wants both SSO and local auth, PRD assumed SSO only", "section": "Authentication", "source": "Questionnaire #3"}}
        ],
        "enhancements": [
            {{"description": "Add reporting module", "section": "Reports", "source": "Client Text Feedback"}}
        ]
    }},
    "total_new_requirements": 4,
    "total_clarifications": 6,
    "total_conflicts": 2,
    "total_enhancements": 5
}}"""

        try:
            response = self.llm.chat(
                agent_name="requirements",
                messages=[
                    {"role": "system", "content": "You are a requirements analysis expert. Respond only in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            result = self._parse_json_response(response.content)
            if result:
                return result

        except Exception as e:
            logger.error("Response analysis failed: %s", e)

        return {
            "overall_score": 0,
            "sections": [],
            "feedback_categories": {},
            "total_new_requirements": 0,
            "total_clarifications": 0,
            "total_conflicts": 0,
            "total_enhancements": 0,
        }

    def preview_impact(
        self,
        current_prd: str,
        analysis_result: dict[str, Any],
        locked_sections: list[str],
    ) -> dict[str, Any]:
        """
        Preview what will change if we regenerate the PRD.
        Called before the client clicks "Generate PRD vN+1".
        
        Returns a human-readable impact summary.
        """
        categories = analysis_result.get("feedback_categories", {})

        prompt = f"""Based on the following analysis of client feedback, predict what will 
change in the next PRD version.

CURRENT PRD (summary of sections):
{self._summarize_sections(current_prd)}

FEEDBACK ANALYSIS:
- New Requirements: {json.dumps(categories.get('new_requirements', []))}
- Clarifications: {json.dumps(categories.get('clarifications', []))}
- Conflicts: {json.dumps(categories.get('conflicts', []))}
- Enhancements: {json.dumps(categories.get('enhancements', []))}

LOCKED SECTIONS (will NOT be modified): {locked_sections}

Predict the impact. Respond in JSON:
{{
    "sections_modified": 5,
    "features_added": 2,
    "requirements_removed": 1,
    "ambiguities_resolved": 8,
    "estimated_change_magnitude": "significant",
    "changes_summary": [
        "Add refund workflow to Payments section",
        "Update Authentication to support both SSO and local auth",
        "Add new Reporting module"
    ],
    "sections_affected": ["Payments", "Authentication", "Reports"],
    "sections_unchanged": ["User Management"]
}}"""

        try:
            response = self.llm.chat(
                agent_name="requirements",
                messages=[
                    {"role": "system", "content": "You are a change impact analyst. Respond only in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            result = self._parse_json_response(response.content)
            if result:
                return result

        except Exception as e:
            logger.error("Impact preview failed: %s", e)

        return {
            "sections_modified": 0,
            "features_added": 0,
            "requirements_removed": 0,
            "ambiguities_resolved": 0,
            "estimated_change_magnitude": "unknown",
            "changes_summary": [],
            "sections_affected": [],
            "sections_unchanged": [],
        }

    def generate_change_evidence(
        self,
        old_prd: str,
        new_prd: str,
        analysis_result: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Generate evidence tracing for every change between PRD versions.
        Links each change to its source (questionnaire #, feedback doc, comment).
        """
        categories = analysis_result.get("feedback_categories", {})

        prompt = f"""Compare the old and new PRD versions. For EVERY change, trace it 
back to its source in the client feedback.

OLD PRD (key sections):
{old_prd[:3000]}

NEW PRD (key sections):
{new_prd[:3000]}

FEEDBACK THAT DROVE CHANGES:
{json.dumps(categories, indent=2)[:2000]}

For each change, provide:
{{
    "evidence": [
        {{
            "change_description": "Added refund workflow",
            "source_type": "questionnaire",
            "source_reference": "Questionnaire #14",
            "section_affected": "Payments",
            "change_type": "added"
        }}
    ]
}}

change_type must be one of: "added", "modified", "removed", "clarified"
source_type must be one of: "questionnaire", "feedback_file", "client_comment", "ai_inference"
"""

        try:
            response = self.llm.chat(
                agent_name="requirements",
                messages=[
                    {"role": "system", "content": "You are a change tracking analyst. Respond only in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )

            result = self._parse_json_response(response.content)
            if result and "evidence" in result:
                return result["evidence"]

        except Exception as e:
            logger.error("Change evidence generation failed: %s", e)

        return []

    # ── Feedback File Parsing ──

    @staticmethod
    def parse_feedback_file(filepath: str, file_type: str) -> str:
        """Extract text content from uploaded feedback files."""
        try:
            if file_type in ("txt", "md", "markdown", "text"):
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()

            elif file_type == "pdf":
                try:
                    import PyPDF2
                    with open(filepath, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        text_parts = []
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                text_parts.append(text)
                        return "\n\n".join(text_parts)
                except ImportError:
                    logger.warning("PyPDF2 not installed — cannot parse PDF")
                    return f"[PDF file: {os.path.basename(filepath)} — install PyPDF2 to extract text]"

            elif file_type in ("docx", "doc"):
                try:
                    from docx import Document
                    doc = Document(filepath)
                    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
                except ImportError:
                    logger.warning("python-docx not installed — cannot parse DOCX")
                    return f"[DOCX file: {os.path.basename(filepath)} — install python-docx to extract text]"

            else:
                # Try reading as text
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

        except Exception as e:
            logger.error("Failed to parse feedback file %s: %s", filepath, e)
            return f"[Error parsing file: {e}]"

    # ── Private Helpers ──

    @staticmethod
    def _extract_sections(prd_content: str) -> list[dict[str, str]]:
        """Extract section names and content from PRD markdown."""
        sections = []
        lines = prd_content.split("\n")
        current_name = "Introduction"
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            is_header = (
                stripped.startswith("#")
                or re.match(r"^\*?\*?\d+\.\s", stripped)
            )

            if is_header and current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append({"name": current_name, "content": content})
                current_lines = []
                clean = stripped.lstrip("#").strip().lstrip("0123456789.").strip().strip("*").strip()
                if clean:
                    current_name = clean

            current_lines.append(line)

        # Last section
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append({"name": current_name, "content": content})

        return sections

    @staticmethod
    def _summarize_sections(prd_content: str) -> str:
        """Create a brief summary of PRD section names and sizes."""
        sections = []
        lines = prd_content.split("\n")
        current_name = "Introduction"
        line_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                if line_count > 0:
                    sections.append(f"- {current_name} ({line_count} lines)")
                current_name = stripped.lstrip("#").strip()
                line_count = 0
            line_count += 1

        if line_count > 0:
            sections.append(f"- {current_name} ({line_count} lines)")

        return "\n".join(sections)

    @staticmethod
    def _parse_json_response(content: str) -> Optional[dict]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Strip markdown code blocks if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            # Remove first line (```json) and last line (```)
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            logger.warning("Could not parse JSON from LLM response: %s...", cleaned[:200])
            return None

    def generate_quick_questions(
        self,
        prd_content: str,
        raw_requirements: str,
    ) -> list[dict[str, Any]]:
        """
        Generate high-level open and multiple-choice questions for the entire PRD to resolve primary ambiguities.
        Generates 5-20 questions based on necessity, focusing on broad questions that can resolve
        multiple detailed issues at once.
        """
        prompt = f"""Review the current PRD against the original raw requirements. Identify major gaps,
ambiguities, or areas where the PRD might have made assumptions that need client validation.

ORIGINAL REQUIREMENTS:
{raw_requirements[:3000]}

PRD CONTENT:
{prd_content[:6000]}

Generate between 5 and 20 critical, high-level questions. Each question must target a major area of uncertainty or gap.
Crucially, make the questions comprehensive and high-level, so that answering a single question can resolve multiple detailed, section-wise questions at once.

For each question, decide whether it is best answered as:
1. "multiple_choice": If there are distinct, realistic alternative paths or choices. In this case, provide 3-5 clear, mutually exclusive options (do NOT include "Others" as an option, as it will be added automatically).
2. "open": If it requires a detailed custom explanation.

Respond in this exact JSON format:
{{
    "questions": [
        {{
            "id": "qq_1",
            "type": "multiple_choice",
            "text": "Question text...",
            "context": "Context or why we are asking this question...",
            "options": ["Option A text", "Option B text", "Option C text"]
        }},
        {{
            "id": "qq_2",
            "type": "open",
            "text": "Question text...",
            "context": "Context or why we are asking this question...",
            "options": null
        }}
    ]
}}
"""
        try:
            response = self.llm.chat(
                agent_name="requirements",
                messages=[
                    {"role": "system", "content": "You are a requirements analyst. Respond only in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            result = self._parse_json_response(response.content)
            if result and "questions" in result:
                return result["questions"]

        except Exception as e:
            logger.error("Failed to generate quick questions: %s", e)

        # Fallback quick questions if something fails
        return [
            {
                "id": "qq_fallback_1",
                "type": "multiple_choice",
                "text": "What is the primary success metric or goal for this initial release that we should optimize for?",
                "context": "Clarifying primary release objective.",
                "options": [
                    "Time-to-market (Fast delivery of core workflow)",
                    "High security and complete compliance auditing",
                    "Exceptional user experience and rich UI/UX animations"
                ]
            },
            {
                "id": "qq_fallback_2",
                "type": "open",
                "text": "Are there any specific user workflows, external integrations, or compliance rules we should cover in detail?",
                "context": "Identifying potential out-of-scope or missing features.",
                "options": None
            },
            {
                "id": "qq_fallback_3",
                "type": "open",
                "text": "Are there any constraints (time, budget, technology stack) that we should explicitly document in the assumptions?",
                "context": "Capturing technical or operational constraints.",
                "options": None
            }
        ]



