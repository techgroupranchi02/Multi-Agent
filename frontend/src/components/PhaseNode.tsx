import React from 'react';
import type { Phase } from '../types';

interface PhaseNodeProps {
  phase: Phase;
  isActive: boolean;
  onClick: (phase: Phase) => void;
  onApproval?: (phaseId: number, decision: 'approved' | 'rejected', feedback?: string) => void;
}

const agentLabels: Record<string, string> = {
  requirements: 'Requirements Agent',
  human: 'Human Checkpoint',
  jira: 'Jira Task Agent',
  developer: 'Developer Agent',
  reviewer: 'Code Review Agent',
  qa: 'QA / Test Agent',
  security: 'Security Agent',
  deployment: 'Deployment Agent',
  docs: 'Documentation Agent',
};

const statusLabels: Record<string, string> = {
  idle: '⏸ Queued',
  running: '⚡ Running',
  waiting: '⏳ Awaiting Approval',
  success: '✓ Complete',
  error: '✗ Failed',
};

export const PhaseNode: React.FC<PhaseNodeProps> = ({ phase, isActive, onClick, onApproval }) => {
  return (
    <div
      className={`phase-node ${isActive ? 'active' : ''}`}
      onClick={() => onClick(phase)}
      style={{ animationDelay: `${phase.id * 60}ms` }}
    >
      {/* Left indicator */}
      <div className="phase-indicator">
        <div className={`phase-dot ${phase.status}`}>
          {phase.status === 'success' ? '✓' : phase.status === 'error' ? '✗' : ''}
        </div>
        <span className="phase-number">{String(phase.id).padStart(2, '0')}</span>
      </div>

      {/* Card */}
      <div
        className={`phase-card ${isActive ? 'active-card' : ''}`}
        data-agent={phase.agent}
        style={isActive ? { borderColor: 'var(--accent-blue)', boxShadow: 'var(--shadow-glow-blue)' } : {}}
      >
        <div className="phase-card-header">
          <div className="phase-card-title">
            <span className="agent-icon">{phase.icon}</span>
            <h3>{phase.name}</h3>
          </div>
          <span className={`meta-tag status ${phase.status}`}>
            {statusLabels[phase.status]}
          </span>
        </div>

        <p className="phase-card-description">{phase.description}</p>

        <div className="phase-card-meta">
          <span className="meta-tag output" style={{ opacity: 0.7 }}>
            🏷 {agentLabels[phase.agent]}
          </span>
          {phase.logsToJira && (
            <span className="meta-tag jira">📋 Logs to Jira</span>
          )}
          {phase.duration && (
            <span className="meta-tag output">⏱ {phase.duration}</span>
          )}
          {phase.retryCount !== undefined && phase.retryCount > 0 && (
            <span className="meta-tag status error">
              🔄 Retry {phase.retryCount}/{phase.maxRetries}
            </span>
          )}
        </div>

        {/* Progress bar for running phases */}
        {phase.status === 'running' && (
          <div className="phase-progress">
            <div
              className="phase-progress-bar"
              style={{ width: `${phase.progress}%` }}
            />
          </div>
        )}

        {/* Approval actions for human checkpoints */}
        {phase.status === 'waiting' && phase.agent === 'human' && (
          <div className="phase-actions">
            <button
              className="btn btn-success"
              onClick={(e) => {
                e.stopPropagation();
                if (onApproval) onApproval(phase.id, 'approved');
              }}
            >
              ✅ Approve
            </button>
            <button
              className="btn btn-danger"
              onClick={(e) => {
                e.stopPropagation();
                const feedback = window.prompt('What changes are needed? Be specific...');
                if (feedback !== null && onApproval) {
                  onApproval(phase.id, 'rejected', feedback || undefined);
                }
              }}
            >
              ❌ Reject + Feedback
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
