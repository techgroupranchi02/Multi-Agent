import React from 'react';
import type { ViewType } from '../types';

interface SidebarProps {
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
  projectName?: string;
  projectStatus?: string;
  currentPhase?: number;
  totalPhases?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeView,
  onViewChange,
  projectName,
  projectStatus,
  currentPhase,
  totalPhases = 14,
}) => {
  return (
    <div className="sidebar">
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">A</div>
        <div className="sidebar-title">
          <h1>Aikyam</h1>
          <span>Multi-Agent Pipeline</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {/* Main section */}
        <div className="nav-section">
          <div className="nav-section-label">Main</div>

          <div
            className={`nav-item ${activeView === 'pipeline' ? 'active' : ''}`}
            onClick={() => onViewChange('pipeline')}
          >
            <span className="nav-item-icon">🔄</span>
            <span>Pipeline</span>
            {currentPhase && (
              <span className="nav-item-badge">{currentPhase}/{totalPhases}</span>
            )}
          </div>

          <div
            className={`nav-item ${activeView === 'new-project' ? 'active' : ''}`}
            onClick={() => onViewChange('new-project')}
          >
            <span className="nav-item-icon">➕</span>
            <span>New Project</span>
          </div>

          <div
            className={`nav-item ${activeView === 'logs' ? 'active' : ''}`}
            onClick={() => onViewChange('logs')}
          >
            <span className="nav-item-icon">📊</span>
            <span>All Logs</span>
          </div>

          <div
            className={`nav-item ${activeView === 'settings' ? 'active' : ''}`}
            onClick={() => onViewChange('settings')}
          >
            <span className="nav-item-icon">⚙️</span>
            <span>Settings</span>
          </div>
        </div>

        {/* Agents section */}
        <div className="nav-section">
          <div className="nav-section-label">Agents</div>

          {[
            { icon: '📝', name: 'Requirements', color: 'var(--agent-requirements)' },
            { icon: '🎫', name: 'Jira Tasks', color: 'var(--agent-jira)' },
            { icon: '👨‍💻', name: 'Developer', color: 'var(--agent-developer)' },
            { icon: '🔍', name: 'Code Review', color: 'var(--agent-reviewer)' },
            { icon: '🧪', name: 'QA / Test', color: 'var(--agent-qa)' },
            { icon: '🔒', name: 'Security', color: 'var(--agent-security)' },
            { icon: '🚀', name: 'Deployment', color: 'var(--agent-deployment)' },
            { icon: '📚', name: 'Documentation', color: 'var(--agent-docs)' },
          ].map((agent) => (
            <div className="nav-item" key={agent.name}>
              <span className="nav-item-icon">{agent.icon}</span>
              <span>{agent.name}</span>
              <div
                style={{
                  marginLeft: 'auto',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: agent.color,
                  opacity: 0.5,
                }}
              />
            </div>
          ))}
        </div>

        {/* Quick Links */}
        <div className="nav-section">
          <div className="nav-section-label">Quick Links</div>
          <a
            className="nav-item"
            href="https://freecomerscore.atlassian.net/jira/core/projects/MAT/board"
            target="_blank"
            rel="noopener noreferrer"
            style={{ textDecoration: 'none' }}
          >
            <span className="nav-item-icon">🎯</span>
            <span>Jira Board</span>
            <span style={{ marginLeft: 'auto', fontSize: '0.7rem', opacity: 0.5 }}>↗</span>
          </a>
          <a
            className="nav-item"
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ textDecoration: 'none' }}
          >
            <span className="nav-item-icon">🐙</span>
            <span>GitHub</span>
            <span style={{ marginLeft: 'auto', fontSize: '0.7rem', opacity: 0.5 }}>↗</span>
          </a>
        </div>
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        {projectName && (
          <div style={{
            padding: '8px 12px',
            background: 'var(--bg-glass)',
            borderRadius: 'var(--radius-md)',
            marginBottom: '8px',
            fontSize: '0.72rem',
          }}>
            <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Active Project</div>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.78rem' }}>
              {projectName}
            </div>
            {projectStatus && (
              <div style={{
                marginTop: '4px',
                color: projectStatus === 'running' ? 'var(--accent-blue)' : 'var(--text-muted)',
                fontWeight: 500,
              }}>
                {projectStatus === 'running' ? '⚡ Running' : projectStatus}
              </div>
            )}
          </div>
        )}
        <div className="sidebar-status">
          <div className="status-dot connected" />
          <span>System Online</span>
          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.65rem' }}>
            v1.0.0
          </span>
        </div>
      </div>
    </div>
  );
};
