import React, { useState } from 'react';
import type { Phase, Project } from '../types';
import { PhaseNode } from './PhaseNode';
import { DetailPanel } from './DetailPanel';

interface PipelineViewProps {
  project: Project;
  onApproval?: (phaseId: number, decision: 'approved' | 'rejected', feedback?: string) => void;
}

export const PipelineView: React.FC<PipelineViewProps> = ({ project, onApproval }) => {
  const [selectedPhase, setSelectedPhase] = useState<Phase | null>(null);

  const completedCount = project.phases.filter(p => p.status === 'success').length;
  const runningCount = project.phases.filter(p => p.status === 'running').length;
  const waitingCount = project.phases.filter(p => p.status === 'waiting').length;

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      {/* Main pipeline area */}
      <div className="pipeline-container">
        {/* Header */}
        <div className="pipeline-header">
          <div>
            <h2>{project.name}</h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              {project.rawRequirements.length > 120
                ? project.rawRequirements.slice(0, 120) + '...'
                : project.rawRequirements}
            </p>
          </div>
        </div>

        {/* Stats bar */}
        <div className="pipeline-stats" style={{ marginBottom: '24px' }}>
          <div className="stat-chip">
            <span>✅</span>
            <span className="stat-value">{completedCount}</span>
            <span>completed</span>
          </div>
          <div className="stat-chip">
            <span>⚡</span>
            <span className="stat-value" style={{ color: 'var(--accent-blue)' }}>{runningCount}</span>
            <span>running</span>
          </div>
          <div className="stat-chip">
            <span>⏳</span>
            <span className="stat-value" style={{ color: 'var(--accent-orange)' }}>{waitingCount}</span>
            <span>waiting</span>
          </div>
          <div className="stat-chip">
            <span>🪙</span>
            <span className="stat-value" style={{ color: 'var(--accent-purple)' }}>
              {project.totalTokens.toLocaleString()}
            </span>
            <span>tokens</span>
          </div>
          <div className="stat-chip">
            <span>💰</span>
            <span className="stat-value" style={{ color: 'var(--accent-green)' }}>
              ${project.totalCost.toFixed(3)}
            </span>
            <span>cost</span>
          </div>
          {project.jiraEpicKey && (
            <a
              className="stat-chip"
              href={`https://freecomerscore.atlassian.net/browse/${project.jiraEpicKey}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: 'none', cursor: 'pointer' }}
            >
              <span>🎯</span>
              <span className="stat-value" style={{ color: 'var(--accent-blue)' }}>
                {project.jiraEpicKey}
              </span>
              <span>↗</span>
            </a>
          )}
        </div>

        {/* Overall progress */}
        <div style={{
          marginBottom: '32px',
          padding: '16px 20px',
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '8px',
          }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>Overall Progress</span>
            <span style={{
              fontSize: '0.8rem',
              fontWeight: 700,
              color: 'var(--accent-blue)',
              fontFamily: 'var(--font-mono)',
            }}>
              {Math.round((completedCount / project.phases.length) * 100)}%
            </span>
          </div>
          <div style={{
            height: '6px',
            background: 'rgba(255,255,255,0.05)',
            borderRadius: '999px',
            overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${(completedCount / project.phases.length) * 100}%`,
              background: 'linear-gradient(90deg, var(--accent-purple), var(--accent-blue), var(--accent-cyan))',
              borderRadius: '999px',
              transition: 'width 1s ease',
            }} />
          </div>
        </div>

        {/* Phase flow */}
        <div className="pipeline-flow">
          {project.phases.map((phase) => (
            <PhaseNode
              key={phase.id}
              phase={phase}
              isActive={selectedPhase?.id === phase.id}
              onClick={setSelectedPhase}
              onApproval={onApproval}
            />
          ))}
        </div>

        {/* Bottom spacer */}
        <div style={{ height: '80px' }} />
      </div>

      {/* Detail panel */}
      <DetailPanel
        phase={selectedPhase ? project.phases.find(p => p.id === selectedPhase.id) || selectedPhase : null}
        projectId={project.id}
        onClose={() => setSelectedPhase(null)}
        onApproval={onApproval}
        latestPrdGdocUrl={project.latestPrdGdocUrl}
      />
    </div>
  );
};
