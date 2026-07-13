"""
Aikyam Multi-Agent Pipeline — Orchestrator
Controls the 14-phase pipeline execution flow with:
- Sequential phase execution
- Human-in-the-loop checkpoints (Slack)
- Dev ↔ Review feedback loop (up to 3 retries)
- Real-time WebSocket broadcasting
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from src.agents.base_agent import BaseAgent
from src.agents.code_review_agent import CodeReviewAgent
from src.agents.deployment_agent import DeploymentAgent
from src.agents.developer_agent import DeveloperAgent
from src.agents.documentation_agent import DocumentationAgent
from src.agents.jira_agent import JiraTaskAgent
from src.agents.qa_agent import QAAgent
from src.agents.requirements_agent import RequirementsAgent
from src.agents.security_agent import SecurityAgent
from src.config import get_settings
from src.integrations.slack_handler import get_slack_handler
from src.models.project_state import (
    PipelineState,
    PhaseStatus,
    ProjectStatus,
)
from src.orchestrator.pipeline_def import PHASE_MAP, PIPELINE_PHASES

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Main pipeline controller.
    Runs phases sequentially, handles human checkpoints via Slack,
    manages the Dev ↔ Review feedback loop, and broadcasts updates.
    """

    def __init__(self):
        self.settings = get_settings()
        self._agents: dict[str, BaseAgent] = {
            "requirements": RequirementsAgent(),
            "jira": JiraTaskAgent(),
            "developer": DeveloperAgent(),
            "code_review": CodeReviewAgent(),
            "qa": QAAgent(),
            "security": SecurityAgent(),
            "deployment": DeploymentAgent(),
            "documentation": DocumentationAgent(),
        }
        self._running_pipelines: dict[str, PipelineState] = {}
        self._pending_approvals: dict[str, asyncio.Future] = {}  # "project_id|phase_id" -> Future
        self._pending_review_decisions: dict[str, asyncio.Future] = {}  # project_id -> Future
        self._broadcast_fn: Optional[Callable] = None
        
        # Load persisted states from disk
        self._load_states()

    def set_broadcast_function(self, fn: Callable) -> None:
        """Set the function to call for broadcasting real-time updates."""
        self._broadcast_fn = fn

    async def _broadcast(self, project_id: str, phase_id: int, event_type: str, data: dict) -> None:
        """Broadcast a pipeline event to connected WebSocket clients and persist state."""
        # Save state to disk on any broadcast/update
        state = self.get_pipeline(project_id)
        if state:
            self._save_state(state)

        if self._broadcast_fn:
            msg = {
                "type": event_type,
                "project_id": project_id,
                "phase_id": phase_id,
                "data": data,
            }
            try:
                await self._broadcast_fn(project_id, msg)
            except Exception as e:
                logger.error("Broadcast failed: %s", e)

    def get_pipeline(self, project_id: str) -> Optional[PipelineState]:
        """Get a running pipeline by project ID."""
        return self._running_pipelines.get(project_id)

    def delete_pipeline(self, project_id: str) -> bool:
        """Delete/clear a pipeline by project ID from memory and disk."""
        if project_id in self._running_pipelines:
            state = self._running_pipelines[project_id]
            try:
                state_file = os.path.join(state.workspace_path, ".state", "pipeline_state.json")
                if os.path.exists(state_file):
                    os.remove(state_file)
            except Exception as e:
                logger.warning("Failed to delete state file: %s", e)
                
            del self._running_pipelines[project_id]
            logger.info("Pipeline %s deleted from memory and disk", project_id)
            return True
        return False

    def _save_state(self, state: PipelineState) -> None:
        """Save a pipeline state to disk."""
        try:
            if not state.workspace_path:
                return
            state_file = os.path.join(state.workspace_path, ".state", "pipeline_state.json")
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as f:
                f.write(state.model_dump_json(indent=2))
        except Exception as e:
            logger.warning("Failed to save state for project %s: %s", state.project_id[:8], e)

    def _load_states(self) -> None:
        """Load all saved pipeline states from disk."""
        try:
            workspace_dir = self.settings.workspace_dir
            if not os.path.exists(workspace_dir):
                return

            loaded_count = 0
            for folder in os.listdir(workspace_dir):
                folder_path = os.path.join(workspace_dir, folder)
                if not os.path.isdir(folder_path):
                    continue

                state_file = os.path.join(folder_path, ".state", "pipeline_state.json")
                if os.path.exists(state_file):
                    try:
                        with open(state_file, "r", encoding="utf-8") as f:
                            json_str = f.read()
                        state = PipelineState.model_validate_json(json_str)
                        self._running_pipelines[state.project_id] = state
                        loaded_count += 1
                    except Exception as ex:
                        logger.warning("Failed to load state from %s: %s", state_file, ex)

            if loaded_count > 0:
                logger.info("Loaded %d project states from disk", loaded_count)
        except Exception as e:
            logger.error("Failed to load states: %s", e)

    def list_pipelines(self) -> list[dict[str, Any]]:
        """List all pipelines with summary info."""
        result = []
        for pid, state in self._running_pipelines.items():
            completed = sum(1 for p in state.phases.values() if p.status == "success")
            result.append({
                "id": state.project_id,
                "name": state.project_name,
                "status": "running" if state.current_phase <= 14 else "completed",
                "current_phase": state.current_phase,
                "total_phases": 14,
                "completed_phases": completed,
                "total_tokens": state.total_tokens,
                "total_cost_usd": state.total_cost_usd,
                "jira_epic_key": state.jira_epic_key,
                "created_at": state.started_at.isoformat() if state.started_at else None,
            })
        return result

    async def start_pipeline(self, project_name: str, raw_requirements: str) -> PipelineState:
        """
        Initialize and start a new pipeline execution.
        Returns immediately; runs phases asynchronously.
        """
        state = PipelineState(
            project_id=str(uuid.uuid4()),
            project_name=project_name,
            raw_requirements=raw_requirements,
            started_at=datetime.utcnow(),
        )

        # Create workspace
        workspace = os.path.join(
            str(self.settings.workspace_dir),
            state.project_id[:8],
        )
        os.makedirs(workspace, exist_ok=True)
        os.makedirs(os.path.join(workspace, ".state"), exist_ok=True)
        state.workspace_path = workspace

        # Initialize all phase states
        for phase_def in PIPELINE_PHASES:
            phase_state = state.get_phase(phase_def.id)

        self._running_pipelines[state.project_id] = state
        self._save_state(state)

        logger.info(
            "Pipeline started: %s (id: %s, workspace: %s)",
            project_name, state.project_id[:8], workspace,
        )

        # Launch pipeline execution in background
        asyncio.create_task(self._run_pipeline(state))

        return state

    async def _run_pipeline(self, state: PipelineState) -> None:
        """Execute the full pipeline sequentially."""
        try:
            # Phase 1: Requirements Analysis (generates PRD v1)
            await self._execute_agent_phase(state, 1, "requirements")

            # Phase 1.5-2: PRD Review Loop
            # Creates versioned PRD, computes AI confidence, sends for review
            await self._prd_review_loop(state)

            # Phase 3: Design & Architecture
            await self._execute_agent_phase(state, 3, "requirements")

            # Phase 4: Human Checkpoint — Approve Scope
            phase3 = state.get_phase(3)
            pdd_gdoc_url = phase3.output_artifacts.get("pdd_gdoc_url", "")
            plan_gdoc_url = phase3.output_artifacts.get("execution_plan_gdoc_url", "")
            api_gdoc_url = phase3.output_artifacts.get("api_spec_gdoc_url", "")
            db_gdoc_url = phase3.output_artifacts.get("db_schema_gdoc_url", "")

            doc_urls = {}
            links = []
            if pdd_gdoc_url:
                doc_urls["pdd"] = pdd_gdoc_url
                links.append(f"📄 *<{pdd_gdoc_url}|View PDD in Google Docs>*")
            if plan_gdoc_url:
                doc_urls["execution_plan"] = plan_gdoc_url
                links.append(f"📅 *<{plan_gdoc_url}|View Execution Plan in Google Docs>*")
            if api_gdoc_url:
                doc_urls["api_spec"] = api_gdoc_url
                links.append(f"🔌 *<{api_gdoc_url}|View API Spec in Google Docs>*")
            if db_gdoc_url:
                doc_urls["db_schema"] = db_gdoc_url
                links.append(f"🗄️ *<{db_gdoc_url}|View Database Schema in Google Docs>*")

            links_text = "\n".join(links) + "\n\n" if links else ""

            design_summary = (
                f"PDD, API Spec, DB Schema, and Execution Plan generated.\n\n"
                f"{links_text}"
                f"Review the technical scope and approve to proceed."
            )
            await self._human_checkpoint(
                state, 4,
                "Approve Technical Scope",
                design_summary,
                approval_key="scope_approved",
                doc_urls=doc_urls if doc_urls else None,
            )

            # Phase 5: Jira Task Creation
            await self._execute_agent_phase(state, 5, "jira")

            # Phase 6-7: Dev ↔ Review Loop (up to 3 iterations)
            max_dev_iterations = 3
            for iteration in range(max_dev_iterations):
                # Phase 6: Development
                await self._execute_agent_phase(state, 6, "developer")

                # Phase 7: Code Review
                await self._execute_agent_phase(state, 7, "code_review")

                if state.review_verdict == "APPROVED":
                    break
                elif iteration < max_dev_iterations - 1:
                    logger.info(
                        "Code review: CHANGES_REQUESTED — starting iteration %d/%d",
                        iteration + 2, max_dev_iterations,
                    )
                    # Reset phases for retry
                    state.get_phase(6).status = "idle"
                    state.get_phase(6).progress = 0
                    state.get_phase(7).status = "idle"
                    state.get_phase(7).progress = 0
                else:
                    logger.warning("Max dev iterations reached — proceeding despite review feedback")

            # Phase 8: QA Testing
            await self._execute_agent_phase(state, 8, "qa")

            # Phase 9: Security Scan
            await self._execute_agent_phase(state, 9, "security")

            # Phase 10: Staging Deployment
            await self._execute_agent_phase(state, 10, "deployment")

            # Phase 11: Human Checkpoint — Approve Production
            staging_summary = (
                f"Staging URL: {state.staging_url}\n"
                f"Smoke Tests: {'PASSED ✅' if state.smoke_test_passed else 'FAILED ❌'}\n"
                f"Security: {'PASS ✅' if state.security_passed else 'ISSUES ⚠️'}\n"
                f"Tests: {state.test_results.get('pass_rate', 'N/A') if state.test_results else 'N/A'}% pass rate"
            )
            await self._human_checkpoint(
                state, 11,
                "Approve Production Deployment",
                staging_summary,
                approval_key="production_approved",
            )

            # Phase 12: Production Deployment
            await self._execute_agent_phase(state, 12, "deployment")

            # Phase 13: Documentation
            await self._execute_agent_phase(state, 13, "documentation")

            # Phase 14: Project Complete
            await self._execute_agent_phase(state, 14, "documentation")

            logger.info("🎉 Pipeline complete: %s", state.project_name)

        except Exception as e:
            logger.exception("Pipeline failed: %s", e)
            await self._broadcast(
                state.project_id, state.current_phase,
                "pipeline_error",
                {"error": str(e)},
            )

    async def _execute_agent_phase(
        self,
        state: PipelineState,
        phase_id: int,
        agent_key: str,
    ) -> None:
        """Execute a single agent phase."""
        state.advance_phase(phase_id)
        agent = self._agents[agent_key]

        await self._broadcast(
            state.project_id, phase_id,
            "phase_started",
            {"agent": agent_key, "phase_name": PHASE_MAP[phase_id].name},
        )

        # Run agent synchronously in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, agent.run, state, phase_id)

        phase = state.get_phase(phase_id)
        await self._broadcast(
            state.project_id, phase_id,
            "phase_completed",
            {
                "status": phase.status,
                "duration": phase.duration_display,
                "tokens": phase.tokens_used,
                "cost": phase.cost_usd,
            },
        )

    async def _human_checkpoint(
        self,
        state: PipelineState,
        phase_id: int,
        checkpoint_name: str,
        summary: str,
        open_questions: Optional[list[str]] = None,
        approval_key: str = "",
        doc_urls: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Handle a human-in-the-loop checkpoint.
        Sends approval request to Slack and waits for response.

        Args:
            doc_urls: Optional dict of artifact_name -> Google Doc URL to include in Slack message.
        """
        state.advance_phase(phase_id)
        phase = state.get_phase(phase_id)
        phase.status = "waiting"
        phase.started_at = datetime.utcnow()
        phase.add_log("info", f"Waiting for human approval: {checkpoint_name}")

        await self._broadcast(
            state.project_id, phase_id,
            "approval_requested",
            {"checkpoint": checkpoint_name, "summary": summary[:500]},
        )

        # Create a future for the approval decision
        loop = asyncio.get_event_loop()
        approval_future: asyncio.Future = loop.create_future()

        # Register in pending approvals so submit_approval() can resolve it
        future_key = f"{state.project_id}|{phase_id}"
        self._pending_approvals[future_key] = approval_future

        def on_decision(decision: str, feedback: Optional[str], user: str):
            """Callback from Slack when user approves/rejects."""
            try:
                loop.call_soon_threadsafe(
                    approval_future.set_result,
                    {"decision": decision, "feedback": feedback, "user": user},
                )
            except Exception:
                pass

        # Send to Slack
        slack = get_slack_handler()
        slack_ts = slack.send_approval_request(
            project_id=state.project_id,
            project_name=state.project_name,
            phase_id=phase_id,
            phase_name=checkpoint_name,
            summary=summary[:2000],
            open_questions=open_questions,
            on_decision=on_decision,
            doc_urls=doc_urls,
        )
        if slack_ts:
            phase.add_log("info", "Approval request sent to Slack successfully")
        else:
            phase.add_log("warn", "Slack notification failed — use dashboard to approve")

        # Wait for approval (with timeout)
        try:
            result = await asyncio.wait_for(approval_future, timeout=3600)  # 1hr timeout

            if result["decision"] == "approved":
                phase.status = "success"
                phase.progress = 100
                phase.add_log("success", f"APPROVED by @{result['user']}")
                if approval_key:
                    setattr(state, approval_key, True)
            else:
                phase.status = "success"  # Phase itself completes, just with feedback
                phase.progress = 100
                state.human_feedback = result.get("feedback")
                phase.add_log("warn", f"REJECTED by @{result['user']}: {result.get('feedback', 'No feedback')}")
                if approval_key:
                    setattr(state, approval_key, True)  # Still proceed with feedback incorporated

        except asyncio.TimeoutError:
            phase.add_log("warn", "Approval timed out (1hr) — auto-approving")
            phase.status = "success"
            phase.progress = 100
            if approval_key:
                setattr(state, approval_key, True)
        finally:
            # Clean up the pending approval
            self._pending_approvals.pop(future_key, None)

        phase.completed_at = datetime.utcnow()
        if phase.started_at:
            phase.duration_seconds = (phase.completed_at - phase.started_at).total_seconds()

        await self._broadcast(
            state.project_id, phase_id,
            "phase_completed",
            {"status": phase.status, "duration": phase.duration_display},
        )

    async def submit_approval(
        self,
        project_id: str,
        phase_id: int,
        decision: str,
        feedback: Optional[str] = None,
        user: str = "dashboard",
    ) -> bool:
        """
        Submit an approval decision from the dashboard UI
        (alternative to Slack approval).
        Resolves the pending asyncio.Future so the pipeline resumes.
        """
        state = self._running_pipelines.get(project_id)
        if not state:
            logger.warning("submit_approval: project %s not found", project_id)
            return False

        phase = state.get_phase(phase_id)
        if phase.status != "waiting":
            logger.warning(
                "submit_approval: phase %d not in waiting state (current: %s)",
                phase_id, phase.status,
            )
            return False

        # Resolve the pending future so _human_checkpoint() wakes up
        approval_key = f"{project_id}|{phase_id}"
        future = self._pending_approvals.get(approval_key)
        if future and not future.done():
            future.set_result({
                "decision": decision,
                "feedback": feedback,
                "user": user,
            })
            logger.info(
                "Resolved approval future for %s (decision: %s by %s)",
                approval_key, decision, user,
            )
        else:
            # Fallback: directly update phase if no future found
            logger.warning(
                "No pending future for %s — updating phase directly",
                approval_key,
            )
            if decision == "approved":
                phase.status = "success"
                phase.progress = 100
                phase.add_log("success", f"APPROVED by {user} (via dashboard)")
            else:
                phase.status = "success"
                phase.progress = 100
                state.human_feedback = feedback
                phase.add_log("warn", f"REJECTED by {user}: {feedback or 'No feedback'}")

            phase.completed_at = datetime.utcnow()
            if phase.started_at:
                phase.duration_seconds = (phase.completed_at - phase.started_at).total_seconds()

        return True

    async def submit_review_decision(
        self,
        project_id: str,
        decision: str,
    ) -> bool:
        """
        Submit a review decision (approved/regenerate) from the review UI.
        Resolves the pending asyncio.Future so the review loop continues.
        """
        future = self._pending_review_decisions.get(project_id)
        if future and not future.done():
            future.set_result({"decision": decision})
            logger.info("Resolved review decision for %s: %s", project_id[:8], decision)
            return True

        logger.warning("No pending review decision for project %s", project_id[:8])
        return False

    async def _prd_review_loop(self, state: PipelineState) -> None:
        """
        Iterative PRD review sub-workflow within Phase 1-2.
        
        Loop:
        1. Create versioned PRD → save to Docs → index in RAG → compute AI Confidence
        2. Send Slack notification with review link
        3. Wait for client: approve or regenerate
        4. If regenerate → rebuild PRD with feedback → loop again
        5. If approve → proceed to Phase 3
        """
        from src.orchestrator.prd_review_service import PRDReviewService

        review_service = PRDReviewService()

        # Create initial PRD version (v1) from Phase 1 output
        state = review_service.create_version(state, state.prd or "")

        while not state.prd_approved:
            current_version = state.get_current_prd_version()
            if not current_version:
                break

            # Update Phase 2 status
            phase2 = state.get_phase(2)
            phase2.status = "waiting"
            phase2.started_at = datetime.utcnow()
            phase2.add_log(
                "info",
                f"PRD v{current_version.version} ready for review "
                f"(AI Confidence: {current_version.overall_ai_confidence:.0f}%)",
            )
            state.advance_phase(2)

            await self._broadcast(
                state.project_id, 2,
                "review_ready",
                {
                    "version": current_version.version,
                    "ai_confidence": current_version.overall_ai_confidence,
                    "gdoc_url": current_version.gdoc_url,
                },
            )

            # Generate review token for the Slack link
            token_info = review_service.generate_review_token(state.project_id)
            review_url = f"http://localhost:5173/review/{state.project_id}?token={token_info['token']}"

            # Send Slack notification
            await self._send_review_slack_notification(
                state, current_version, review_url,
            )

            # Wait for client decision: "approved" or "regenerate"
            loop = asyncio.get_event_loop()
            decision_future: asyncio.Future = loop.create_future()
            self._pending_review_decisions[state.project_id] = decision_future

            # Also register as a Phase 2 approval (backward compat with dashboard)
            approval_key = f"{state.project_id}|2"
            self._pending_approvals[approval_key] = decision_future

            try:
                result = await asyncio.wait_for(decision_future, timeout=86400)  # 24hr
                decision = result.get("decision", "approved")
            except asyncio.TimeoutError:
                decision = "approved"  # Auto-approve after 24hr
                phase2.add_log("warn", "Review timed out (24hr) — auto-approving")
            finally:
                self._pending_review_decisions.pop(state.project_id, None)
                self._pending_approvals.pop(approval_key, None)

            if decision == "approved":
                state.prd_approved = True
                phase2.status = "success"
                phase2.progress = 100
                phase2.add_log(
                    "success",
                    f"PRD v{current_version.version} APPROVED",
                )
            elif decision == "regenerate":
                phase2.add_log(
                    "info",
                    f"Regenerating PRD (v{current_version.version} → v{current_version.version + 1})...",
                )

                # Regenerate PRD using the requirements agent with feedback
                await self._regenerate_prd(state, review_service)

                # Reset phase 2 for next iteration
                phase2.status = "idle"
                phase2.progress = 0
            else:
                # Treat unknown decisions as approve
                state.prd_approved = True
                phase2.status = "success"
                phase2.progress = 100

            phase2.completed_at = datetime.utcnow()
            if phase2.started_at:
                phase2.duration_seconds = (phase2.completed_at - phase2.started_at).total_seconds()

            await self._broadcast(
                state.project_id, 2,
                "phase_completed",
                {"status": phase2.status, "duration": phase2.duration_display},
            )

    async def _regenerate_prd(
        self,
        state: PipelineState,
        review_service,
    ) -> None:
        """
        Regenerate PRD using feedback from the current review session.
        Calls the requirements agent with an iteration-aware prompt.
        """
        current = state.get_current_prd_version()
        if not current or not current.review_session:
            return

        session = current.review_session

        # Gather all feedback
        feedback_parts = []

        # Include Quick Mode responses if present
        quick_resp = getattr(session, "quick_responses", None)
        if quick_resp:
            feedback_parts.append("QUICK MODE CLARIFICATIONS:")
            # Find the text of each quick question to pair it with its answer
            for q_id, answer in quick_resp.items():
                q_text = q_id
                for qq in getattr(session, "quick_questions", []):
                    if qq.get("id") == q_id:
                        q_text = qq.get("text", "")
                        break
                feedback_parts.append(f"  Q: {q_text} → A: {answer}")

        if session.questionnaire_responses:
            feedback_parts.append("QUESTIONNAIRE RESPONSES:")
            for section, responses in session.questionnaire_responses.items():
                for resp in responses:
                    feedback_parts.append(
                        f"  [{section}] Q: {resp.get('question', '')} → A: {resp.get('answer', '')}"
                    )

        if session.feedback_text:
            feedback_parts.append(f"\nCLIENT TEXT FEEDBACK:\n{session.feedback_text}")

        if session.feedback_files:
            from src.agents.understanding_analyzer import UnderstandingAnalyzer
            for file_info in session.feedback_files:
                content = UnderstandingAnalyzer.parse_feedback_file(
                    file_info["path"], file_info["type"]
                )
                feedback_parts.append(
                    f"\nFEEDBACK FILE ({file_info['filename']}):\n{content[:2000]}"
                )

        locked_sections = state.get_locked_sections()
        if locked_sections:
            feedback_parts.append(
                f"\nLOCKED SECTIONS (do NOT modify): {', '.join(locked_sections)}"
            )

        # Build the combined feedback for the agent
        combined_feedback = "\n".join(feedback_parts)
        state.human_feedback = combined_feedback

        # Run the requirements agent again (Phase 1 re-run)
        agent = self._agents["requirements"]
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, agent.run, state, 1)

        # Create new version via review service
        if state.prd:
            # Get change summary
            changes = []
            if session.understanding_analysis:
                categories = session.understanding_analysis.get("feedback_categories", {})
                for cat_name, items in categories.items():
                    for item in items:
                        changes.append(item.get("description", ""))

            state = review_service.create_version(
                state, state.prd,
                changes_from_previous=changes[:10],
            )

    async def _send_review_slack_notification(
        self,
        state: PipelineState,
        version,
        review_url: str,
    ) -> None:
        """Send rich Slack notification for PRD review."""
        slack = get_slack_handler()
        if not slack._initialized:
            return

        # Build section scores summary
        low_confidence = []
        for s in version.section_scores:
            if s.ai_confidence < 80:
                low_confidence.append(f"• {s.section_name} ({s.ai_confidence:.0f}%)")

        # Build changes summary for v2+
        changes_text = ""
        if version.changes_from_previous:
            changes_items = "\n".join(f"• {c}" for c in version.changes_from_previous[:5])
            changes_text = f"\n*Changes Since v{version.version - 1}:*\n{changes_items}\n"

        low_text = ""
        if low_confidence:
            low_items = "\n".join(low_confidence[:5])
            low_text = f"\n*Sections Needing Attention:*\n{low_items}\n"

        summary = (
            f"✅ *PRD Version {version.version} Generated*\n\n"
            f"*AI Confidence:* {version.overall_ai_confidence:.0f}%\n"
            f"{changes_text}"
            f"{low_text}\n"
            f"Please validate our understanding below.\n\n"
            f"📋 *<{review_url}|Open Review Questionnaire>*"
        )

        if version.gdoc_url:
            summary += f"\n📄 *<{version.gdoc_url}|View PRD in Google Docs>*"

        # Use thread for all review notifications
        thread_ts = state.prd_review_slack_thread_ts

        try:
            ts = slack.send_approval_request(
                project_id=state.project_id,
                project_name=state.project_name,
                phase_id=2,
                phase_name=f"PRD v{version.version} Review",
                summary=summary,
                open_questions=None,
                on_decision=lambda decision, feedback, user: (
                    asyncio.get_event_loop().call_soon_threadsafe(
                        self._resolve_review_decision,
                        state.project_id, decision,
                    )
                ),
            )

            # Track thread for future notifications
            if ts and not state.prd_review_slack_thread_ts:
                state.prd_review_slack_thread_ts = ts

        except Exception as e:
            logger.warning("Failed to send review Slack notification: %s", e)

    def _resolve_review_decision(self, project_id: str, decision: str) -> None:
        """Resolve a pending review decision from Slack callback."""
        future = self._pending_review_decisions.get(project_id)
        if future and not future.done():
            mapped = "approved" if decision == "approved" else "regenerate"
            future.set_result({"decision": mapped})


# ── Singleton ──
_orchestrator: Optional[PipelineOrchestrator] = None


def get_orchestrator() -> PipelineOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipelineOrchestrator()
    return _orchestrator
