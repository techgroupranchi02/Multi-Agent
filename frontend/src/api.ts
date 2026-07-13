import type { Project } from './types';

const API_BASE = '/api';
const WS_BASE = `ws://${window.location.host}/api`;

// Helper to convert backend project keys to frontend types
export function mapBackendProjectToFrontend(data: any): Project {
  return {
    id: data.id,
    name: data.name,
    rawRequirements: data.raw_requirements || '',
    status: data.status || 'draft',
    currentPhase: data.current_phase || 1,
    createdAt: data.created_at || new Date().toISOString(),
    totalTokens: data.total_tokens || 0,
    totalCost: data.total_cost_usd || 0.0,
    jiraEpicKey: data.jira_epic_key,
    githubRepo: data.git_repo,
    stagingUrl: data.staging_url,
    productionUrl: data.production_url,
    latestPrdGdocUrl: data.latest_prd_gdoc_url,
    phases: (data.phases || []).map((p: any) => ({
      id: p.id,
      name: p.name,
      agent: p.agent,
      icon: p.icon,
      description: p.description,
      outputs: p.outputs || [],
      outputArtifacts: p.output_artifacts || {},
      logsToJira: p.logs_to_jira || false,
      status: p.status || 'idle',
      progress: p.progress || 0,
      logs: (p.logs || []).map((l: any) => ({
        time: l.time || '',
        level: l.level || 'info',
        message: l.message || '',
      })),
      duration: p.duration,
      retryCount: p.retry_count,
      maxRetries: p.max_retries,
    })),
  };
}

export async function fetchProjects(): Promise<Project[]> {
  try {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    const data = await res.json();
    return (data.projects || []).map((p: any) => ({
      id: p.id,
      name: p.name,
      status: p.status,
      currentPhase: p.current_phase,
      createdAt: p.created_at,
      totalTokens: p.total_tokens || 0,
      totalCost: p.total_cost_usd || 0,
      jiraEpicKey: p.jira_epic_key,
    }));
  } catch (err) {
    console.error('fetchProjects error:', err);
    return [];
  }
}

export async function fetchProjectDetail(projectId: string): Promise<Project | null> {
  try {
    const res = await fetch(`${API_BASE}/projects/${projectId}`);
    if (!res.ok) throw new Error('Failed to fetch project detail');
    const data = await res.json();
    return mapBackendProjectToFrontend(data);
  } catch (err) {
    console.error('fetchProjectDetail error:', err);
    return null;
  }
}

export async function createNewProject(
  name: string,
  rawRequirements: string,
  llmProvider?: string
): Promise<{ id: string; name: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        raw_requirements: rawRequirements,
        llm_provider: llmProvider,
      }),
    });
    if (!res.ok) throw new Error('Failed to create project');
    return await res.json();
  } catch (err) {
    console.error('createNewProject error:', err);
    return null;
  }
}

export async function approvePhase(
  projectId: string,
  phaseId: number,
  decision: 'approved' | 'rejected',
  feedback?: string
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/projects/${projectId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        phase_id: phaseId,
        decision,
        feedback,
      }),
    });
    if (!res.ok) throw new Error('Failed to submit approval');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('approvePhase error:', err);
    return false;
  }
}

export async function deleteProject(projectId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      if (res.status === 404) {
        // Project is already gone (e.g. backend was restarted)
        return true;
      }
      throw new Error('Failed to delete project');
    }
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('deleteProject error:', err);
    return false;
  }
}

export function connectWebSocket(
  projectId: string | null,
  onMessage: (msg: any) => void
): WebSocket {
  const url = projectId
    ? `${WS_BASE}/ws?project_id=${projectId}`
    : `${WS_BASE}/ws`;
  const ws = new WebSocket(url);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (err) {
      console.error('WS parse error:', err);
    }
  };

  ws.onerror = (err) => {
    console.error('WS error:', err);
  };

  return ws;
}

export async function fetchArtifactContent(
  projectId: string,
  artifactName: string
): Promise<{ content: string; googleDocUrl?: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/projects/${projectId}/artifacts/${artifactName}`);
    if (!res.ok) throw new Error('Failed to fetch artifact');
    const data = await res.json();
    return {
      content: data.content || '',
      googleDocUrl: data.google_doc_url || undefined,
    };
  } catch (err) {
    console.error('fetchArtifactContent error:', err);
    return null;
  }
}
