"""
Aikyam Multi-Agent Pipeline — API Routes
REST + WebSocket endpoints for the dashboard frontend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.integrations.llm_provider import get_llm_manager
from src.models.project_state import ApprovalRequest, CreateProjectRequest
from src.orchestrator.orchestrator import get_orchestrator
from src.orchestrator.pipeline_def import PHASE_MAP, PIPELINE_PHASES

logger = logging.getLogger(__name__)
router = APIRouter()


# ── WebSocket Connection Manager ──

class ConnectionManager:
    """Manages WebSocket connections per project."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}  # project_id -> connections
        self._global: list[WebSocket] = []  # subscribed to all projects

    async def connect(self, ws: WebSocket, project_id: str | None = None):
        await ws.accept()
        if project_id:
            self._connections.setdefault(project_id, []).append(ws)
        else:
            self._global.append(ws)

    def disconnect(self, ws: WebSocket, project_id: str | None = None):
        if project_id and project_id in self._connections:
            self._connections[project_id] = [c for c in self._connections[project_id] if c != ws]
        self._global = [c for c in self._global if c != ws]

    async def broadcast(self, project_id: str, message: dict):
        """Send message to all connections for this project + global listeners."""
        targets = self._connections.get(project_id, []) + self._global
        disconnected = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        # Clean up disconnected
        for ws in disconnected:
            self.disconnect(ws, project_id)


manager = ConnectionManager()


# ── REST Endpoints ──

@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy", "service": "aikyam-pipeline"}


@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    """Create a new project and start the pipeline."""
    orchestrator = get_orchestrator()

    # Wire up WebSocket broadcasting
    orchestrator.set_broadcast_function(manager.broadcast)

    state = await orchestrator.start_pipeline(
        project_name=req.name,
        raw_requirements=req.raw_requirements,
    )

    return {
        "id": state.project_id,
        "name": state.project_name,
        "status": "running",
        "current_phase": state.current_phase,
        "message": f"Pipeline started for '{state.project_name}'",
    }


@router.get("/projects")
async def list_projects():
    """List all pipelines."""
    orchestrator = get_orchestrator()
    return {"projects": orchestrator.list_pipelines()}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get detailed project state."""
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline(project_id)
    if not state:
        return {"error": "Project not found"}, 404

    # Build response with phase details
    phases = []
    for phase_def in PIPELINE_PHASES:
        phase_state = state.get_phase(phase_def.id)
        phases.append({
            "id": phase_def.id,
            "name": phase_def.name,
            "agent": phase_def.agent.value,
            "icon": phase_def.icon,
            "description": phase_def.description,
            "status": phase_state.status,
            "progress": phase_state.progress,
            "logs": [
                {
                    "time": log.timestamp.strftime("%H:%M:%S"),
                    "level": log.level,
                    "message": log.message,
                }
                for log in phase_state.logs
            ],
            "outputs": phase_def.outputs,
            "output_artifacts": phase_state.output_artifacts,
            "logs_to_jira": phase_def.logs_to_jira,
            "duration": phase_state.duration_display,
            "retry_count": phase_state.retry_count,
            "max_retries": phase_def.max_retries,
            "tokens_used": phase_state.tokens_used,
            "cost_usd": phase_state.cost_usd,
        })

    return {
        "id": state.project_id,
        "name": state.project_name,
        "raw_requirements": state.raw_requirements,
        "status": "running" if state.current_phase <= 14 else "completed",
        "current_phase": state.current_phase,
        "phases": phases,
        "total_tokens": state.total_tokens,
        "total_cost_usd": state.total_cost_usd,
        "jira_epic_key": state.jira_epic_key,
        "git_repo": state.git_repo,
        "staging_url": state.staging_url,
        "production_url": state.production_url,
        "latest_prd_gdoc_url": state.get_current_prd_version().gdoc_url if state.get_current_prd_version() else None,
        "created_at": state.started_at.isoformat() if state.started_at else None,
    }


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete / clear a project from memory."""
    orchestrator = get_orchestrator()
    success = orchestrator.delete_pipeline(project_id)
    if success:
        return {"status": "ok", "message": f"Project {project_id} deleted successfully"}
    return {"status": "error", "message": "Project not found"}, 404


