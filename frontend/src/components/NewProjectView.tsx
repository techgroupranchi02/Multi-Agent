import React, { useState } from 'react';
import { createDefaultPhases } from '../data';
import type { Project } from '../types';
import { createNewProject } from '../api';

interface NewProjectViewProps {
  onProjectCreated: (project: Project) => void;
}

export const NewProjectView: React.FC<NewProjectViewProps> = ({ onProjectCreated }) => {
  const [projectName, setProjectName] = useState('');
  const [requirements, setRequirements] = useState('');
  const [llmProvider, setLlmProvider] = useState('gemini');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectName.trim() || !requirements.trim()) return;

    setIsSubmitting(true);

    const result = await createNewProject(projectName, requirements, llmProvider);
    setIsSubmitting(false);

    if (result) {
      // Create a skeleton project and pass it back
      const project: Project = {
        id: result.id,
        name: result.name,
        rawRequirements: requirements,
        status: 'running',
        currentPhase: 1,
        phases: createDefaultPhases(),
        createdAt: new Date().toISOString(),
        totalTokens: 0,
        totalCost: 0,
      };

      // Start phase 1 as running
      project.phases[0].status = 'running';
      project.phases[0].progress = 10;
      project.phases[0].logs.push({
        time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        level: 'info',
        message: 'Pipeline started — Requirements Agent initializing...',
      });

      onProjectCreated(project);
    }
  };

  return (
    <div className="pipeline-container">
      <div className="new-project-view">
        <h2>🚀 Launch New Project</h2>
        <p className="subtitle">
          Provide your raw requirements and the multi-agent pipeline will handle everything —
          from PRD to production deployment.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Project Name</label>
            <input
              type="text"
              placeholder="e.g., E-Commerce Platform, Task Manager API, SaaS Dashboard..."
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label>Raw Requirements</label>
            <textarea
              placeholder={`Describe your project requirements in plain language. Be as detailed as possible.\n\nExample:\n"Build a task management API with:\n- User authentication (JWT)\n- CRUD operations for tasks and projects\n- Role-based access control (admin, manager, member)\n- Real-time notifications via WebSocket\n- PostgreSQL database\n- REST API with OpenAPI docs"`}
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              required
              style={{ minHeight: '250px' }}
            />
          </div>

          <div className="form-group">
            <label>LLM Provider (for Requirements Agent)</label>
            <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}>
              <option value="gemini">Google Gemini 2.5 Pro</option>
              <option value="gpt4o">OpenAI GPT-4o</option>
              <option value="ollama">Ollama (Local)</option>
              <option value="vllm">vLLM (Local)</option>
              <option value="groq">Groq (Llama 3.1)</option>
            </select>
          </div>

          {/* Config summary */}
          <div style={{
            padding: '16px 20px',
            background: 'var(--bg-glass)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            marginBottom: '24px',
            fontSize: '0.78rem',
          }}>
            <div style={{ fontWeight: 600, marginBottom: '8px', color: 'var(--text-primary)' }}>
              Pipeline Configuration
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', color: 'var(--text-secondary)' }}>
              <span>📡 Notifications:</span><span style={{ color: 'var(--text-primary)' }}>Slack</span>
              <span>🎫 Task Tracking:</span><span style={{ color: 'var(--text-primary)' }}>Jira (MAT)</span>
              <span>🐙 Version Control:</span><span style={{ color: 'var(--text-primary)' }}>GitHub</span>
              <span>🐳 Sandbox:</span><span style={{ color: 'var(--text-primary)' }}>Docker</span>
              <span>🖥️ Deploy Target:</span><span style={{ color: 'var(--text-primary)' }}>VPS (Linux)</span>
              <span>📊 Total Phases:</span><span style={{ color: 'var(--text-primary)' }}>14</span>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            disabled={!projectName.trim() || !requirements.trim() || isSubmitting}
            style={{
              width: '100%',
              justifyContent: 'center',
              opacity: (!projectName.trim() || !requirements.trim()) ? 0.5 : 1,
            }}
          >
            {isSubmitting ? (
              <>⏳ Initializing Pipeline...</>
            ) : (
              <>🚀 Launch Pipeline</>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
