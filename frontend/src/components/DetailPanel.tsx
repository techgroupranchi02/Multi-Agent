import React, { useState } from 'react';
import type { Phase } from '../types';
import { fetchArtifactContent } from '../api';

interface DetailPanelProps {
  phase: Phase | null;
  projectId?: string;
  onClose: () => void;
  onApproval?: (phaseId: number, decision: 'approved' | 'rejected', feedback?: string) => void;
  latestPrdGdocUrl?: string;
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

export const DetailPanel: React.FC<DetailPanelProps> = ({ phase, projectId, onClose, onApproval, latestPrdGdocUrl }) => {
  const [expandedArtifact, setExpandedArtifact] = useState<string | null>(null);
  const [artifactData, setArtifactData] = useState<Record<string, { content: string; googleDocUrl?: string }>>({});
  const [loadingArtifact, setLoadingArtifact] = useState<string | null>(null);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState('');

  if (!phase) {
    return <div className="detail-panel hidden" />;
  }

  // Check which output artifacts actually exist for this phase
  const artifactNames = Object.keys(phase.outputArtifacts || {}).filter(n => !n.endsWith('_gdoc_url'));

  const handleViewArtifact = async (artifactName: string) => {
    if (expandedArtifact === artifactName) {
      setExpandedArtifact(null);
      return;
    }

    // Load if not cached
    if (!artifactData[artifactName] && projectId) {
      setLoadingArtifact(artifactName);
      const result = await fetchArtifactContent(projectId, artifactName);
      if (result) {
        setArtifactData(prev => ({ ...prev, [artifactName]: result }));
      }
      setLoadingArtifact(null);
    }
    setExpandedArtifact(artifactName);
  };

  const handleRejectSubmit = () => {
    if (onApproval && phase) {
      onApproval(phase.id, 'rejected', rejectFeedback || undefined);
    }
    setShowRejectModal(false);
    setRejectFeedback('');
  };

  return (
    <div className="detail-panel animate-slide-in">
      <div className="detail-panel-header">
        <h3>
          <span>{phase.icon}</span>
          Phase {phase.id}
        </h3>
        <button className="btn btn-icon" onClick={onClose} title="Close panel">
          ✕
        </button>
      </div>

      <div className="detail-panel-body">
        {/* Agent Info */}
        <div className="detail-section">
          <h4>Agent</h4>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '1.5rem' }}>{phase.icon}</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{phase.name}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {agentLabels[phase.agent]}
              </div>
            </div>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {phase.description}
          </p>
        </div>

        {/* Status */}
        <div className="detail-section">
          <h4>Status</h4>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className={`meta-tag status ${phase.status}`} style={{ fontSize: '0.75rem' }}>
              {phase.status === 'idle' && '⏸ Queued'}
              {phase.status === 'running' && '⚡ Running'}
              {phase.status === 'waiting' && '⏳ Awaiting Approval'}
              {phase.status === 'success' && '✓ Complete'}
              {phase.status === 'error' && '✗ Failed'}
            </span>
            {phase.duration && (
              <span className="meta-tag output">⏱ {phase.duration}</span>
            )}
            {phase.logsToJira && (
              <span className="meta-tag jira">📋 Logs to Jira</span>
            )}
          </div>
          {phase.status === 'running' && (
            <div className="phase-progress" style={{ marginTop: '12px' }}>
              <div className="phase-progress-bar" style={{ width: `${phase.progress}%` }} />
            </div>
          )}
        </div>

