"""
Aikyam Multi-Agent Pipeline — Review API Routes
REST endpoints for the PRD review flow, questionnaire, and client dashboard.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.models.project_state import (
    FeedbackTextSubmission,
    QuestionnaireSubmission,
    RegenerateRequest,
    SectionLockRequest,
)
from src.orchestrator.orchestrator import get_orchestrator
from src.orchestrator.prd_review_service import PRDReviewService

logger = logging.getLogger(__name__)
review_router = APIRouter(prefix="/api/review", tags=["Review"])
client_router = APIRouter(prefix="/api/client", tags=["Client Dashboard"])

# Shared service instance
_review_service: Optional[PRDReviewService] = None


def _get_review_service() -> PRDReviewService:
    global _review_service
    if _review_service is None:
        _review_service = PRDReviewService()
    return _review_service


def _get_state(project_id: str):
    """Get pipeline state or raise 404."""
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")
    return state


def _validate_token(project_id: str, token: Optional[str] = None):
    """Validate review token if provided."""
    if token:
        service = _get_review_service()
        if not service.validate_review_token(project_id, token):
            raise HTTPException(status_code=403, detail="Invalid or expired review token")


# ── Review Endpoints ──

@review_router.get("/{project_id}")
async def get_review_status(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """Get current PRD version, understanding scores, and review status."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    current = state.get_current_prd_version()
    if not current:
        return {
            "project_id": project_id,
            "project_name": state.project_name,
            "has_prd": False,
            "message": "No PRD version generated yet",
        }

    # Lazily ensure heading IDs are populated
    service.ensure_heading_ids(state, current)

    readiness = service.check_readiness(state)

    return {
        "project_id": project_id,
        "project_name": state.project_name,
        "has_prd": True,
        "current_version": current.version,
        "status": current.status.value,
        "gdoc_url": current.gdoc_url,
        "ai_confidence": current.overall_ai_confidence,
        "understanding_score": current.overall_understanding_score,
        "section_scores": [
            {
                "section_name": s.section_name,
                "ai_confidence": s.ai_confidence,
                "understanding_score": s.understanding_score,
                "question_count": s.question_count,
                "estimated_minutes": s.estimated_minutes,
                "why_low": s.why_low,
                "confidence_level": s.confidence_level,
                "locked": s.lock_status.value == "locked",
                "gdoc_heading_id": s.gdoc_heading_id,
            }
            for s in current.section_scores
        ],
        "readiness": readiness,
        "prd_approved": state.prd_approved,
        "review_mode": current.review_session.review_mode if current.review_session else "detailed",
        "quick_questions": current.review_session.quick_questions if current.review_session else [],
        "quick_responses": current.review_session.quick_responses if current.review_session else {},
    }


@review_router.get("/{project_id}/questionnaire")
async def get_questionnaire(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """Get the dynamic, version-aware questionnaire."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    questionnaire = service.get_questionnaire(state)

    current = state.get_current_prd_version()
    return {
        "project_id": project_id,
        "version": current.version if current else 0,
        "sections": questionnaire,
        "locked_sections": state.get_locked_sections(),
    }


@review_router.post("/{project_id}/questionnaire/{section_name}")
async def submit_section_response(
    project_id: str,
    section_name: str,
    submission: QuestionnaireSubmission,
    token: Optional[str] = Query(None),
):
    """Submit answers for a single questionnaire section."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    result = service.submit_questionnaire_response(
        state=state,
        section_name=section_name,
        responses=submission.responses,
    )

    if result is None:
        raise HTTPException(status_code=400, detail="No active review session")

    # Persist updated state to disk
    orchestrator = get_orchestrator()
    orchestrator._save_state(state)

    return {"status": "ok", **result}


