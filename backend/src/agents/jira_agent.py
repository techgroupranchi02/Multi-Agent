"""
Aikyam Multi-Agent Pipeline — Jira Task Agent
Phase 5: Creates Jira Epic with Stories and Sub-tasks from the execution plan.
"""

from __future__ import annotations

import json
import logging

from src.agents.base_agent import BaseAgent
from src.integrations.jira_client import get_jira_client
from src.models.project_state import PhaseState, PipelineState

logger = logging.getLogger(__name__)

JIRA_PROMPT = """You are a Jira project management expert. Given a project execution plan and PRD,
create a structured task breakdown as a JSON object.

Output ONLY valid JSON with this structure:
{
    "epic_summary": "Short epic title",
    "epic_description": "Brief description",
    "stories": [
        {
            "summary": "Story title",
            "description": "Story description with acceptance criteria",
            "story_points": 5,
            "subtasks": [
                {"summary": "Subtask title", "description": "Details"},
            ]
        }
    ]
}

Create stories for: Backend API, Frontend UI, Testing, Deployment & Docs.
Each story should have 2-5 subtasks. Use realistic story point estimates (1, 2, 3, 5, 8, 13)."""


class JiraTaskAgent(BaseAgent):
    """Phase 5: Creates Jira task hierarchy from the execution plan."""

    agent_name = "jira"
    agent_display_name = "Jira Task Agent"
    agent_icon = "🎫"

    def execute(self, state: PipelineState, phase: PhaseState) -> PipelineState:
        phase.progress = 10
        phase.add_log("info", "Generating Jira task structure from execution plan...")

        # Ask LLM to structure the tasks
        context = state.execution_plan or state.pdd or state.prd or ""
        messages = [
            {"role": "system", "content": JIRA_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {state.project_name}\n\n"
                    f"Execution Plan / Design:\n---\n{context[:6000]}\n---\n\n"
                    "Create the Jira task hierarchy as JSON."
                ),
            },
        ]

        response = self.call_llm(phase, messages, "Generating task hierarchy")
        phase.progress = 40

        # Parse LLM response as JSON
        try:
            # Try to extract JSON from markdown code block if present
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            task_data = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError) as e:
            phase.add_log("warn", f"Failed to parse LLM output as JSON, using fallback: {e}")
            task_data = {
                "epic_summary": state.project_name,
                "epic_description": f"Auto-generated from requirements: {state.raw_requirements[:200]}",
                "stories": [
                    {
                        "summary": "Backend Development",
                        "description": "Implement the backend API and database layer.",
                        "story_points": 8,
                        "subtasks": [
                            {"summary": "Setup project scaffolding", "description": ""},
                            {"summary": "Implement core API endpoints", "description": ""},
                            {"summary": "Database schema and migrations", "description": ""},
                        ],
                    },
                    {
                        "summary": "Frontend Development",
                        "description": "Build the user interface.",
                        "story_points": 8,
                        "subtasks": [
                            {"summary": "UI component library setup", "description": ""},
                            {"summary": "Implement main views", "description": ""},
                        ],
                    },
                    {
                        "summary": "Testing & QA",
                        "description": "Write and execute tests.",
                        "story_points": 5,
                        "subtasks": [
                            {"summary": "Unit tests", "description": ""},
                            {"summary": "Integration tests", "description": ""},
                        ],
                    },
                ],
            }

        phase.progress = 50
        state.jira_tasks = task_data.get("stories", [])

        # Create in Jira
        jira = get_jira_client()
        if jira._initialized:
            phase.add_log("info", f"Creating Jira Epic: {task_data['epic_summary']}")
            result = jira.create_task_hierarchy(
                epic_summary=task_data.get("epic_summary", state.project_name),
                epic_description=task_data.get("epic_description", ""),
                stories=task_data.get("stories", []),
            )

            if result["epic"]:
                state.jira_epic_key = result["epic"]["key"]
                num_stories = len(result["stories"])
                num_subtasks = len(result["subtasks"])
                phase.add_log(
                    "success",
                    f"Created Jira Epic {state.jira_epic_key} "
                    f"with {num_stories} stories, {num_subtasks} subtasks",
                )
                phase.add_log("info", f"Board: {jira.get_board_url()}")
            else:
                phase.add_log("warn", "Failed to create Jira tasks — continuing without Jira")
        else:
            phase.add_log("warn", "Jira not configured — task structure saved locally only")
            self.save_artifact(state, phase, "jira_tasks", json.dumps(task_data, indent=2), "json")

        phase.progress = 95
        return state
