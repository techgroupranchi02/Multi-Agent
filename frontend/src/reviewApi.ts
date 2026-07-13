import type { ReviewStatus, PRDVersion, ReviewSession } from './types';

const API_BASE = '/api/review';
const CLIENT_API_BASE = '/api/client';

/**
 * Helper to build headers and URL with query token
 */
function buildUrl(path: string, token?: string): string {
  if (token) {
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}token=${encodeURIComponent(token)}`;
  }
  return path;
}

export async function fetchReviewStatus(projectId: string, token?: string): Promise<ReviewStatus | null> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}`, token));
    if (!res.ok) throw new Error('Failed to fetch review status');
    return await res.json();
  } catch (err) {
    console.error('fetchReviewStatus error:', err);
    return null;
  }
}

export async function fetchQuestionnaire(projectId: string, token?: string): Promise<any | null> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/questionnaire`, token));
    if (!res.ok) throw new Error('Failed to fetch questionnaire');
    return await res.json();
  } catch (err) {
    console.error('fetchQuestionnaire error:', err);
    return null;
  }
}

export async function submitSectionResponses(
  projectId: string,
  sectionName: string,
  responses: Array<{ id: string; answer: any; confidence?: number }>,
  token?: string
): Promise<boolean> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/questionnaire/${encodeURIComponent(sectionName)}`, token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_name: sectionName,
        responses: responses.map(r => ({
          question_id: r.id,
          answer: String(r.answer),
          confidence: r.confidence || 3,
        })),
      }),
    });
    if (!res.ok) throw new Error('Failed to submit responses');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('submitSectionResponses error:', err);
    return false;
  }
}

export async function submitTextFeedback(
  projectId: string,
  feedbackText: string,
  token?: string
): Promise<any | null> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/feedback/text`, token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback_text: feedbackText }),
    });
    if (!res.ok) throw new Error('Failed to submit text feedback');
    return await res.json();
  } catch (err) {
    console.error('submitTextFeedback error:', err);
    return null;
  }
}

export async function uploadFeedbackFile(
  projectId: string,
  file: File,
  token?: string
): Promise<any | null> {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/feedback/upload`, token), {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to upload file');
    return await res.json();
  } catch (err) {
    console.error('uploadFeedbackFile error:', err);
    return null;
  }
}

export async function fetchImpactPreview(projectId: string, token?: string): Promise<any | null> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/impact-preview`, token));
    if (!res.ok) throw new Error('Failed to fetch impact preview');
    const data = await res.json();
    return data.impact || null;
  } catch (err) {
    console.error('fetchImpactPreview error:', err);
    return null;
  }
}

export async function lockSection(
  projectId: string,
  sectionName: string,
  lockedBy: string = 'client',
  token?: string
): Promise<boolean> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/sections/${encodeURIComponent(sectionName)}/lock`, token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locked_by: lockedBy }),
    });
    if (!res.ok) throw new Error('Failed to lock section');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('lockSection error:', err);
    return false;
  }
}

export async function unlockSection(
  projectId: string,
  sectionName: string,
  token?: string
): Promise<boolean> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/sections/${encodeURIComponent(sectionName)}/lock`, token), {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to unlock section');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('unlockSection error:', err);
    return false;
  }
}

export async function triggerRegeneration(projectId: string, token?: string): Promise<boolean> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/regenerate`, token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    });
    if (!res.ok) throw new Error('Failed to trigger regeneration');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('triggerRegeneration error:', err);
    return false;
  }
}

export async function approvePRD(projectId: string, token?: string): Promise<boolean> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/approve`, token), {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to approve PRD');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('approvePRD error:', err);
    return false;
  }
}

export async function fetchVersions(projectId: string, token?: string): Promise<PRDVersion[]> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/versions`, token));
    if (!res.ok) throw new Error('Failed to fetch versions');
    const data = await res.json();
    return data.versions || [];
  } catch (err) {
    console.error('fetchVersions error:', err);
    return [];
  }
}

export async function fetchVersionDetail(
  projectId: string,
  version: number,
  token?: string
): Promise<any | null> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/versions/${version}`, token));
    if (!res.ok) throw new Error('Failed to fetch version detail');
    return await res.json();
  } catch (err) {
    console.error('fetchVersionDetail error:', err);
    return null;
  }
}

export async function fetchClientDashboard(projectId: string, token?: string): Promise<any | null> {
  try {
    const res = await fetch(buildUrl(`${CLIENT_API_BASE}/${projectId}`, token));
    if (!res.ok) throw new Error('Failed to fetch client dashboard');
    return await res.json();
  } catch (err) {
    console.error('fetchClientDashboard error:', err);
    return null;
  }
}

export async function submitQuickResponses(
  projectId: string,
  responses: Record<string, string>,
  token?: string
): Promise<boolean> {
  try {
    const res = await fetch(buildUrl(`${API_BASE}/${projectId}/quick`, token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ responses }),
    });
    if (!res.ok) throw new Error('Failed to submit quick responses');
    const data = await res.json();
    return data.status === 'ok';
  } catch (err) {
    console.error('submitQuickResponses error:', err);
    return false;
  }
}