@review_router.post("/{project_id}/feedback/upload")
async def upload_feedback_file(
    project_id: str,
    file: UploadFile = File(...),
    token: Optional[str] = Query(None),
):
    """Upload a feedback file (PDF/DOCX/TXT/MD)."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    # Validate file type
    allowed_types = {"pdf", "docx", "doc", "txt", "md", "markdown"}
    ext = (file.filename or "unknown.txt").rsplit(".", 1)[-1].lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(allowed_types)}",
        )

    # Save to workspace
    feedback_dir = os.path.join(state.workspace_path, ".state", "feedback")
    os.makedirs(feedback_dir, exist_ok=True)
    filepath = os.path.join(feedback_dir, file.filename or "feedback.txt")

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    # Determine MIME type
    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain",
        "md": "text/markdown",
        "markdown": "text/markdown",
    }

    result = service.upload_feedback(
        state=state,
        filename=file.filename or "feedback.txt",
        filepath=filepath,
        file_type=ext,
        mime_type=mime_map.get(ext, "application/octet-stream"),
    )

    if result is None:
        raise HTTPException(status_code=400, detail="No active review session")

    # Persist updated state to disk
    orchestrator = get_orchestrator()
    orchestrator._save_state(state)

    return {"status": "ok", **result}


@review_router.post("/{project_id}/feedback/text")
async def submit_text_feedback(
    project_id: str,
    submission: FeedbackTextSubmission,
    token: Optional[str] = Query(None),
):
    """Submit pasted text feedback."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    result = service.submit_feedback_text(
        state=state,
        feedback_text=submission.feedback_text,
    )

    if result is None:
        raise HTTPException(status_code=400, detail="No active review session")

    # Persist updated state to disk
    orchestrator = get_orchestrator()
    orchestrator._save_state(state)

    return {"status": "ok", **result}


