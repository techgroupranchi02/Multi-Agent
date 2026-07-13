"""
Aikyam Multi-Agent Pipeline — Pipeline Definitions
Static definitions for all 14 phases.
"""

from src.models.project_state import AgentType, PhaseDefinition

PIPELINE_PHASES: list[PhaseDefinition] = [
    PhaseDefinition(
        id=1, name="Requirements Analysis", agent=AgentType.REQUIREMENTS,
        icon="📝", description="Analyze raw requirements, generate PRD with open questions.",
        outputs=["PRD.md"], logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=2, name="Human Checkpoint — Approve PRD", agent=AgentType.HUMAN,
        icon="🧑", description="Review PRD via Slack. Approve or reject with feedback.",
        outputs=["approval_status"], logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=3, name="Design & Architecture", agent=AgentType.REQUIREMENTS,
        icon="📐", description="Create PDD, Execution Plan, API Design, DB Schema.",
        outputs=["PDD.md", "execution_plan.md", "api_spec.yaml", "db_schema.sql"],
        logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=4, name="Human Checkpoint — Approve Scope", agent=AgentType.HUMAN,
        icon="🧑", description="Review technical scope via Slack. Approve to proceed.",
        outputs=["approval_status"], logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=5, name="Jira Task Creation", agent=AgentType.JIRA,
        icon="🎫", description="Create Jira Epic with Stories and Sub-tasks.",
        outputs=["jira_epic", "jira_stories"], logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=6, name="Development", agent=AgentType.DEVELOPER,
        icon="👨‍💻", description="Generate source code + unit tests. Commit to Git.",
        outputs=["source_code", "unit_tests", "git_branch"],
        logs_to_jira=True, max_retries=3,
    ),
    PhaseDefinition(
        id=7, name="Code Review", agent=AgentType.REVIEWER,
        icon="🔍", description="Static analysis + LLM-powered code review.",
        outputs=["review_report", "verdict"], logs_to_jira=False, max_retries=3,
    ),
    PhaseDefinition(
        id=8, name="QA Testing", agent=AgentType.QA,
        icon="🧪", description="Generate test cases, export to Excel, run tests.",
        outputs=["test_cases.xlsx", "test_results"],
        logs_to_jira=True, max_retries=3,
    ),
    PhaseDefinition(
        id=9, name="Security Scan", agent=AgentType.SECURITY,
        icon="🔒", description="SAST analysis, dependency audit, secret detection.",
        outputs=["security_report.md"], logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=10, name="Staging Deployment", agent=AgentType.DEPLOYMENT,
        icon="🚀", description="Docker build, deploy to staging, smoke tests.",
        outputs=["staging_url", "smoke_test_results"],
        logs_to_jira=True, max_retries=0,
    ),
    PhaseDefinition(
        id=11, name="Human Checkpoint — Approve Production", agent=AgentType.HUMAN,
        icon="🧑", description="Review staging, approve production deployment via Slack.",
        outputs=["production_approval"], logs_to_jira=False, max_retries=0,
    ),
    PhaseDefinition(
        id=12, name="Production Deployment", agent=AgentType.DEPLOYMENT,
        icon="🚀", description="Deploy to production VPS, health checks.",
        outputs=["production_url", "health_check_log"],
        logs_to_jira=True, max_retries=0,
    ),
    PhaseDefinition(
        id=13, name="Documentation", agent=AgentType.DOCS,
        icon="📚", description="Generate User Guide, API Docs, CHANGELOG, Runbook.",
        outputs=["user_guide.md", "api_docs.md", "CHANGELOG.md", "runbook.md"],
        logs_to_jira=True, max_retries=0,
    ),
    PhaseDefinition(
        id=14, name="Project Complete", agent=AgentType.DOCS,
        icon="✅", description="Final summary, Slack notification, close Jira Epic.",
        outputs=["project_summary", "final_report"],
        logs_to_jira=False, max_retries=0,
    ),
]

PHASE_MAP: dict[int, PhaseDefinition] = {p.id: p for p in PIPELINE_PHASES}