        {/* Outputs with artifact viewer */}
        <div className="detail-section">
          <h4>Expected Outputs</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {phase.outputs.map((output, i) => {
              // Check if this output has a corresponding artifact
              const artifactKey = artifactNames.find(name => {
                const outputBase = output.replace(/\.[^.]+$/, '').toLowerCase();
                return name.toLowerCase() === outputBase || name.toLowerCase() === output.toLowerCase();
              });
              const hasArtifact = !!artifactKey;
              const isExpanded = expandedArtifact === artifactKey;
              const isLoading = loadingArtifact === artifactKey;

              return (
                <div key={i}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '6px 10px',
                      background: isExpanded
                        ? 'rgba(79, 143, 255, 0.08)'
                        : 'var(--bg-glass)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.78rem',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)',
                      cursor: hasArtifact ? 'pointer' : 'default',
                      border: isExpanded ? '1px solid rgba(79, 143, 255, 0.2)' : '1px solid transparent',
                      transition: 'all 0.2s ease',
                    }}
                    onClick={() => hasArtifact && artifactKey && handleViewArtifact(artifactKey)}
                  >
                    <span style={{ opacity: 0.5 }}>📄</span>
                    {output}
                    {phase.status === 'success' && (
                      <span style={{ marginLeft: 'auto', color: 'var(--accent-green)', fontSize: '0.7rem' }}>✓</span>
                    )}
                    {hasArtifact && phase.status === 'success' && (
                      <button
                        style={{
                          marginLeft: '4px',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                          background: isExpanded ? 'rgba(79, 143, 255, 0.15)' : 'rgba(79, 143, 255, 0.08)',
                          border: '1px solid rgba(79, 143, 255, 0.2)',
                          color: 'var(--accent-blue)',
                          fontSize: '0.65rem',
                          fontWeight: 600,
                          cursor: 'pointer',
                          fontFamily: 'var(--font-sans)',
                          transition: 'all 0.2s ease',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (artifactKey) handleViewArtifact(artifactKey);
                        }}
                      >
                        {isLoading ? '⏳ Loading...' : isExpanded ? '▲ Hide' : '👁 View'}
                      </button>
                    )}
                    {/* Google Docs link — always visible when available */}
                    {artifactKey && phase.status === 'success' && (phase.outputArtifacts[`${artifactKey}_gdoc_url`] || (artifactKey === 'prd' && latestPrdGdocUrl)) && (
                      <a
                        href={phase.outputArtifacts[`${artifactKey}_gdoc_url`] || (artifactKey === 'prd' ? latestPrdGdocUrl : '')}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          marginLeft: '4px',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                          background: 'rgba(66, 133, 244, 0.08)',
                          border: '1px solid rgba(66, 133, 244, 0.2)',
                          color: '#4285F4',
                          fontSize: '0.65rem',
                          fontWeight: 600,
                          cursor: 'pointer',
                          fontFamily: 'var(--font-sans)',
                          textDecoration: 'none',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                          transition: 'all 0.2s ease',
                        }}
                        onClick={(e) => e.stopPropagation()}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(66, 133, 244, 0.18)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(66, 133, 244, 0.08)';
                        }}
                      >
                        📄 GDocs ↗
                      </a>
                    )}
                  </div>

                  {/* Expanded artifact content */}
                  {isExpanded && artifactKey && (
                    <div>
                      {/* Google Docs link */}
                      {artifactData[artifactKey]?.googleDocUrl && (
                        <a
                          href={artifactData[artifactKey].googleDocUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            marginTop: '6px',
                            marginBottom: '4px',
                            padding: '6px 12px',
                            background: 'rgba(66, 133, 244, 0.1)',
                            border: '1px solid rgba(66, 133, 244, 0.25)',
                            borderRadius: 'var(--radius-sm)',
                            color: '#4285F4',
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            textDecoration: 'none',
                            transition: 'all 0.2s ease',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'rgba(66, 133, 244, 0.2)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'rgba(66, 133, 244, 0.1)';
                          }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M14 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V8L14 2Z" fill="#4285F4" opacity="0.2"/>
                            <path d="M14 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V8L14 2Z" stroke="#4285F4" strokeWidth="1.5"/>
                            <path d="M14 2V8H20" stroke="#4285F4" strokeWidth="1.5"/>
                            <path d="M8 13H16M8 17H13" stroke="#4285F4" strokeWidth="1.5" strokeLinecap="round"/>
                          </svg>
                          Open in Google Docs ↗
                        </a>
                      )}
                      <div
                        style={{
                          marginTop: '4px',
                          padding: '12px 14px',
                          background: 'rgba(0, 0, 0, 0.2)',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid rgba(79, 143, 255, 0.1)',
                          maxHeight: '400px',
                          overflowY: 'auto',
                          fontSize: '0.75rem',
                          lineHeight: 1.7,
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-secondary)',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                        }}
                      >
                        {artifactData[artifactKey]?.content || 'Loading...'}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Retry info */}
        {phase.retryCount !== undefined && (
          <div className="detail-section">
            <h4>Retry Policy</h4>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>
                Attempts: {phase.retryCount} / {phase.maxRetries}
              </span>
              <div style={{
                flex: 1,
                height: '4px',
                background: 'var(--bg-glass)',
                borderRadius: '999px',
                overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%',
                  width: `${((phase.retryCount || 0) / (phase.maxRetries || 3)) * 100}%`,
                  background: phase.retryCount === phase.maxRetries
                    ? 'var(--accent-red)'
                    : 'var(--accent-orange)',
                  borderRadius: '999px',
                  transition: 'width 0.3s ease',
                }} />
              </div>
            </div>
          </div>
        )}

        {/* Logs */}
        <div className="detail-section">
          <h4>Execution Logs</h4>
          {phase.logs.length > 0 ? (
            <div className="log-viewer">
              {phase.logs.map((log, i) => (
                <div className="log-line" key={i}>
                  <span className="log-time">{log.time}</span>
                  <span className={`log-level ${log.level}`}>
                    {log.level === 'info' && 'INFO'}
                    {log.level === 'success' && ' OK '}
                    {log.level === 'warn' && 'WARN'}
                    {log.level === 'error' && ' ERR'}
                  </span>
                  <span className="log-message">{log.message}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{
              padding: '24px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '0.8rem',
              background: 'var(--bg-glass)',
              borderRadius: 'var(--radius-md)',
            }}>
              No logs yet — phase hasn't started
            </div>
          )}
        </div>

        {/* Actions for waiting phases */}
        {phase.status === 'waiting' && phase.agent === 'human' && (
          <div className="detail-section">
            <h4>Action Required</h4>
            <div style={{
              padding: '16px',
              background: 'rgba(251, 191, 36, 0.05)',
              border: '1px solid rgba(251, 191, 36, 0.15)',
              borderRadius: 'var(--radius-md)',
              marginBottom: '12px',
            }}>
              <p style={{ fontSize: '0.8rem', color: 'var(--accent-orange)', marginBottom: '12px' }}>
                ⚠️ This phase requires your approval to continue. You can also approve via Slack.
              </p>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="btn btn-success"
                  onClick={() => {
                    if (onApproval) onApproval(phase.id, 'approved');
                  }}
                >
                  ✅ Approve
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => setShowRejectModal(true)}
                >
                  ❌ Reject + Feedback
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Rejection Feedback Modal */}
      {showRejectModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}
          onClick={() => setShowRejectModal(false)}
        >
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              width: '480px',
              maxWidth: '90vw',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.4)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{
              fontSize: '1.1rem',
              fontWeight: 700,
              marginBottom: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              ❌ Reject Phase — Provide Feedback
            </h3>
            <p style={{
              fontSize: '0.8rem',
              color: 'var(--text-muted)',
              marginBottom: '16px',
            }}>
              Your feedback will be incorporated into the next iteration. Be specific about what changes are needed.
            </p>
            <textarea
              value={rejectFeedback}
              onChange={(e) => setRejectFeedback(e.target.value)}
              placeholder="What changes are needed? Be specific..."
              style={{
                width: '100%',
                minHeight: '120px',
                padding: '12px',
                background: 'var(--bg-glass)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                fontSize: '0.85rem',
                fontFamily: 'var(--font-sans)',
                resize: 'vertical',
                outline: 'none',
                transition: 'border-color 0.2s ease',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'var(--accent-blue)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'var(--border-subtle)';
              }}
              autoFocus
            />
            <div style={{
              display: 'flex',
              gap: '8px',
              justifyContent: 'flex-end',
              marginTop: '16px',
            }}>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowRejectModal(false);
                  setRejectFeedback('');
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                onClick={handleRejectSubmit}
              >
                ❌ Submit Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