@router.post("/projects/{project_id}/approve")
async def submit_approval(project_id: str, req: ApprovalRequest):
    """Submit approval/rejection for a human checkpoint phase."""
    orchestrator = get_orchestrator()
    success = await orchestrator.submit_approval(
        project_id=project_id,
        phase_id=req.phase_id,
        decision=req.decision.value,
        feedback=req.feedback,
        user="dashboard",
    )
    if success:
        return {"status": "ok", "message": f"Phase {req.phase_id} {req.decision.value}"}
    return {"status": "error", "message": "Phase not in waiting state or project not found"}


@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(project_id: str):
    """List all output artifacts for a project (across all phases)."""
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline(project_id)
    if not state:
        return {"error": "Project not found"}, 404

    artifacts = []
    for phase_id, phase_state in state.phases.items():
        for name, path in phase_state.output_artifacts.items():
            # Skip gdoc URL entries — they'll be included as metadata
            if name.endswith("_gdoc_url"):
                continue
            import os
            gdoc_url = phase_state.output_artifacts.get(f"{name}_gdoc_url", "")
            artifacts.append({
                "name": name,
                "phase_id": phase_id,
                "path": path,
                "exists": os.path.isfile(path),
                "google_doc_url": gdoc_url,
            })
    return {"artifacts": artifacts}


@router.get("/projects/{project_id}/artifacts/{artifact_name}")
async def get_artifact(project_id: str, artifact_name: str):
    """Get the content of a specific artifact by name."""
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline(project_id)
    if not state:
        return {"error": "Project not found"}, 404

    # Search across all phases for the artifact
    for phase_state in state.phases.values():
        if artifact_name in phase_state.output_artifacts:
            filepath = phase_state.output_artifacts[artifact_name]
            gdoc_url = phase_state.output_artifacts.get(f"{artifact_name}_gdoc_url", "")
            import os
            if os.path.isfile(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                return {
                    "name": artifact_name,
                    "content": content,
                    "path": filepath,
                    "google_doc_url": gdoc_url,
                }
            else:
                return {"error": f"Artifact file not found on disk: {filepath}"}, 404

    return {"error": f"Artifact '{artifact_name}' not found"}, 404


@router.get("/projects/{project_id}/phases/{phase_id}/logs")
async def get_phase_logs(project_id: str, phase_id: int):
    """Get logs for a specific phase."""
    orchestrator = get_orchestrator()
    state = orchestrator.get_pipeline(project_id)
    if not state:
        return {"error": "Project not found"}

    phase = state.get_phase(phase_id)
    return {
        "phase_id": phase_id,
        "status": phase.status,
        "logs": [
            {
                "time": log.timestamp.strftime("%H:%M:%S"),
                "level": log.level,
                "message": log.message,
            }
            for log in phase.logs
        ],
    }


@router.get("/llm/providers")
async def list_llm_providers():
    """List configured LLM providers."""
    llm = get_llm_manager()
    return {"providers": llm.list_providers()}


@router.get("/llm/health/{provider}")
async def check_llm_health(provider: str):
    """Health check for a specific LLM provider."""
    llm = get_llm_manager()
    return llm.health_check(provider)


@router.get("/pipeline/definition")
async def get_pipeline_definition():
    """Get the static pipeline phase definitions."""
    return {
        "phases": [
            {
                "id": p.id,
                "name": p.name,
                "agent": p.agent.value,
                "icon": p.icon,
                "description": p.description,
                "outputs": p.outputs,
                "logs_to_jira": p.logs_to_jira,
                "max_retries": p.max_retries,
            }
            for p in PIPELINE_PHASES
        ]
    }


# ── WebSocket Endpoint ──

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint for real-time pipeline updates.
    Query param: ?project_id=xxx to subscribe to a specific project.
    Without project_id, subscribes to all projects.
    """
    project_id = ws.query_params.get("project_id")
    await manager.connect(ws, project_id)
    logger.info("WebSocket connected (project: %s)", project_id or "global")

    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await ws.receive_text()
            # Could handle client-side actions here (e.g., approval from dashboard)
            try:
                import json
                msg = json.loads(data)
                if msg.get("type") == "approve":
                    orchestrator = get_orchestrator()
                    await orchestrator.submit_approval(
                        project_id=msg["project_id"],
                        phase_id=msg["phase_id"],
                        decision=msg["decision"],
                        feedback=msg.get("feedback"),
                        user="websocket",
                    )
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws, project_id)
        logger.info("WebSocket disconnected (project: %s)", project_id or "global")
