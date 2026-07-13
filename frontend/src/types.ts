// ── Types for the Multi-Agent SDLC Pipeline ──

export type PhaseStatus = 'idle' | 'running' | 'waiting' | 'success' | 'error';

export type AgentType =
  | 'requirements'
  | 'human'
  | 'jira'
  | 'developer'
  | 'reviewer'
  | 'qa'
  | 'security'
  | 'deployment'
  | 'docs';

export interface PhaseLog {
  time: string;
  level: 'info' | 'success' | 'warn' | 'error';
  message: string;
}

export interface Phase {
  id: number;
  name: string;
  agent: AgentType;
  icon: string;
  description: string;
  outputs: string[];
  outputArtifacts: Record<string, string>;  // artifact name -> file path
  logsToJira: boolean;
  status: PhaseStatus;
  progress: number; // 0-100
  logs: PhaseLog[];
  duration?: string;
  retryCount?: number;
  maxRetries?: number;
}

export interface Project {
  id: string;
  name: string;
  rawRequirements: string;
  status: 'draft' | 'running' | 'paused' | 'completed' | 'failed';
  currentPhase: number;
  phases: Phase[];
  createdAt: string;
  totalTokens: number;
  totalCost: number;
  jiraEpicKey?: string;
  githubRepo?: string;
  stagingUrl?: string;
  productionUrl?: string;
  latestPrdGdocUrl?: string;
}

export type ViewType = 'pipeline' | 'new-project' | 'settings' | 'logs' | 'review' | 'client-dashboard';

// ── Review Flow Types ──

export interface ChangeEvidence {
  change_description: string;
  source_type: string;
  source_reference: string;
  section_affected: string;
  change_type: string;
}

export interface SectionUnderstanding {
  section_name: string;
  section_content_preview?: string;
  ai_confidence: number;
  understanding_score?: number | null;
  question_count: number;
  estimated_minutes: number;
  questions: any[];
  why_low: string[];
  confidence_level: 'high' | 'medium' | 'low';
  locked: boolean;
  gdoc_heading_id?: string | null;
}

export interface ReviewSession {
  session_id: string;
  prd_version: number;
  started_at: string;
  completed_at?: string | null;
  questionnaire_responses: Record<string, any[]>;
  completed_sections: string[];
  feedback_files: Array<{ filename: string; path: string; type: string; drive_url?: string }>;
  feedback_text?: string | null;
  new_requirements: number;
  clarifications: number;
  conflicts: number;
  enhancements: number;
  status: 'in_progress' | 'completed' | 'ready_for_redraft';
}

export interface PRDVersion {
  version: number;
  status: 'active' | 'archived';
  created_at: string;
  gdoc_url?: string | null;
  gdoc_tab_id?: string | null;
  ai_confidence: number;
  understanding_score?: number | null;
  changes_count?: number;
}

export interface ReviewStatus {
  project_id: string;
  project_name: string;
  has_prd: boolean;
  current_version?: number;
  status?: string;
  gdoc_url?: string | null;
  ai_confidence?: number;
  understanding_score?: number | null;
  section_scores?: SectionUnderstanding[];
  readiness?: {
    ready: boolean;
    overall_understanding_score?: number | null;
    overall_ai_confidence: number;
    total_sections: number;
    completed_sections: number;
    locked_sections: number;
    has_questionnaire: boolean;
    has_feedback: boolean;
    feedback_file_count: number;
    version: number;
    version_warning: boolean;
  };
  prd_approved: boolean;
  review_mode?: 'detailed' | 'quick';
  quick_questions?: Array<{
    id: string;
    type?: 'open' | 'multiple_choice';
    text: string;
    context?: string;
    options?: string[] | null;
  }>;
  quick_responses?: Record<string, string>;
}

