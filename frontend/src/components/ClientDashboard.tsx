import React, { useState, useEffect } from 'react';
import { fetchClientDashboard } from '../reviewApi';

interface ClientDashboardProps {
  projectId: string;
  token?: string;
  onOpenReview?: () => void;
}

export function ClientDashboard({ projectId, token, onOpenReview }: ClientDashboardProps) {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    const result = await fetchClientDashboard(projectId, token);
    if (result) {
      setData(result);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="status-dot connected" style={{ width: 16, height: 16, marginBottom: 16 }} />
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Loading project status...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="empty-state" style={{ padding: '40px 20px' }}>
        <h3>Project Not Found</h3>
        <p>We could not retrieve the details for this project ID.</p>
      </div>
    );
  }

  const activePhaseInfo = data.phases?.find((p: any) => p.id === data.current_phase);

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      
      {/* Top Breadcrumb & Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
            Client Dashboard
          </span>
          <h2 style={{ fontSize: '1.8rem', fontWeight: 800, margin: '4px 0 0 0', background: 'linear-gradient(135deg, #fff, rgba(255,255,255,0.7))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            {data.project_name}
          </h2>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          {data.jira_epic_key && (
            <span style={{
              background: 'rgba(79, 143, 255, 0.05)',
              border: '1px solid rgba(79, 143, 255, 0.15)',
              padding: '6px 12px',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.75rem',
              fontWeight: 600,
              color: 'var(--accent-blue)',
            }}>
              🎫 Jira: {data.jira_epic_key}
            </span>
          )}
        </div>
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
        
        {/* Left Column: Progress Flow & Phase Overview */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Active Phase Card */}
          {activePhaseInfo && (
            <div className="card" style={{ padding: '24px', background: 'linear-gradient(135deg, var(--bg-card), rgba(79, 143, 255, 0.03))' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', items: 'flex-start', marginBottom: '16px' }}>
                <div>
                  <span style={{
                    fontSize: '0.7rem',
                    background: 'rgba(79, 143, 255, 0.1)',
                    color: 'var(--accent-blue)',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-full)',
                    fontWeight: 700,
                  }}>
                    ACTIVE PHASE
                  </span>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '8px 0 0 0' }}>
                    {activePhaseInfo.icon} Phase {activePhaseInfo.id}: {activePhaseInfo.name}
                  </h3>
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--accent-blue)' }}>
                  {activePhaseInfo.progress}%
                </div>
              </div>

              {/* Progress Bar */}
              <div style={{
                height: '8px',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: 'var(--radius-full)',
                overflow: 'hidden',
                marginBottom: '16px',
              }}>
                <div style={{
                  width: `${activePhaseInfo.progress}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, var(--accent-blue), var(--accent-purple))',
                  transition: 'width 0.4s ease',
                }} />
              </div>

              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>
                {activePhaseInfo.description}
              </p>
            </div>
          )}

          {/* Phase Pipeline Map */}
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '20px' }}>Delivery Progress</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {data.phases?.map((phase: any) => {
                const isActive = phase.id === data.current_phase;
                const isComplete = phase.status === 'success';
                const isWaiting = phase.status === 'waiting';
                
                return (
                  <div key={phase.id} style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 16px',
                    background: isActive ? 'rgba(79, 143, 255, 0.04)' : 'rgba(255,255,255,0.01)',
                    border: `1px solid ${isActive ? 'rgba(79, 143, 255, 0.2)' : isComplete ? 'rgba(16, 185, 129, 0.1)' : 'var(--border-subtle)'}`,
                    borderRadius: 'var(--radius-md)',
                    opacity: phase.id > data.current_phase ? 0.4 : 1,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '1.1rem' }}>{phase.icon}</span>
                      <div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{phase.name}</div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Phase {phase.id}</div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      {isComplete && (
                        <span style={{ color: '#10b981', fontSize: '0.75rem', fontWeight: 600 }}>✓ Complete</span>
                      )}
                      {isActive && !isWaiting && (
                        <span style={{ color: 'var(--accent-blue)', fontSize: '0.75rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="status-dot connected" style={{ width: 6, height: 6 }} /> In Progress ({phase.progress}%)
                        </span>
                      )}
                      {isWaiting && (
                        <span style={{
                          background: 'rgba(245, 158, 11, 0.1)',
                          color: '#f59e0b',
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-full)',
                        }}>
                          ⏳ Action Required
                        </span>
                      )}
                      {phase.id > data.current_phase && (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Upcoming</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Column: Key Details & Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Action Callouts */}
          {data.review_active && (
            <div className="card" style={{
              padding: '24px',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              background: 'linear-gradient(180deg, var(--bg-card), rgba(245, 158, 11, 0.03))',
              textAlign: 'center',
            }}>
              <span style={{ fontSize: '1.8rem' }}>📋</span>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, marginTop: '12px', marginBottom: '8px' }}>
                PRD Validation Required
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '16px', lineHeight: 1.4 }}>
                We have generated a product specifications document. Please complete our validation questionnaire to verify the requirements.
              </p>
              <button
                className="btn btn-primary"
                onClick={onOpenReview}
                style={{
                  width: '100%',
                  background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                  border: 'none',
                  boxShadow: '0 4px 12px rgba(245, 158, 11, 0.2)',
                }}
              >
                Start Validation Questionnaire
              </button>
            </div>
          )}

          {/* Staging/Prod URL panel */}
          {(data.staging_url || data.production_url) && (
            <div className="card" style={{ padding: '24px' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '16px' }}>Deployment Links</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {data.staging_url && (
                  <div>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block' }}>STAGING URL</span>
                    <a href={data.staging_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.8rem', color: 'var(--accent-blue)', textDecoration: 'underline' }}>
                      {data.staging_url}
                    </a>
                  </div>
                )}
                {data.production_url && (
                  <div>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block' }}>PRODUCTION URL</span>
                    <a href={data.production_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.8rem', color: 'var(--accent-green)', textDecoration: 'underline' }}>
                      {data.production_url}
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* PRD Versions Summary */}
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '16px' }}>Document Versions</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {data.prd_versions?.length > 0 ? (
                data.prd_versions.map((v: any) => (
                  <div key={v.version} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 12px',
                    background: 'rgba(255,255,255,0.01)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: '0.75rem',
                  }}>
                    <div>
                      <span style={{ fontWeight: 700 }}>v{v.version}</span>
                      <span style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>
                        {v.status === 'active' ? 'Active' : 'Archived'}
                      </span>
                    </div>
                    {v.gdoc_url && (
                      <a href={v.gdoc_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
                        View Docs
                      </a>
                    )}
                  </div>
                ))
              ) : (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No versions generated yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
