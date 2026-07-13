import type { Phase, Project } from './types';

// ── Default 14 phases matching the implementation plan ──
export function createDefaultPhases(): Phase[] {
  return [
    {
      id: 1,
      name: 'Requirements Analysis',
      agent: 'requirements',
      icon: '📝',
      description: 'Analyze raw requirements, generate PRD with open questions, user personas, functional & non-functional specs.',
      outputs: ['PRD.md', 'open_questions.md'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 2,
      name: 'Human Checkpoint — Approve PRD',
      agent: 'human',
      icon: '🧑',
      description: 'Review PRD and open questions via Slack. Approve to proceed or reject with feedback to regenerate.',
      outputs: ['approval_status'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 3,
      name: 'Design & Architecture',
      agent: 'requirements',
      icon: '📐',
      description: 'Create PDD, Execution Plan, API Design (OpenAPI 3.0), and Database Schema (ERD + migrations).',
      outputs: ['PDD.md', 'execution_plan.md', 'api_spec.yaml', 'db_schema.sql'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 4,
      name: 'Human Checkpoint — Approve Scope',
      agent: 'human',
      icon: '🧑',
      description: 'Review PDD, API design, and DB schema via Slack. Approve the full technical scope before development.',
      outputs: ['approval_status'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 5,
      name: 'Jira Task Creation',
      agent: 'jira',
      icon: '🎫',
      description: 'Create Jira Epic with Stories and Sub-tasks. Each task includes description, acceptance criteria, and story points.',
      outputs: ['jira_epic', 'jira_stories', 'jira_subtasks'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 6,
      name: 'Development',
      agent: 'developer',
      icon: '👨‍💻',
      description: 'Generate source code + unit tests. Create Git branch, commit with conventional messages, and run build locally.',
      outputs: ['source_code', 'unit_tests', 'git_branch'],
      logsToJira: true,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
      retryCount: 0,
      maxRetries: 3,
    },
    {
      id: 7,
      name: 'Code Review',
      agent: 'reviewer',
      icon: '🔍',
      description: 'Run static analysis (pylint/eslint) + LLM-powered review for SOLID violations, security, and performance.',
      outputs: ['review_report', 'verdict'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
      retryCount: 0,
      maxRetries: 3,
    },
    {
      id: 8,
      name: 'QA Testing',
      agent: 'qa',
      icon: '🧪',
      description: 'Generate test case matrix, export to Excel, run automated tests (pytest/vitest), and report results.',
      outputs: ['test_cases.xlsx', 'test_scripts', 'test_results'],
      logsToJira: true,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
      retryCount: 0,
      maxRetries: 3,
    },
    {
      id: 9,
      name: 'Security Scan',
      agent: 'security',
      icon: '🔒',
      description: 'Run SAST (Bandit/Semgrep), dependency audit (npm audit/pip-audit), and secret detection.',
      outputs: ['security_report.md', 'vulnerability_list'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 10,
      name: 'Staging Deployment',
      agent: 'deployment',
      icon: '🚀',
      description: 'Build Docker image, deploy to staging environment, and run smoke tests against live endpoints.',
      outputs: ['staging_url', 'smoke_test_results'],
      logsToJira: true,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 11,
      name: 'Human Checkpoint — Approve Production',
      agent: 'human',
      icon: '🧑',
      description: 'Review staging deployment, test results, and security report. Approve production deployment via Slack.',
      outputs: ['production_approval'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 12,
      name: 'Production Deployment',
      agent: 'deployment',
      icon: '🚀',
      description: 'Deploy to production VPS, run health checks, and verify all endpoints are operational.',
      outputs: ['production_url', 'health_check_log'],
      logsToJira: true,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 13,
      name: 'Documentation',
      agent: 'docs',
      icon: '📚',
      description: 'Generate User Guide, API Docs, Release Notes, CHANGELOG, and Deployment Runbook.',
      outputs: ['user_guide.md', 'api_docs.md', 'CHANGELOG.md', 'runbook.md'],
      logsToJira: true,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
    {
      id: 14,
      name: 'Project Complete',
      agent: 'docs',
      icon: '✅',
      description: 'Send final summary to Slack with all links, close Jira Epic, and archive workspace.',
      outputs: ['project_summary', 'final_report'],
      logsToJira: false,
      outputArtifacts: {},
      status: 'idle',
      progress: 0,
      logs: [],
    },
  ];
}

// ── Demo project with some phases completed for preview ──
export function createDemoProject(): Project {
  const phases = createDefaultPhases();

  // Simulate a pipeline in progress at Phase 7
  phases[0].status = 'success';
  phases[0].progress = 100;
  phases[0].duration = '2m 34s';
  phases[0].logs = [
    { time: '10:01:02', level: 'info', message: 'Starting requirements analysis...' },
    { time: '10:01:15', level: 'info', message: 'LLM generating PRD (Gemini 2.5 Pro)...' },
    { time: '10:02:48', level: 'info', message: 'PRD generated — 3 open questions identified' },
    { time: '10:03:01', level: 'info', message: 'Saved PRD to workspace/.state/prd.md' },
    { time: '10:03:12', level: 'success', message: 'Sent PRD to Slack #project-alpha for approval' },
    { time: '10:03:36', level: 'success', message: '✓ Phase complete — tokens: 4,280 | cost: $0.032' },
  ];

  phases[1].status = 'success';
  phases[1].progress = 100;
  phases[1].duration = '14m 22s';
  phases[1].logs = [
    { time: '10:03:40', level: 'info', message: 'Waiting for human approval via Slack...' },
    { time: '10:17:55', level: 'success', message: 'PRD APPROVED by @gaurav via Slack' },
    { time: '10:18:02', level: 'success', message: '✓ Phase complete' },
  ];

  phases[2].status = 'success';
  phases[2].progress = 100;
  phases[2].duration = '5m 11s';
  phases[2].logs = [
    { time: '10:18:05', level: 'info', message: 'Generating PDD from approved PRD...' },
    { time: '10:19:30', level: 'info', message: 'Generating API Design (OpenAPI 3.0)...' },
    { time: '10:20:45', level: 'info', message: 'Generating DB Schema (PostgreSQL)...' },
    { time: '10:22:10', level: 'info', message: 'Generating Execution Plan...' },
    { time: '10:23:16', level: 'success', message: '✓ All design artifacts saved — tokens: 12,540 | cost: $0.094' },
  ];

  phases[3].status = 'success';
  phases[3].progress = 100;
  phases[3].duration = '8m 05s';
  phases[3].logs = [
    { time: '10:23:20', level: 'info', message: 'Sent scope for review via Slack...' },
    { time: '10:31:25', level: 'success', message: 'Scope APPROVED by @gaurav — no changes requested' },
  ];

  phases[4].status = 'success';
  phases[4].progress = 100;
  phases[4].duration = '1m 47s';
  phases[4].logs = [
    { time: '10:31:30', level: 'info', message: 'Creating Jira Epic: MAT-42 "Project Alpha"' },
    { time: '10:32:05', level: 'info', message: 'Created 4 Stories, 12 Sub-tasks' },
    { time: '10:33:17', level: 'success', message: '✓ Jira board ready — https://freecomerscore.atlassian.net/browse/MAT-42' },
  ];

  phases[5].status = 'success';
  phases[5].progress = 100;
  phases[5].duration = '18m 32s';
  phases[5].logs = [
    { time: '10:33:20', level: 'info', message: 'Created branch: feature/MAT-43-backend-api' },
    { time: '10:35:00', level: 'info', message: 'Generating FastAPI server scaffolding...' },
    { time: '10:42:15', level: 'info', message: 'Implementing auth endpoints...' },
    { time: '10:48:00', level: 'info', message: 'Writing unit tests (18 test cases)...' },
    { time: '10:50:30', level: 'info', message: 'Build successful — all 18 tests passing' },
    { time: '10:51:52', level: 'success', message: '✓ Code committed — tokens: 45,320 | cost: $0.340' },
  ];

  phases[6].status = 'running';
  phases[6].progress = 65;
  phases[6].logs = [
    { time: '10:52:00', level: 'info', message: 'Starting code review...' },
    { time: '10:52:10', level: 'info', message: 'Running pylint analysis... 9.2/10' },
    { time: '10:52:25', level: 'info', message: 'Running bandit security scan... 0 issues' },
    { time: '10:52:40', level: 'info', message: 'LLM reviewing code patterns (Gemini)...' },
    { time: '10:53:15', level: 'warn', message: 'Minor: Consider adding rate limiting to /api/auth/login' },
  ];

  return {
    id: 'proj-alpha-001',
    name: 'Project Alpha — Task Management API',
    rawRequirements: 'Build a task management API with user authentication, CRUD operations for tasks and projects, role-based access control, and real-time notifications via WebSocket.',
    status: 'running',
    currentPhase: 7,
    phases,
    createdAt: '2026-07-07T10:00:00Z',
    totalTokens: 62140,
    totalCost: 0.466,
    jiraEpicKey: 'MAT-42',
    githubRepo: 'aikyam/project-alpha',
    stagingUrl: undefined,
    productionUrl: undefined,
  };
}