@review_router.get("/{project_id}/understanding")
async def get_understanding_scores(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """Get current understanding scores with 'why is this low?' explanations."""
    _validate_token(project_id, token)
    state = _get_state(project_id)

    current = state.get_current_prd_version()
    if not current:
        raise HTTPException(status_code=404, detail="No PRD version found")

    return {
        "version": current.version,
        "overall_ai_confidence": current.overall_ai_confidence,
        "overall_understanding_score": current.overall_understanding_score,
        "sections": [
            {
                "section_name": s.section_name,
                "ai_confidence": s.ai_confidence,
                "understanding_score": s.understanding_score,
                "why_low": s.why_low,
                "confidence_level": s.confidence_level,
                "locked": s.lock_status.value == "locked",
            }
            for s in current.section_scores
        ],
    }


@review_router.get("/{project_id}/impact-preview")
async def get_impact_preview(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """Preview what will change if we regenerate the PRD."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    preview = service.get_impact_preview(state)
    return {"project_id": project_id, "impact": preview}


from pydantic import BaseModel

class QuickSubmission(BaseModel):
    responses: dict[str, str]


@review_router.post("/{project_id}/quick")
async def submit_quick_mode(
    project_id: str,
    submission: QuickSubmission,
    token: Optional[str] = Query(None),
):
    """Submit responses in Quick Mode and trigger automatic PRD regeneration."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    success = service.submit_quick_responses(state, submission.responses)
    if not success:
        raise HTTPException(status_code=400, detail="No active review session")

    # Persist updated state to disk
    orchestrator = get_orchestrator()
    orchestrator._save_state(state)

    # Trigger automatic PRD regeneration
    success_trigger = await orchestrator.submit_review_decision(
        project_id=project_id,
        decision="regenerate",
    )
    if not success_trigger:
        raise HTTPException(
            status_code=500,
            detail="Failed to trigger PRD regeneration. Ensure review is in progress."
        )

    return {
        "status": "ok",
        "message": f"Quick responses saved and PRD v{state.current_prd_version + 1} regeneration started",
    }


@review_router.post("/{project_id}/regenerate")
async def regenerate_prd(
    project_id: str,
    req: RegenerateRequest,
    token: Optional[str] = Query(None),
):
    """
    Trigger PRD regeneration (creates next version).
    Client must confirm after seeing impact preview.
    """
    _validate_token(project_id, token)
    state = _get_state(project_id)

    if not req.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")

    # Signal the orchestrator to regenerate
    # This resolves the pending review future with "regenerate" decision
    orchestrator = get_orchestrator()
    success = await orchestrator.submit_review_decision(
        project_id=project_id,
        decision="regenerate",
    )

    if not success:
        raise HTTPException(status_code=400, detail="No pending review decision")

    return {
        "status": "ok",
        "message": f"PRD v{state.current_prd_version + 1} regeneration started",
    }


@review_router.post("/{project_id}/approve")
async def approve_prd(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """Approve the current PRD version and proceed to Phase 3."""
    _validate_token(project_id, token)

    orchestrator = get_orchestrator()
    success = await orchestrator.submit_review_decision(
        project_id=project_id,
        decision="approved",
    )

    if not success:
        raise HTTPException(status_code=400, detail="No pending review decision")

    return {"status": "ok", "message": "PRD approved — proceeding to Design phase"}


@review_router.get("/{project_id}/history")
async def get_review_history(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """Get all review sessions with stats."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    return {
        "project_id": project_id,
        "history": service.get_review_history(state),
    }


@review_router.get("/{project_id}/versions")
async def list_prd_versions(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """List all PRD versions with Google Doc URLs."""
    _validate_token(project_id, token)
    state = _get_state(project_id)

    return {
        "project_id": project_id,
        "versions": [
            {
                "version": v.version,
                "status": v.status.value,
                "created_at": v.created_at.isoformat(),
                "gdoc_url": v.gdoc_url,
                "ai_confidence": v.overall_ai_confidence,
                "understanding_score": v.overall_understanding_score,
                "changes_count": len(v.changes_from_previous),
            }
            for v in state.prd_versions
        ],
    }


@review_router.get("/{project_id}/versions/{version}")
async def get_prd_version(
    project_id: str,
    version: int,
    token: Optional[str] = Query(None),
):
    """Get detailed info for a specific PRD version."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    details = service.get_version_details(state, version)
    if not details:
        raise HTTPException(status_code=404, detail=f"PRD version {version} not found")

    return details


@review_router.post("/{project_id}/sections/{section_name}/lock")
async def lock_section(
    project_id: str,
    section_name: str,
    req: SectionLockRequest,
    token: Optional[str] = Query(None),
):
    """Lock an approved section to prevent modification."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    success = service.lock_section(state, section_name, req.locked_by)
    if not success:
        raise HTTPException(status_code=400, detail="Section not found or cannot be locked")

    # Persist updated state to disk
    orchestrator = get_orchestrator()
    orchestrator._save_state(state)

    return {"status": "ok", "section": section_name, "locked": True}


@review_router.delete("/{project_id}/sections/{section_name}/lock")
async def unlock_section(
    project_id: str,
    section_name: str,
    token: Optional[str] = Query(None),
):
    """Unlock a previously locked section."""
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    success = service.unlock_section(state, section_name)
    if not success:
        raise HTTPException(status_code=400, detail="Section not found")

    # Persist updated state to disk
    orchestrator = get_orchestrator()
    orchestrator._save_state(state)

    return {"status": "ok", "section": section_name, "locked": False}


# ── Client Dashboard Endpoints ──

@client_router.get("/{project_id}")
async def get_client_dashboard(
    project_id: str,
    token: Optional[str] = Query(None),
):
    """
    Client-facing dashboard showing overall project progress,
    PRD versions, timeline, and pending decisions.
    """
    _validate_token(project_id, token)
    state = _get_state(project_id)
    service = _get_review_service()

    from src.orchestrator.pipeline_def import PIPELINE_PHASES

    # Build phase progress summary
    phases_summary = []
    for phase_def in PIPELINE_PHASES:
        phase_state = state.get_phase(phase_def.id)
        phases_summary.append({
            "id": phase_def.id,
            "name": phase_def.name,
            "icon": phase_def.icon,
            "status": phase_state.status.value if hasattr(phase_state.status, 'value') else phase_state.status,
            "progress": phase_state.progress,
        })

    # PRD versions summary
    versions_summary = [
        {
            "version": v.version,
            "status": v.status.value,
            "created_at": v.created_at.isoformat(),
            "ai_confidence": v.overall_ai_confidence,
            "understanding_score": v.overall_understanding_score,
            "gdoc_url": v.gdoc_url,
        }
        for v in state.prd_versions
    ]

    # Pending decisions
    pending = []
    for phase_def in PIPELINE_PHASES:
        phase_state = state.get_phase(phase_def.id)
        status_val = phase_state.status.value if hasattr(phase_state.status, 'value') else phase_state.status
        if status_val == "waiting":
            pending.append({
                "phase_id": phase_def.id,
                "phase_name": phase_def.name,
                "description": phase_def.description,
            })

    # Check if PRD review is active
    current_prd = state.get_current_prd_version()
    review_active = current_prd is not None and not state.prd_approved

    return {
        "project_id": project_id,
        "project_name": state.project_name,
        "current_phase": state.current_phase,
        "total_phases": 14,
        "phases": phases_summary,
        "prd_versions": versions_summary,
        "current_prd_version": state.current_prd_version,
        "prd_approved": state.prd_approved,
        "review_active": review_active,
        "pending_decisions": pending,
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "jira_epic_key": state.jira_epic_key,
        "staging_url": state.staging_url,
        "production_url": state.production_url,
    }
