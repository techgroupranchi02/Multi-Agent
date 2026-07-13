import { useState, useEffect, useCallback } from 'react';
import type { Project, ViewType } from './types';
import { createDemoProject } from './data';
import { Sidebar } from './components/Sidebar';
import { PipelineView } from './components/PipelineView';
import { NewProjectView } from './components/NewProjectView';
import { ReviewPage } from './components/ReviewPage';
import { ClientDashboard } from './components/ClientDashboard';
import { fetchProjects, fetchProjectDetail, approvePhase, connectWebSocket, deleteProject } from './api';
import './App.css';

function App() {
  const [activeView, setActiveView] = useState<ViewType>('pipeline');
  const [project, setProject] = useState<Project | null>(null);
  const [toasts, setToasts] = useState<Array<{ id: number; icon: string; message: string }>>([]);
  const [urlProjectId, setUrlProjectId] = useState<string | null>(null);
  const [urlToken, setUrlToken] = useState<string>('');

  // Toast notification helper
  const addToast = useCallback((icon: string, message: string) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, icon, message }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);

  // Helper to load project detail
  const loadProjectDetail = useCallback(async (projectId: string) => {
    const detail = await fetchProjectDetail(projectId);
    if (detail) {
      setProject(detail);
    }
  }, []);

  // Load latest project or parse URL route on mount
  useEffect(() => {
    async function init() {
      const pathname = window.location.pathname;
      const searchParams = new URLSearchParams(window.location.search);
      const token = searchParams.get('token') || '';
      setUrlToken(token);

      if (pathname.startsWith('/review/')) {
        const pId = pathname.split('/')[2];
        setUrlProjectId(pId);
        setActiveView('review');
        await loadProjectDetail(pId);
        return;
      }

      if (pathname.startsWith('/client/')) {
        const pId = pathname.split('/')[2];
        setUrlProjectId(pId);
        setActiveView('client-dashboard');
        await loadProjectDetail(pId);
        return;
      }

      // Default internal view routing
      const list = await fetchProjects();
      if (list.length > 0) {
        // Sort by created time or ID to get latest
        const sorted = [...list].sort((a, b) => b.id.localeCompare(a.id));
        await loadProjectDetail(sorted[0].id);
      } else {
        // Fallback to demo project if no backend projects exist AND not cleared
        const demoCleared = localStorage.getItem('aikyam_demo_cleared') === 'true';
        if (!demoCleared) {
          const demo = createDemoProject();
          setProject(demo);
        } else {
          setProject(null);
        }
      }
    }
    init();
  }, [loadProjectDetail]);

  // Connect WebSocket for real-time updates
  useEffect(() => {
    if (!project || project.id.startsWith('proj-alpha')) return; // Don't connect WS for static demo

    const ws = connectWebSocket(project.id, (message) => {
      console.log('Received WebSocket message:', message);
      // Trigger a refresh of project detail on any pipeline state update
      loadProjectDetail(project.id);

      // Show toast on specific events
      if (message.type === 'phase_started') {
        addToast('⚡', `Started: ${message.data?.phase_name}`);
      } else if (message.type === 'phase_completed') {
        addToast('✓', `Completed phase!`);
      } else if (message.type === 'approval_requested') {
        addToast('⏳', `Approval required for ${message.data?.checkpoint}`);
      } else if (message.type === 'pipeline_complete') {
        addToast('🎉', 'Pipeline completed successfully!');
      } else if (message.type === 'pipeline_error') {
        addToast('✗', `Pipeline error: ${message.data?.error}`);
      }
    });

    return () => {
      ws.close();
    };
  }, [project?.id, loadProjectDetail, addToast]);

  // Handle new project creation
  const handleProjectCreated = useCallback((newProject: Project) => {
    localStorage.removeItem('aikyam_demo_cleared'); // Reset flag on creation
    setProject(newProject);
    setActiveView('pipeline');
    addToast('🚀', `Pipeline started for "${newProject.name}"`);
  }, [addToast]);

  // Handle human approval action
  const handleApprovalAction = useCallback(async (phaseId: number, decision: 'approved' | 'rejected', feedback?: string) => {
    if (!project) return;
    addToast('⏳', `Submitting ${decision}...`);
    const success = await approvePhase(project.id, phaseId, decision, feedback);
    if (success) {
      addToast('✓', `Phase ${phaseId} ${decision}`);
      await loadProjectDetail(project.id);
    } else {
      addToast('❌', 'Failed to submit decision');
    }
  }, [project, addToast, loadProjectDetail]);

  // Handle clearing/deleting the current project
  const handleClearProject = useCallback(async () => {
    if (!project) return;
    localStorage.setItem('aikyam_demo_cleared', 'true'); // Save dismissed preference
    if (project.id.startsWith('proj-alpha')) {
      // Mock demo project
      setProject(null);
      addToast('🧹', 'Demo project cleared');
      return;
    }

    addToast('⏳', 'Clearing project...');
    const success = await deleteProject(project.id);
    if (success) {
      setProject(null);
      addToast('🧹', 'Project cleared successfully');
    } else {
      addToast('❌', 'Failed to clear project');
    }
  }, [project, addToast]);

  if (activeView === 'review') {
    return (
      <div className="app-layout" style={{ display: 'block', height: '100vh', width: '100vw', overflowY: 'auto', background: 'var(--bg-primary)' }}>
        <div className="topbar" style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="topbar-left">
            <h1 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0 }}>Aikyam Validation Portal</h1>
          </div>
          <div className="topbar-right">
            <button 
              className="btn btn-secondary" 
              onClick={() => {
                const search = urlToken ? `?token=${urlToken}` : '';
                window.location.href = `/client/${urlProjectId || project?.id}${search}`;
              }}
            >
              📋 View Project Dashboard
            </button>
          </div>
        </div>
        <ReviewPage 
          projectId={urlProjectId || project?.id || ''} 
          token={urlToken} 
          onApproveSuccess={() => loadProjectDetail(urlProjectId || project?.id || '')} 
        />
        {/* Toast notifications */}
        {toasts.length > 0 && (
          <div className="toast-container">
            {toasts.map(toast => (
              <div className="toast" key={toast.id}>
                <span className="toast-icon">{toast.icon}</span>
                <span>{toast.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (activeView === 'client-dashboard') {
    return (
      <div className="app-layout" style={{ display: 'block', height: '100vh', width: '100vw', overflowY: 'auto', background: 'var(--bg-primary)' }}>
        <div className="topbar" style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="topbar-left">
            <h1 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0 }}>Aikyam Client Portal</h1>
          </div>
          <div className="topbar-right">
            <button 
              className="btn btn-primary" 
              onClick={() => {
                const search = urlToken ? `?token=${urlToken}` : '';
                window.location.href = `/review/${urlProjectId || project?.id}${search}`;
              }}
            >
              📋 Review PRD Document
            </button>
          </div>
        </div>
        <ClientDashboard 
          projectId={urlProjectId || project?.id || ''} 
          token={urlToken} 
          onOpenReview={() => {
            const search = urlToken ? `?token=${urlToken}` : '';
            window.location.href = `/review/${urlProjectId || project?.id}${search}`;
          }}
        />
        {/* Toast notifications */}
        {toasts.length > 0 && (
          <div className="toast-container">
            {toasts.map(toast => (
              <div className="toast" key={toast.id}>
                <span className="toast-icon">{toast.icon}</span>
                <span>{toast.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <Sidebar
        activeView={activeView}
        onViewChange={setActiveView}
        projectName={project?.name}
        projectStatus={project?.status}
        currentPhase={project?.currentPhase}
      />

      {/* Main content */}
      <div className="main-content">
        {/* Top bar */}
        <div className="topbar">
          <div className="topbar-left">
            <div className="topbar-breadcrumb">
              <span>Aikyam</span>
              <span style={{ opacity: 0.3 }}>/</span>
              <span className="current">
                {activeView === 'pipeline' && 'Pipeline'}
                {activeView === 'new-project' && 'New Project'}
                {activeView === 'settings' && 'Settings'}
                {activeView === 'logs' && 'All Logs'}
              </span>
            </div>
          </div>
          <div className="topbar-right">
            {project && activeView === 'pipeline' && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '4px 12px',
                background: project.status === 'running'
                  ? 'rgba(79, 143, 255, 0.1)'
                  : 'var(--bg-glass)',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: project.status === 'running'
                  ? 'var(--accent-blue)'
                  : 'var(--text-muted)',
                border: `1px solid ${project.status === 'running'
                  ? 'rgba(79, 143, 255, 0.2)'
                  : 'var(--border-subtle)'}`,
              }}>
                {project.status === 'running' && (
                  <div className="status-dot connected" style={{ width: 6, height: 6 }} />
                )}
                {project.status === 'running' ? 'Pipeline Running' : project.status}
              </div>
            )}
            {project && (
              <button
                className="btn btn-secondary"
                style={{ marginRight: '8px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', color: '#ef4444' }}
                onClick={handleClearProject}
              >
                🗑️ Clear Project
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={() => setActiveView('new-project')}
            >
              ➕ New Project
            </button>
          </div>
        </div>

        {/* Content */}
        {activeView === 'pipeline' && project && (
          <PipelineView project={project} onApproval={handleApprovalAction} />
        )}

        {activeView === 'pipeline' && !project && (
          <div className="empty-state">
            <div className="empty-state-icon">🏗️</div>
            <h3>No Active Project</h3>
            <p>Create a new project to start the multi-agent SDLC pipeline.</p>
            <button
              className="btn btn-primary btn-lg"
              onClick={() => setActiveView('new-project')}
            >
              🚀 Launch New Project
            </button>
          </div>
        )}

        {activeView === 'new-project' && (
          <NewProjectView onProjectCreated={handleProjectCreated} />
        )}

        {activeView === 'settings' && (
          <div className="pipeline-container">
            <div style={{ maxWidth: '700px', margin: '32px auto' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '24px' }}>
                ⚙️ Settings
              </h2>

              {/* LLM Providers */}
              <div style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-lg)',
                padding: '24px',
                marginBottom: '16px',
              }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '16px' }}>
                  🤖 LLM Providers
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {[
                    { name: 'Google Gemini', status: 'Connected', color: 'var(--accent-green)' },
                    { name: 'Ollama (Local)', status: 'Not configured', color: 'var(--text-muted)' },
                    { name: 'vLLM (Local)', status: 'Not configured', color: 'var(--text-muted)' },
                    { name: 'Groq', status: 'Not configured', color: 'var(--text-muted)' },
                    { name: 'OpenAI', status: 'Not configured', color: 'var(--text-muted)' },
                  ].map(provider => (
                    <div key={provider.name} style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      background: 'var(--bg-glass)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.8rem',
                    }}>
                      <span>{provider.name}</span>
                      <span style={{ color: provider.color, fontWeight: 500 }}>{provider.status}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Integrations */}
              <div style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-lg)',
                padding: '24px',
                marginBottom: '16px',
              }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '16px' }}>
                  🔗 Integrations
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {[
                    { name: '📡 Slack', status: 'Connected', detail: 'Socket Mode' },
                    { name: '🎫 Jira', status: 'Connected', detail: 'MAT project' },
                    { name: '🐙 GitHub', status: 'Connected', detail: 'aikyam org' },
                    { name: '🐳 Docker', status: 'Available', detail: 'v24.0' },
                  ].map(int => (
                    <div key={int.name} style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      background: 'var(--bg-glass)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.8rem',
                    }}>
                      <span>{int.name}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>{int.detail}</span>
                        <span style={{ color: 'var(--accent-green)', fontWeight: 500 }}>{int.status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeView === 'logs' && project && (
          <div className="pipeline-container">
            <div style={{ maxWidth: '900px', margin: '32px auto' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '24px' }}>
                📊 All Execution Logs
              </h2>

              {/* Cost Cards */}
              <div className="cost-cards">
                <div className="cost-card">
                  <div className="cost-card-label">Total Tokens</div>
                  <div className="cost-card-value blue">{project.totalTokens.toLocaleString()}</div>
                </div>
                <div className="cost-card">
                  <div className="cost-card-label">Total Cost</div>
                  <div className="cost-card-value green">${project.totalCost.toFixed(3)}</div>
                </div>
                <div className="cost-card">
                  <div className="cost-card-label">Phases Complete</div>
                  <div className="cost-card-value purple">
                    {project.phases.filter(p => p.status === 'success').length}/{project.phases.length}
                  </div>
                </div>
                <div className="cost-card">
                  <div className="cost-card-label">Active Phase</div>
                  <div className="cost-card-value orange">
                    #{project.currentPhase}
                  </div>
                </div>
              </div>

              {/* Combined log viewer */}
              <div className="log-viewer" style={{ maxHeight: '600px' }}>
                {project.phases
                  .filter(p => p.logs.length > 0)
                  .flatMap(p => p.logs.map(log => ({
                    ...log,
                    phaseId: p.id,
                    phaseName: p.name,
                    phaseIcon: p.icon,
                  })))
                  .map((log, i) => (
                    <div className="log-line" key={i}>
                      <span className="log-time">{log.time}</span>
                      <span style={{
                        color: 'var(--text-muted)',
                        flexShrink: 0,
                        fontSize: '0.65rem',
                        minWidth: '20px',
                        textAlign: 'center',
                      }}>
                        {log.phaseIcon}
                      </span>
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
            </div>
          </div>
        )}
      </div>

      {/* Toast notifications */}
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map(toast => (
            <div className="toast" key={toast.id}>
              <span className="toast-icon">{toast.icon}</span>
              <span>{toast.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default App;
