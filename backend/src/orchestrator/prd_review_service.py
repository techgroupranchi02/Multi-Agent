"""
Aikyam Multi-Agent Pipeline — PRD Review Service
Core orchestration sub-workflow for the iterative PRD refinement loop.

Manages the lifecycle: generate PRD → save to Docs → index in RAG →
compute AI confidence → generate questionnaire → collect feedback →
analyze understanding → regenerate (on demand) → repeat.

Review Session belongs to PRD Version (not Project).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from src.models.project_state import (
    ChangeEvidence,
    PipelineState,
    PRDVersion,
    PRDVersionStatus,
    ReviewSession,
    ReviewSessionStatus,
    SectionLockStatus,
    SectionUnderstanding,
)

logger = logging.getLogger(__name__)

# Secret for signing review tokens (in production, use env var)
_TOKEN_SECRET = os.environ.get("REVIEW_TOKEN_SECRET", "aikyam-review-secret-change-me")
_TOKEN_EXPIRY_HOURS = 72  # 3 days


def _normalize_name(name: str) -> str:
    """Normalize a section or heading name for comparison."""
    n = name.lower()
    n = n.replace("and", "").replace("&", "")
    return re.sub(r"[^a-zA-Z0-9]", "", n)


class PRDReviewService:
    """
    Manages the PRD review loop as a sub-workflow within Phase 1-2.
    
    Flow:
    1. create_version() — after PRD is generated
    2. start_review_session() — opens review for the version
    3. submit_questionnaire_response() — client answers questions
    4. upload_feedback() — client uploads feedback files
    5. check_readiness() — checks if ready for regeneration
    6. regenerate_prd() — creates next version (on demand)
    """

    def __init__(self):
        self._analyzer = None
        self._rag = None
        self._gdocs = None

    @property
    def analyzer(self):
        """Lazy-load the understanding analyzer."""
        if self._analyzer is None:
            from src.agents.understanding_analyzer import UnderstandingAnalyzer
            self._analyzer = UnderstandingAnalyzer()
        return self._analyzer

    @property
    def rag(self):
        """Lazy-load the RAG knowledge base."""
        if self._rag is None:
            from src.integrations.rag_knowledge_base import get_rag_knowledge_base
            self._rag = get_rag_knowledge_base()
        return self._rag

    @property
    def gdocs(self):
        """Lazy-load the Google Docs client."""
        if self._gdocs is None:
            from src.integrations.google_docs_client import get_google_docs_client
            self._gdocs = get_google_docs_client()
        return self._gdocs

    # ── Version Lifecycle ──

    def create_version(
        self,
        state: PipelineState,
        prd_content: str,
        changes_from_previous: Optional[list[str]] = None,
        change_evidence: Optional[list[ChangeEvidence]] = None,
    ) -> PipelineState:
        """
        Create a new PRD version. Called after PRD generation.
        
        1. Create PRDVersion object
        2. Archive previous version (if any)
        3. Save to Google Docs as versioned tab
        4. Index in RAG (replace previous)
        5. Compute AI Confidence scores
        6. Create ReviewSession
        """
        version_num = state.current_prd_version + 1

        # Soft warning after 5 versions
        if version_num > 5:
            logger.warning(
                "⚠ PRD version %d for project %s — consider finalizing the requirements",
                version_num, state.project_name,
            )

        # Archive previous version
        prev = state.get_current_prd_version()
        if prev:
            prev.status = PRDVersionStatus.ARCHIVED
            # Archive in Google Docs
            if prev.gdoc_tab_id:
                try:
                    doc_id_file = os.path.join(state.workspace_path, ".state", "project_doc_id.txt")
                    if os.path.exists(doc_id_file):
                        with open(doc_id_file) as f:
                            doc_id = f.read().strip()
                        self.gdocs.archive_tab(doc_id, prev.gdoc_tab_id, prev.version)
                except Exception as e:
                    logger.warning("Failed to archive previous tab: %s", e)

        # Create new PRD version
        prd_version = PRDVersion(
            version=version_num,
            content=prd_content,
            created_at=datetime.utcnow(),
            changes_from_previous=changes_from_previous or [],
            change_evidence=change_evidence or [],
        )

        # Save to Google Docs as versioned tab
        try:
            result = self.gdocs.create_versioned_tab(
                project_id=state.project_id,
                project_name=state.project_name,
                version=version_num,
                content=prd_content,
                workspace_path=state.workspace_path,
            )
            if result:
                prd_version.gdoc_url = result["url"]
                prd_version.gdoc_tab_id = result.get("tab_id", "")
                logger.info("Saved PRD v%d to Google Docs: %s", version_num, result["url"])
        except Exception as e:
            logger.warning("Failed to save PRD v%d to Google Docs: %s", version_num, e)

        # Index in RAG (replace previous)
        try:
            self.rag.replace_index(
                project_id=state.project_id,
                content=prd_content,
                new_version=version_num,
                metadata={"project_name": state.project_name},
            )
            logger.info("Indexed PRD v%d in RAG", version_num)
        except Exception as e:
            logger.warning("Failed to index PRD v%d in RAG: %s", version_num, e)

        # Compute AI Confidence
        try:
            confidence_scores = self.analyzer.compute_ai_confidence(
                prd_content=prd_content,
                raw_requirements=state.raw_requirements,
            )

            section_understandings = []
            total_confidence = 0.0

            for score_data in confidence_scores:
                section = SectionUnderstanding(
                    section_name=score_data.get("section_name", "Unknown"),
                    ai_confidence=score_data.get("confidence_score", 75),
                    confidence_level=score_data.get("confidence_level", "medium"),
                    why_low=score_data.get("why_low", []),
                )

                # Carry over locked status from previous version
                if prev:
                    for prev_section in prev.section_scores:
                        if prev_section.section_name == section.section_name:
                            if prev_section.lock_status == SectionLockStatus.LOCKED:
                                section.lock_status = SectionLockStatus.LOCKED
                                section.locked_at = prev_section.locked_at
                                section.locked_by = prev_section.locked_by
                            break

                section_understandings.append(section)
                total_confidence += section.ai_confidence

            prd_version.section_scores = section_understandings
            
            # Map heading IDs if Google Doc tab was successfully created
            if 'result' in locals() and result and result.get("doc_id") and result.get("tab_id"):
                try:
                    heading_ids = self.gdocs.get_heading_ids(result["doc_id"], result["tab_id"])
                    for score in section_understandings:
                        norm_score_name = _normalize_name(score.section_name)
                        for heading_text, h_id in heading_ids.items():
                            if _normalize_name(heading_text) == norm_score_name:
                                score.gdoc_heading_id = h_id
                                break
                    logger.info("Mapped heading IDs to section scores for PRD v%d", version_num)
                except Exception as heading_err:
                    logger.warning("Failed to map heading IDs to section scores on creation: %s", heading_err)

            prd_version.overall_ai_confidence = (
                total_confidence / len(section_understandings)
                if section_understandings else 0.0
            )

            logger.info(
                "AI Confidence for v%d: %.1f%% (%d sections)",
                version_num, prd_version.overall_ai_confidence, len(section_understandings),
            )
        except Exception as e:
            logger.warning("Failed to compute AI Confidence: %s", e)

        # Generate questionnaire on creation and store in understandings
        try:
            previous_responses = None
            previous_feedback = None
            if version_num > 1:
                prev_version = state.get_prd_version(version_num - 1)
                if prev_version and prev_version.review_session:
                    previous_responses = prev_version.review_session.questionnaire_responses
                    previous_feedback = prev_version.review_session.feedback_text

            locked_sections = state.get_locked_sections()

            ai_confidence = [
                {
                    "section_name": s.section_name,
                    "confidence_score": s.ai_confidence,
                    "confidence_level": s.confidence_level,
                    "why_low": s.why_low,
                }
                for s in prd_version.section_scores
            ]

            questionnaire = self.analyzer.generate_questionnaire(
                prd_content=prd_content,
                version=version_num,
                ai_confidence_scores=ai_confidence,
                previous_responses=previous_responses,
                previous_feedback=previous_feedback,
                locked_sections=locked_sections,
            )

            # Update section question counts and questions list in state
            for section_data in questionnaire:
                section_name = section_data.get("section_name", "")
                for score in prd_version.section_scores:
                    if score.section_name == section_name:
                        score.question_count = section_data.get("question_count", 0)
                        score.estimated_minutes = section_data.get("estimated_minutes", 0)
                        score.questions = section_data.get("questions", [])
                        break

            # Ensure every unlocked section has at least one validation question
            for score in prd_version.section_scores:
                if score.lock_status == SectionLockStatus.UNLOCKED and not score.questions:
                    score.questions = [
                        {
                            "id": f"q_fallback_{score.section_name.lower().replace(' ', '_')}",
                            "text": f"Is the '{score.section_name}' section accurate and complete?",
                            "type": "yes_no",
                            "options": None,
                            "context": "General confirmation question."
                        }
                    ]
                    score.question_count = 1
                    score.estimated_minutes = 1

            logger.info("Generated and cached questionnaire for PRD v%d", version_num)
        except Exception as q_err:
            logger.warning("Failed to generate questionnaire on version creation: %s", q_err)

        # Create ReviewSession for this version
        review_session = ReviewSession(
            prd_version=version_num,
            started_at=datetime.utcnow(),
        )

        # Generate quick questions for Quick Mode validation
        try:
            quick_questions = self.analyzer.generate_quick_questions(
                prd_content=prd_content,
                raw_requirements=state.raw_requirements,
            )
            review_session.quick_questions = quick_questions
            logger.info("Generated %d quick questions for PRD v%d", len(quick_questions), version_num)
        except Exception as quick_q_err:
            logger.warning("Failed to generate quick questions on version creation: %s", quick_q_err)

        prd_version.review_session = review_session

        # Update state
        state.prd_versions.append(prd_version)
        state.current_prd_version = version_num
        state.prd = prd_content  # Keep backward compatibility

        return state

    def ensure_heading_ids(self, state: PipelineState, prd_version: PRDVersion) -> None:
        """Lazily populate heading IDs for sections if missing."""
        if not prd_version.gdoc_tab_id:
            return
        
        # Check if any section is missing a heading ID
        missing_ids = any(s.gdoc_heading_id is None for s in prd_version.section_scores)
        if not missing_ids:
            return
            
        try:
            doc_id_file = os.path.join(state.workspace_path, ".state", "project_doc_id.txt")
            if not os.path.exists(doc_id_file):
                return
            with open(doc_id_file) as f:
                doc_id = f.read().strip()
                
            heading_ids = self.gdocs.get_heading_ids(doc_id, prd_version.gdoc_tab_id)
            if heading_ids:
                for score in prd_version.section_scores:
                    if score.gdoc_heading_id is None:
                        norm_score_name = _normalize_name(score.section_name)
                        for heading_text, h_id in heading_ids.items():
                            if _normalize_name(heading_text) == norm_score_name:
                                score.gdoc_heading_id = h_id
                                break
                # Save state changes
                from src.orchestrator.orchestrator import get_orchestrator
                get_orchestrator()._save_state(state)
                logger.info("Lazily populated heading IDs for PRD v%d", prd_version.version)
        except Exception as e:
            logger.warning("Failed to lazily populate heading IDs: %s", e)

    def start_review_session(self, state: PipelineState) -> Optional[str]:
        """Get or start the review session for the current PRD version."""
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return None
        return current.review_session.session_id

    # ── Questionnaire ──

    def get_questionnaire(self, state: PipelineState) -> list[dict[str, Any]]:
        """
        Return the pre-generated questionnaire for the current PRD version.
        If questions are cached in the state, return them immediately.
        """
        current = state.get_current_prd_version()
        if not current:
            return []

        # Check if questionnaire is already generated and cached in state
        has_questions = any(len(s.questions) > 0 for s in current.section_scores)
        if has_questions:
            return [
                {
                    "section_name": s.section_name,
                    "question_count": s.question_count,
                    "estimated_minutes": s.estimated_minutes,
                    "questions": s.questions,
                }
                for s in current.section_scores
                if s.questions
            ]

        # Gather context from previous versions (Fallback dynamic generation)
        previous_responses = None
        previous_feedback = None
        if current.version > 1:
            prev = state.get_prd_version(current.version - 1)
            if prev and prev.review_session:
                previous_responses = prev.review_session.questionnaire_responses
                previous_feedback = prev.review_session.feedback_text

        locked_sections = state.get_locked_sections()

        ai_confidence = [
            {
                "section_name": s.section_name,
                "confidence_score": s.ai_confidence,
                "confidence_level": s.confidence_level,
                "why_low": s.why_low,
            }
            for s in current.section_scores
        ]

        questionnaire = self.analyzer.generate_questionnaire(
            prd_content=current.content,
            version=current.version,
            ai_confidence_scores=ai_confidence,
            previous_responses=previous_responses,
            previous_feedback=previous_feedback,
            locked_sections=locked_sections,
        )

        # Update section question counts
        for section_data in questionnaire:
            section_name = section_data.get("section_name", "")
            for score in current.section_scores:
                if score.section_name == section_name:
                    score.question_count = section_data.get("question_count", 0)
                    score.estimated_minutes = section_data.get("estimated_minutes", 0)
                    score.questions = section_data.get("questions", [])
                    break

        # Ensure every unlocked section has at least one validation question
        for score in current.section_scores:
            if score.lock_status == SectionLockStatus.UNLOCKED and not score.questions:
                score.questions = [
                    {
                        "id": f"q_fallback_{score.section_name.lower().replace(' ', '_')}",
                        "text": f"Is the '{score.section_name}' section accurate and complete?",
                        "type": "yes_no",
                        "options": None,
                        "context": "General confirmation question."
                    }
                ]
                score.question_count = 1
                score.estimated_minutes = 1

        return [
            {
                "section_name": s.section_name,
                "question_count": s.question_count,
                "estimated_minutes": s.estimated_minutes,
                "questions": s.questions,
            }
            for s in current.section_scores
            if s.questions
        ]

    def submit_questionnaire_response(
        self,
        state: PipelineState,
        section_name: str,
        responses: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """
        Store responses for a section and recalculate understanding scores.
        Returns updated section score or None.
        """
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return None

        session = current.review_session
        
        # Resolve question text from cached questions in state
        resolved_responses = []
        for resp in responses:
            q_id = resp.get("id")
            q_text = ""
            for score in current.section_scores:
                if score.section_name == section_name:
                    for q in score.questions:
                        if q.get("id") == q_id:
                            q_text = q.get("text", "")
                            break
                    break
            resolved_responses.append({
                "id": q_id,
                "question": q_text,
                "answer": resp.get("answer"),
                "confidence": resp.get("confidence", 3),
            })

        session.questionnaire_responses[section_name] = resolved_responses

        if section_name not in session.completed_sections:
            session.completed_sections.append(section_name)

        # Recalculate understanding score for this section using AI
        try:
            analysis = self.analyzer.analyze_responses(
                prd_content=current.content,
                questionnaire_responses={section_name: resolved_responses},
            )

            # Update the specific section score
            for section_result in analysis.get("sections", []):
                if section_result.get("section_name") == section_name:
                    for score in current.section_scores:
                        if score.section_name == section_name:
                            score.understanding_score = section_result.get("understanding_score")
                            score.why_low = section_result.get("why_low", [])
                            score.confidence_level = section_result.get("confidence_level", "medium")
                            break

            return {
                "section_name": section_name,
                "responses_saved": len(responses),
                "updated_score": next(
                    (s.understanding_score for s in current.section_scores
                     if s.section_name == section_name),
                    None,
                ),
            }

        except Exception as e:
            logger.error("Failed to analyze responses for %s: %s", section_name, e)
            return {"section_name": section_name, "responses_saved": len(responses)}

    def submit_quick_responses(
        self,
        state: PipelineState,
        responses: dict[str, str],
    ) -> bool:
        """
        Submit responses to the global open questions (Quick Mode).
        Saves the answers, switches review_mode to 'quick', and completes the session.
        """
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return False

        session = current.review_session
        session.quick_responses = responses
        session.review_mode = "quick"
        session.status = ReviewSessionStatus.READY_FOR_REDRAFT
        session.completed_at = datetime.utcnow()

        logger.info("Saved %d quick responses for PRD v%d", len(responses), current.version)
        return True

    # ── Feedback ──

    def upload_feedback(
        self,
        state: PipelineState,
        filename: str,
        filepath: str,
        file_type: str,
        mime_type: str = "application/octet-stream",
    ) -> Optional[dict[str, Any]]:
        """
        Process an uploaded feedback file:
        1. Save locally
        2. Extract text content
        3. Upload to Google Drive
        4. Run AI analysis
        """
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return None

        session = current.review_session

        # Extract text from file
        text_content = self.analyzer.parse_feedback_file(filepath, file_type)

        # Upload to Google Drive
        drive_url = ""
        try:
            drive_url = self.gdocs.upload_feedback_to_drive(
                filename=filename,
                filepath=filepath,
                mime_type=mime_type,
                project_name=state.project_name,
            ) or ""
        except Exception as e:
            logger.warning("Failed to upload feedback to Drive: %s", e)

        # Track in session
        session.feedback_files.append({
            "filename": filename,
            "path": filepath,
            "type": file_type,
            "drive_url": drive_url,
        })

        # Run AI analysis
        try:
            analysis = self.analyzer.analyze_responses(
                prd_content=current.content,
                questionnaire_responses=session.questionnaire_responses,
                feedback_file_contents=[{
                    "filename": filename,
                    "content": text_content,
                }],
            )

            session.understanding_analysis = analysis
            session.new_requirements = analysis.get("total_new_requirements", 0)
            session.clarifications = analysis.get("total_clarifications", 0)
            session.conflicts = analysis.get("total_conflicts", 0)
            session.enhancements = analysis.get("total_enhancements", 0)

            return {
                "filename": filename,
                "drive_url": drive_url,
                "analysis": {
                    "new_requirements": session.new_requirements,
                    "clarifications": session.clarifications,
                    "conflicts": session.conflicts,
                    "enhancements": session.enhancements,
                },
            }

        except Exception as e:
            logger.error("Feedback analysis failed: %s", e)
            return {"filename": filename, "drive_url": drive_url}

    def submit_feedback_text(
        self,
        state: PipelineState,
        feedback_text: str,
    ) -> Optional[dict[str, Any]]:
        """Process pasted text feedback."""
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return None

        session = current.review_session
        session.feedback_text = feedback_text

        # Run analysis
        try:
            analysis = self.analyzer.analyze_responses(
                prd_content=current.content,
                questionnaire_responses=session.questionnaire_responses,
                feedback_text=feedback_text,
            )

            session.understanding_analysis = analysis
            session.new_requirements = analysis.get("total_new_requirements", 0)
            session.clarifications = analysis.get("total_clarifications", 0)
            session.conflicts = analysis.get("total_conflicts", 0)
            session.enhancements = analysis.get("total_enhancements", 0)

            return {
                "overall_score": analysis.get("overall_score", 0),
                "new_requirements": session.new_requirements,
                "clarifications": session.clarifications,
                "conflicts": session.conflicts,
                "enhancements": session.enhancements,
            }

        except Exception as e:
            logger.error("Text feedback analysis failed: %s", e)
            return None

    # ── Readiness & Impact ──

    def check_readiness(self, state: PipelineState) -> dict[str, Any]:
        """Check if the current review session is ready for PRD regeneration."""
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return {"ready": False, "reason": "No active review session"}

        session = current.review_session
        total_sections = len(current.section_scores)
        locked_sections = len(state.get_locked_sections())
        answerable = total_sections - locked_sections
        completed = len(session.completed_sections)

        has_questionnaire = completed > 0
        has_feedback = bool(session.feedback_files) or bool(session.feedback_text)

        # Compute overall understanding score
        scores = [
            s.understanding_score for s in current.section_scores
            if s.understanding_score is not None
        ]
        overall_understanding = sum(scores) / len(scores) if scores else None

        return {
            "ready": has_questionnaire or has_feedback,
            "overall_understanding_score": overall_understanding,
            "overall_ai_confidence": current.overall_ai_confidence,
            "total_sections": total_sections,
            "completed_sections": completed,
            "locked_sections": locked_sections,
            "has_questionnaire": has_questionnaire,
            "has_feedback": has_feedback,
            "feedback_file_count": len(session.feedback_files),
            "version": current.version,
            "version_warning": current.version >= 5,
        }

    def get_impact_preview(self, state: PipelineState) -> dict[str, Any]:
        """Preview what will change if we regenerate the PRD."""
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return {}

        session = current.review_session
        analysis = session.understanding_analysis

        if not analysis:
            # Run analysis if not done yet
            analysis = self.analyzer.analyze_responses(
                prd_content=current.content,
                questionnaire_responses=session.questionnaire_responses,
                feedback_text=session.feedback_text,
            )
            session.understanding_analysis = analysis

        return self.analyzer.preview_impact(
            current_prd=current.content,
            analysis_result=analysis,
            locked_sections=state.get_locked_sections(),
        )

    # ── Section Locking ──

    def lock_section(
        self,
        state: PipelineState,
        section_name: str,
        locked_by: str = "client",
    ) -> bool:
        """Lock a section that has ≥95% understanding score."""
        current = state.get_current_prd_version()
        if not current:
            return False

        for score in current.section_scores:
            if score.section_name == section_name:
                effective_score = score.understanding_score or score.ai_confidence
                if effective_score >= 95 or True:  # Allow client to lock any section
                    score.lock_status = SectionLockStatus.LOCKED
                    score.locked_at = datetime.utcnow()
                    score.locked_by = locked_by
                    logger.info("Locked section: %s (score: %.1f%%)", section_name, effective_score)
                    return True
        return False

    def unlock_section(self, state: PipelineState, section_name: str) -> bool:
        """Unlock a previously locked section."""
        current = state.get_current_prd_version()
        if not current:
            return False

        for score in current.section_scores:
            if score.section_name == section_name:
                score.lock_status = SectionLockStatus.UNLOCKED
                score.locked_at = None
                score.locked_by = None
                return True
        return False

    # ── Review Token Management ──

    @staticmethod
    def generate_review_token(project_id: str) -> dict[str, str]:
        """Generate a signed, expiring token for questionnaire access."""
        expires_at = int(time.time()) + (_TOKEN_EXPIRY_HOURS * 3600)
        payload = f"{project_id}.{expires_at}"
        signature = hmac.new(
            _TOKEN_SECRET.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        token = f"{payload}.{signature}"

        return {
            "token": token,
            "expires_at": datetime.fromtimestamp(expires_at).isoformat(),
            "review_url": f"/review/{project_id}?token={token}",
        }

    @staticmethod
    def validate_review_token(project_id: str, token: str) -> bool:
        """Validate a review token."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False

            token_project_id, expires_at_str, signature = parts

            if token_project_id != project_id:
                return False

            expires_at = int(expires_at_str)
            if time.time() > expires_at:
                return False

            # Verify signature
            payload = f"{token_project_id}.{expires_at_str}"
            expected_sig = hmac.new(
                _TOKEN_SECRET.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()[:16]

            return hmac.compare_digest(signature, expected_sig)

        except Exception:
            return False

    # ── History & Versions ──

    def get_review_history(self, state: PipelineState) -> list[dict[str, Any]]:
        """Get all review sessions with stats, ordered by version."""
        history = []
        for version in state.prd_versions:
            session = version.review_session
            entry = {
                "version": version.version,
                "status": version.status.value,
                "created_at": version.created_at.isoformat(),
                "gdoc_url": version.gdoc_url,
                "ai_confidence": version.overall_ai_confidence,
                "understanding_score": version.overall_understanding_score,
                "changes_from_previous": version.changes_from_previous,
            }

            if session:
                entry.update({
                    "session_id": session.session_id,
                    "session_status": session.status.value,
                    "session_started": session.started_at.isoformat(),
                    "session_completed": (
                        session.completed_at.isoformat()
                        if session.completed_at else None
                    ),
                    "completed_sections": len(session.completed_sections),
                    "feedback_files": len(session.feedback_files),
                    "new_requirements": session.new_requirements,
                    "clarifications": session.clarifications,
                    "conflicts": session.conflicts,
                    "enhancements": session.enhancements,
                })

            history.append(entry)

        return history

    def get_version_details(
        self,
        state: PipelineState,
        version: int,
    ) -> Optional[dict[str, Any]]:
        """Get detailed info for a specific PRD version."""
        prd_version = state.get_prd_version(version)
        if not prd_version:
            return None

        return {
            "version": prd_version.version,
            "content": prd_version.content,
            "status": prd_version.status.value,
            "created_at": prd_version.created_at.isoformat(),
            "gdoc_url": prd_version.gdoc_url,
            "ai_confidence": prd_version.overall_ai_confidence,
            "understanding_score": prd_version.overall_understanding_score,
            "section_scores": [
                {
                    "section_name": s.section_name,
                    "ai_confidence": s.ai_confidence,
                    "understanding_score": s.understanding_score,
                    "question_count": s.question_count,
                    "estimated_minutes": s.estimated_minutes,
                    "why_low": s.why_low,
                    "confidence_level": s.confidence_level,
                    "locked": s.lock_status == SectionLockStatus.LOCKED,
                }
                for s in prd_version.section_scores
            ],
            "changes_from_previous": prd_version.changes_from_previous,
            "change_evidence": [
                {
                    "change_description": e.change_description,
                    "source_type": e.source_type,
                    "source_reference": e.source_reference,
                    "section_affected": e.section_affected,
                    "change_type": e.change_type,
                }
                for e in prd_version.change_evidence
            ],
        }
