"""
Aikyam Multi-Agent Pipeline — Data Models
Pydantic models for the pipeline state, projects, phases, and API payloads.
Includes PRD versioning, review sessions, and understanding scoring.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──

class PhaseStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting for human approval
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class AgentType(str, Enum):
    REQUIREMENTS = "requirements"
    HUMAN = "human"
    JIRA = "jira"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    QA = "qa"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    DOCS = "docs"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewSessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    READY_FOR_REDRAFT = "ready_for_redraft"


class PRDVersionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SectionLockStatus(str, Enum):
    UNLOCKED = "unlocked"
    LOCKED = "locked"  # ≥95% understanding + explicit client approval


# ── PRD Versioning & Review Models ──

class ChangeEvidence(BaseModel):
    """Traces a PRD change back to its source for auditability."""
    change_description: str                 # What changed in the PRD
    source_type: str                        # "questionnaire" | "feedback_file" | "client_comment" | "ai_inference"
    source_reference: str                   # e.g., "Questionnaire #14", "Feedback Document Page 3"
    section_affected: str                   # Which PRD section was changed
    change_type: str = "modified"           # "added" | "modified" | "removed" | "clarified"


class SectionUnderstanding(BaseModel):
    """Understanding score for a single PRD section.
    
    Two-phase scoring:
    1. AI Confidence — computed when PRD is generated (before client interaction)
    2. Understanding Score — computed after client answers questionnaire
    """
    section_name: str
    section_content_preview: str = ""       # First ~200 chars of the section
    gdoc_heading_id: Optional[str] = None   # Heading ID for direct Google Doc redirection
    ai_confidence: float = 0.0              # 0-100, AI's own estimate of ambiguity
    understanding_score: Optional[float] = None  # 0-100, actual score after client validation
    question_count: int = 0
    estimated_minutes: int = 0
    questions: list[dict[str, Any]] = Field(default_factory=list)
    # "Why is this score low?" — specific reasons for low confidence/understanding
    why_low: list[str] = Field(default_factory=list)
    confidence_level: str = "medium"        # "high" | "medium" | "low"
    lock_status: SectionLockStatus = SectionLockStatus.UNLOCKED
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None         # User who locked the section


class ReviewSession(BaseModel):
    """Tracks a single review cycle for a PRD version.
    
    Architecture: ReviewSession belongs to PRDVersion (not Project).
    Each PRD version has exactly one review session.
    """
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prd_version: int
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    # Questionnaire responses keyed by section name
    questionnaire_responses: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    completed_sections: list[str] = Field(default_factory=list)
    # Feedback files uploaded during this session
    feedback_files: list[dict[str, str]] = Field(default_factory=list)  # [{filename, path, type, drive_url}]
    feedback_text: Optional[str] = None
    # Analysis results
    understanding_analysis: Optional[dict[str, Any]] = None
    new_requirements: int = 0
    clarifications: int = 0
    conflicts: int = 0
    enhancements: int = 0
    # Evidence for changes (populated when next version is generated)
    change_evidence: list[ChangeEvidence] = Field(default_factory=list)
    status: ReviewSessionStatus = ReviewSessionStatus.IN_PROGRESS
    # Quick mode fields
    quick_questions: list[dict[str, Any]] = Field(default_factory=list)
    quick_responses: dict[str, str] = Field(default_factory=dict)
    review_mode: str = "detailed"


class PRDVersion(BaseModel):
    """A single versioned PRD snapshot.
    
    Lifecycle:
    1. PRD generated → status=active, ai_confidence computed
    2. Client reviews → understanding_scores populated via review_session
    3. New version generated → status=archived, Google Docs tab archived
    """
    version: int                            # 1, 2, 3, ...
    content: str                            # Full PRD markdown
    created_at: datetime = Field(default_factory=datetime.utcnow)
    gdoc_url: Optional[str] = None          # Google Docs tab URL
    gdoc_tab_id: Optional[str] = None       # Tab ID for archival
    # Scoring
    overall_ai_confidence: float = 0.0      # Before client interaction
    overall_understanding_score: Optional[float] = None  # After client validation
    section_scores: list[SectionUnderstanding] = Field(default_factory=list)
    # Review session for this version
    review_session: Optional[ReviewSession] = None
    # Impact summary (what changed from previous version)
    changes_from_previous: list[str] = Field(default_factory=list)
    change_evidence: list[ChangeEvidence] = Field(default_factory=list)
    status: PRDVersionStatus = PRDVersionStatus.ACTIVE


class ReviewToken(BaseModel):
    """Signed, expiring token for questionnaire access via Slack links."""
    token: str
    project_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    used: bool = False


# ── Log Entry ──

class PhaseLog(BaseModel):
    """A single log entry from an agent execution."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = "info"  # info, success, warn, error
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Phase Definition ──

class PhaseDefinition(BaseModel):
    """Static definition of a pipeline phase."""
    id: int
    name: str
    agent: AgentType
    icon: str
    description: str
    outputs: list[str] = Field(default_factory=list)
    logs_to_jira: bool = False
    max_retries: int = 0  # 0 = no retry loop


class PhaseState(BaseModel):
    """Runtime state of a pipeline phase."""
    phase_id: int
    status: PhaseStatus = PhaseStatus.IDLE
    progress: int = 0  # 0-100
    logs: list[PhaseLog] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    retry_count: int = 0
    output_artifacts: dict[str, str] = Field(default_factory=dict)  # name -> path/content
    error_message: Optional[str] = None
    tokens_used: int = 0
    cost_usd: float = 0.0

    def add_log(self, level: str, message: str, **metadata: Any) -> None:
        """Add a log entry to this phase."""
        self.logs.append(PhaseLog(level=level, message=message, metadata=metadata))

    @property
    def duration_display(self) -> Optional[str]:
        """Human-readable duration string."""
        if self.duration_seconds is None:
            return None
        m, s = divmod(int(self.duration_seconds), 60)
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"


