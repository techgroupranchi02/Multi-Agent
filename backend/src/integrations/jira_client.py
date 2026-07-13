"""
Aikyam Multi-Agent Pipeline — Jira Integration
Creates epics, stories, subtasks; logs work; transitions issue statuses.
Target: https://freecomerscore.atlassian.net (project: MAT)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


class JiraClient:
    """
    Wrapper around atlassian-python-api for Jira Cloud operations.
    """

    def __init__(self):
        self.settings = get_settings()
        self._jira = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize Jira client. Returns False if credentials are missing."""
        if not self.settings.jira_username or not self.settings.jira_api_token:
            logger.warning("Jira credentials not configured — Jira integration disabled")
            return False

        try:
            from atlassian import Jira

            self._jira = Jira(
                url=self.settings.jira_url,
                username=self.settings.jira_username,
                password=self.settings.jira_api_token,
                cloud=True,
            )
            # Test connection
            self._jira.myself()
            self._initialized = True
            logger.info("✓ Jira client initialized (%s, project: %s)",
                        self.settings.jira_url, self.settings.jira_project_key)
            return True
        except ImportError:
            logger.warning("atlassian-python-api not installed — run: pip install atlassian-python-api")
            return False
        except Exception as e:
            logger.error("Failed to initialize Jira: %s", e)
            return False

    def create_epic(self, summary: str, description: str = "") -> Optional[dict[str, Any]]:
        """Create a Jira Epic and return the issue data."""
        if not self._initialized:
            logger.warning("Jira not initialized — skipping epic creation")
            return None

        try:
            issue = self._jira.issue_create(fields={
                "project": {"key": self.settings.jira_project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": "Epic"},
            })
            logger.info("Created Jira Epic: %s — %s", issue["key"], summary)
            return issue
        except Exception as e:
            logger.error("Failed to create Jira Epic: %s", e)
            return None

    def create_story(
        self,
        summary: str,
        description: str = "",
        epic_key: Optional[str] = None,
        story_points: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """Create a Jira Story, optionally linked to an Epic."""
        if not self._initialized:
            return None

        try:
            fields: dict[str, Any] = {
                "project": {"key": self.settings.jira_project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": "Story"},
            }

            # Link to Epic (Jira Cloud uses customfield for epic link)
            if epic_key:
                fields["parent"] = {"key": epic_key}

            if story_points:
                fields["story_points"] = story_points

            issue = self._jira.issue_create(fields=fields)
            logger.info("Created Jira Story: %s — %s (epic: %s)", issue["key"], summary, epic_key)
            return issue
        except Exception as e:
            logger.error("Failed to create Jira Story: %s", e)
            return None

    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: str = "",
    ) -> Optional[dict[str, Any]]:
        """Create a Jira Sub-task under a parent issue."""
        if not self._initialized:
            return None

        try:
            issue = self._jira.issue_create(fields={
                "project": {"key": self.settings.jira_project_key},
                "parent": {"key": parent_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": "Sub-task"},
            })
            logger.info("Created Jira Sub-task: %s — %s (parent: %s)", issue["key"], summary, parent_key)
            return issue
        except Exception as e:
            logger.error("Failed to create Jira Sub-task: %s", e)
            return None

    def create_task_hierarchy(
        self,
        epic_summary: str,
        epic_description: str,
        stories: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Create a full Jira task hierarchy:
        Epic → Stories → Sub-tasks.

        stories format:
        [
            {
                "summary": "Backend API",
                "description": "...",
                "subtasks": [
                    {"summary": "Setup server", "description": "..."},
                    ...
                ]
            },
            ...
        ]
        """
        result = {"epic": None, "stories": [], "subtasks": []}

        # Create Epic
        epic = self.create_epic(epic_summary, epic_description)
        if not epic:
            return result
        result["epic"] = epic

        # Create Stories and Sub-tasks
        for story_data in stories:
            story = self.create_story(
                summary=story_data["summary"],
                description=story_data.get("description", ""),
                epic_key=epic["key"],
                story_points=story_data.get("story_points"),
            )
            if not story:
                continue
            result["stories"].append(story)

            for subtask_data in story_data.get("subtasks", []):
                subtask = self.create_subtask(
                    parent_key=story["key"],
                    summary=subtask_data["summary"],
                    description=subtask_data.get("description", ""),
                )
                if subtask:
                    result["subtasks"].append(subtask)

        total_stories = len(result["stories"])
        total_subtasks = len(result["subtasks"])
        logger.info(
            "Created Jira hierarchy: Epic %s → %d stories, %d subtasks",
            epic["key"], total_stories, total_subtasks,
        )
        return result

    def transition_issue(self, issue_key: str, status_name: str) -> bool:
        """Transition an issue to a new status (e.g., 'In Progress', 'Done')."""
        if not self._initialized:
            return False

        try:
            transitions = self._jira.get_issue_transitions(issue_key)
            target = next(
                (t for t in transitions if t["name"].lower() == status_name.lower()),
                None,
            )
            if target:
                self._jira.issue_transition(issue_key, target["id"])
                logger.info("Transitioned %s → %s", issue_key, status_name)
                return True
            else:
                available = [t["name"] for t in transitions]
                logger.warning("Status '%s' not found for %s. Available: %s", status_name, issue_key, available)
                return False
        except Exception as e:
            logger.error("Failed to transition %s: %s", issue_key, e)
            return False

    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add a comment to a Jira issue."""
        if not self._initialized:
            return False

        try:
            self._jira.issue_add_comment(issue_key, comment)
            logger.info("Added comment to %s", issue_key)
            return True
        except Exception as e:
            logger.error("Failed to add comment to %s: %s", issue_key, e)
            return False

    def log_work(self, issue_key: str, time_spent: str, comment: str = "") -> bool:
        """Log work on a Jira issue (e.g., '2h', '30m')."""
        if not self._initialized:
            return False

        try:
            self._jira.issue_worklog(issue_key, time_spent, comment=comment)
            logger.info("Logged %s work on %s", time_spent, issue_key)
            return True
        except Exception as e:
            logger.error("Failed to log work on %s: %s", issue_key, e)
            return False

    def get_board_url(self) -> str:
        """Get the Jira board URL."""
        return f"{self.settings.jira_url}/jira/core/projects/{self.settings.jira_project_key}/board"


# ── Singleton ──
_jira_client: Optional[JiraClient] = None


def get_jira_client() -> JiraClient:
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraClient()
    return _jira_client
