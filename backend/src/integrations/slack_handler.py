"""
Aikyam Multi-Agent Pipeline — Slack Integration
Sends interactive approval messages with Block Kit buttons,
handles approval/rejection callbacks via Socket Mode.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


class SlackHandler:
    """
    Manages Slack interactions for human-in-the-loop checkpoints.
    Uses slack-bolt with Socket Mode (no public URL required).
    """

    def __init__(self):
        self.settings = get_settings()
        self._app = None
        self._approval_callbacks: dict[str, Callable] = {}
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize Slack app. Returns False if tokens are missing."""
        if not self.settings.slack_bot_token or not self.settings.slack_app_token:
            logger.warning("Slack tokens not configured — Slack integration disabled")
            return False

        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler

            self._app = App(token=self.settings.slack_bot_token)
            self._register_handlers()
            self._initialized = True
            logger.info("✓ Slack handler initialized (Socket Mode)")
            return True
        except ImportError:
            logger.warning("slack-bolt not installed — run: pip install slack-bolt")
            return False
        except Exception as e:
            logger.error("Failed to initialize Slack: %s", e)
            return False

    def _register_handlers(self) -> None:
        """Register Slack action handlers for approval buttons."""
        if not self._app:
            return

        @self._app.action("approve_phase")
        def handle_approve(ack, body, client):
            ack()
            action_value = body["actions"][0]["value"]  # "project_id|phase_id"
            project_id, phase_id = action_value.split("|")
            user = body["user"]["username"]

            # Update the original message
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"✅ *APPROVED* by @{user}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"✅ *APPROVED* by @{user} at <!date^{int(__import__('time').time())}^{{date_short}} {{time}}|now>",
                        },
                    }
                ],
            )

            # Trigger callback
            callback_key = f"{project_id}|{phase_id}"
            if callback_key in self._approval_callbacks:
                self._approval_callbacks[callback_key]("approved", None, user)
                del self._approval_callbacks[callback_key]

            logger.info("Phase %s APPROVED by @%s (project: %s)", phase_id, user, project_id)

        @self._app.action("reject_phase")
        def handle_reject(ack, body, client):
            ack()
            action_value = body["actions"][0]["value"]
            project_id, phase_id = action_value.split("|")

            # Open feedback modal
            client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": f"rejection_feedback|{project_id}|{phase_id}",
                    "title": {"type": "plain_text", "text": "Rejection Feedback"},
                    "submit": {"type": "plain_text", "text": "Submit"},
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "feedback_block",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "feedback_input",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "What changes are needed? Be specific...",
                                },
                            },
                            "label": {"type": "plain_text", "text": "Feedback"},
                        }
                    ],
                },
            )

        @self._app.view_submission("rejection_feedback")
        def handle_feedback_submission(ack, body, view):
            ack()
            callback_id = view["callback_id"]
            _, project_id, phase_id = callback_id.split("|")
            user = body["user"]["username"]
            feedback = view["state"]["values"]["feedback_block"]["feedback_input"]["value"]

            callback_key = f"{project_id}|{phase_id}"
            if callback_key in self._approval_callbacks:
                self._approval_callbacks[callback_key]("rejected", feedback, user)
                del self._approval_callbacks[callback_key]

            logger.info("Phase %s REJECTED by @%s — feedback: %s", phase_id, user, feedback[:100])

    def send_approval_request(
        self,
        project_id: str,
        project_name: str,
        phase_id: int,
        phase_name: str,
        summary: str,
        open_questions: Optional[list[str]] = None,
        attachments: Optional[list[dict]] = None,
        on_decision: Optional[Callable] = None,
        channel: Optional[str] = None,
        doc_urls: Optional[dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Send an interactive approval message to Slack.
        Returns the message timestamp (ts) for threading.

        Args:
            doc_urls: Optional dict of artifact_name -> Google Doc URL to include as links.
        """
        if not self._initialized or not self._app:
            logger.warning("Slack not initialized — skipping approval request")
            return None

        target_channel = channel or self.settings.slack_channel_id
        action_value = f"{project_id}|{phase_id}"

        # Register callback
        if on_decision:
            self._approval_callbacks[action_value] = on_decision

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📋 {phase_name} — Review Required"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Project:* {project_name}\n\n{summary}",
                },
            },
        ]
        # Add open questions if any
        if open_questions:
            questions_text = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(open_questions))
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❓ *Open Questions:*\n{questions_text}",
                },
            })

        blocks.append({"type": "divider"})

        # Action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "action_id": "approve_phase",
                    "value": action_value,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject + Feedback"},
                    "action_id": "reject_phase",
                    "value": action_value,
                    "style": "danger",
                },
            ],
        })

        try:
            logger.info(
                "Sending Slack approval to channel: %s (bot token: %s...)",
                target_channel,
                self.settings.slack_bot_token[:15] if self.settings.slack_bot_token else "MISSING",
            )
            result = self._app.client.chat_postMessage(
                channel=target_channel,
                text=f"📋 {phase_name} — Review Required for {project_name}",
                blocks=blocks,
            )
            ts = result["ts"]
            logger.info("Sent approval request to Slack (ts: %s)", ts)

            # Upload file attachments if provided
            if attachments:
                for att in attachments:
                    self._app.client.files_upload_v2(
                        channel=target_channel,
                        thread_ts=ts,
                        **att,
                    )

            return ts
        except Exception as e:
            logger.error(
                "Failed to send Slack message to channel '%s': %s — %s",
                target_channel, type(e).__name__, e,
            )
            return None

    def send_notification(
        self,
        message: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> None:
        """Send a simple notification message to Slack."""
        if not self._initialized or not self._app:
            logger.info("[Slack-disabled] %s", message)
            return

        try:
            self._app.client.chat_postMessage(
                channel=channel or self.settings.slack_channel_id,
                text=message,
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.error("Failed to send Slack notification: %s", e)

    def send_completion_summary(
        self,
        project_name: str,
        production_url: Optional[str],
        jira_epic_key: Optional[str],
        total_tokens: int,
        total_cost: float,
        duration: str,
        channel: Optional[str] = None,
    ) -> None:
        """Send the final project completion summary."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"✅ Project Complete: {project_name}"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"🚀 *Production:*\n{production_url or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"🎫 *Jira:*\n{jira_epic_key or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"⏱️ *Duration:*\n{duration}"},
                    {"type": "mrkdwn", "text": f"💰 *Cost:*\n${total_cost:.3f} ({total_tokens:,} tokens)"},
                ],
            },
        ]

        self.send_notification(
            message=f"✅ Project Complete: {project_name}",
            channel=channel,
        )

    def start_socket_mode(self) -> None:
        """Start the Slack Socket Mode handler (non-blocking)."""
        if not self._initialized or not self._app:
            logger.warning("Cannot start Socket Mode — Slack not initialized")
            return

        from slack_bolt.adapter.socket_mode import SocketModeHandler
        handler = SocketModeHandler(self._app, self.settings.slack_app_token)
        logger.info("Starting Slack Socket Mode...")
        handler.connect()


# ── Singleton ──
_slack_handler: Optional[SlackHandler] = None


def get_slack_handler() -> SlackHandler:
    global _slack_handler
    if _slack_handler is None:
        _slack_handler = SlackHandler()
    return _slack_handler