# ── Pipeline State (LangGraph state dict) ──

class PipelineState(BaseModel):
    """
    Full pipeline state — this is what flows through LangGraph.
    Each field is updated by the corresponding agent node.
    """
    # ── Project Metadata ──
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str = ""
    raw_requirements: str = ""
    workspace_path: str = ""

    # ── Phase States ──
    phases: dict[int, PhaseState] = Field(default_factory=dict)
    current_phase: int = 1

    # ── Document Artifacts ──
    prd: Optional[str] = None
    pdd: Optional[str] = None
    execution_plan: Optional[str] = None
    api_spec: Optional[str] = None
    db_schema: Optional[str] = None
    open_questions: list[str] = Field(default_factory=list)

    # ── Jira ──
    jira_epic_key: Optional[str] = None
    jira_tasks: list[dict[str, Any]] = Field(default_factory=list)

    # ── Development ──
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    code_files: list[str] = Field(default_factory=list)
    unit_test_results: Optional[dict[str, Any]] = None

    # ── Code Review ──
    review_verdict: Optional[str] = None  # APPROVED / CHANGES_REQUESTED
    review_feedback: Optional[str] = None
    review_attempt_count: int = 0

    # ── QA ──
    test_cases_excel_path: Optional[str] = None
    test_results: Optional[dict[str, Any]] = None
    qa_attempt_count: int = 0

    # ── Security ──
    security_report: Optional[dict[str, Any]] = None
    security_passed: bool = False

    # ── Deployment ──
    staging_url: Optional[str] = None
    production_url: Optional[str] = None
    smoke_test_passed: bool = False

    # ── Human Approvals ──
    prd_approved: bool = False
    scope_approved: bool = False
    production_approved: bool = False
    human_feedback: Optional[str] = None

    # ── PRD Versioning ──
    prd_versions: list[PRDVersion] = Field(default_factory=list)
    current_prd_version: int = 0
    prd_review_slack_thread_ts: Optional[str] = None  # Thread for all review notifications

    # ── Observability ──
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def get_phase(self, phase_id: int) -> PhaseState:
        """Get or create a phase state."""
        if phase_id not in self.phases:
            self.phases[phase_id] = PhaseState(phase_id=phase_id)
        return self.phases[phase_id]

    def advance_phase(self, to_phase: int) -> None:
        """Move the pipeline to the next phase."""
        self.current_phase = to_phase

    # ── PRD Version Helpers ──

    def get_current_prd_version(self) -> Optional[PRDVersion]:
        """Get the currently active PRD version."""
        for v in self.prd_versions:
            if v.status == PRDVersionStatus.ACTIVE:
                return v
        return None

    def get_prd_version(self, version: int) -> Optional[PRDVersion]:
        """Get a specific PRD version by number."""
        for v in self.prd_versions:
            if v.version == version:
                return v
        return None

    def get_current_review_session(self) -> Optional[ReviewSession]:
        """Get the review session for the current active PRD version."""
        current = self.get_current_prd_version()
        if current:
            return current.review_session
        return None

    def get_locked_sections(self) -> list[str]:
        """Get names of all sections that are locked (approved ≥95%)."""
        current = self.get_current_prd_version()
        if not current:
            return []
        return [
            s.section_name for s in current.section_scores
            if s.lock_status == SectionLockStatus.LOCKED
        ]


# ── API Request/Response Models ──

class CreateProjectRequest(BaseModel):
    """Request payload to create a new project."""
    name: str
    raw_requirements: str
    llm_provider: Optional[str] = None  # Override default LLM for this project


class ProjectSummary(BaseModel):
    """Summary of a project for listing."""
    id: str
    name: str
    status: ProjectStatus
    current_phase: int
    total_phases: int = 14
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    created_at: Optional[datetime] = None
    jira_epic_key: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Request payload for human approval/rejection."""
    project_id: str
    phase_id: int
    decision: ApprovalDecision
    feedback: Optional[str] = None


class PhaseDetail(BaseModel):
    """Detailed information about a single phase."""
    phase_id: int
    name: str
    agent: AgentType
    icon: str
    description: str
    status: PhaseStatus
    progress: int
    logs: list[PhaseLog]
    outputs: list[str]
    output_artifacts: dict[str, str]
    logs_to_jira: bool
    duration: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0


class WebSocketMessage(BaseModel):
    """Message sent over WebSocket for real-time updates."""
    type: str  # phase_update, log, approval_request, pipeline_complete, error
    project_id: str
    phase_id: Optional[int] = None
    data: dict[str, Any] = Field(default_factory=dict)


# ── Review Flow API Models ──

class QuestionnaireSubmission(BaseModel):
    """Client submission for a single questionnaire section."""
    section_name: str
    responses: list[dict[str, Any]]  # [{question_id, answer, confidence}]


class FeedbackTextSubmission(BaseModel):
    """Client text feedback submission."""
    feedback_text: str


class SectionLockRequest(BaseModel):
    """Request to lock/unlock a PRD section."""
    locked_by: str = "client"


class RegenerateRequest(BaseModel):
    """Request to regenerate the PRD (create next version)."""
    confirm: bool = True  # Client must confirm after seeing impact preview

