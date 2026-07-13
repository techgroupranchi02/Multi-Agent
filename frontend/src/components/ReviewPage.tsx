import React, { useState, useEffect, useRef } from 'react';
import type { ReviewStatus, PRDVersion } from '../types';
import {
  fetchReviewStatus,
  fetchQuestionnaire,
  submitTextFeedback,
  uploadFeedbackFile,
  lockSection,
  unlockSection,
  fetchImpactPreview,
  triggerRegeneration,
  approvePRD,
  fetchVersions,
  submitQuickResponses,
} from '../reviewApi';
import { QuestionnaireSection } from './QuestionnaireSection';

interface ReviewPageProps {
  projectId: string;
  token?: string;
  onApproveSuccess?: () => void;
}

export function ReviewPage({ projectId, token, onApproveSuccess }: ReviewPageProps) {
  const [status, setStatus] = useState<ReviewStatus | null>(null);
  const [questionnaire, setQuestionnaire] = useState<any | null>(null);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [textFeedback, setTextFeedback] = useState('');
  const [fileFeedback, setFileFeedback] = useState<File | null>(null);
  const [versions, setVersions] = useState<PRDVersion[]>([]);
  const [impactPreview, setImpactPreview] = useState<any | null>(null);
  const [showImpactModal, setShowImpactModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeMode, setActiveMode] = useState<'detailed' | 'quick'>('detailed');
  const [quickAnswers, setQuickAnswers] = useState<Record<string, string>>({});
  const [submittingQuick, setSubmittingQuick] = useState(false);

  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const [otherTexts, setOtherTexts] = useState<Record<string, string>>({});

  const loadData = async () => {
    setLoading(true);
    const [reviewStatus, qData, vList] = await Promise.all([
      fetchReviewStatus(projectId, token),
      fetchQuestionnaire(projectId, token),
      fetchVersions(projectId, token),
    ]);

    if (reviewStatus) {
      setStatus(reviewStatus);
      if (reviewStatus.review_mode) {
        setActiveMode(reviewStatus.review_mode as 'detailed' | 'quick');
      }
      if (reviewStatus.quick_responses) {
        setQuickAnswers(prev => ({
          ...reviewStatus.quick_responses,
          ...prev,
        }));
      }
    }
    if (qData) setQuestionnaire(qData);
    if (vList) setVersions(vList);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  useEffect(() => {
    if (status?.quick_questions) {
      const initialSelected: Record<string, string> = {};
      const initialOthers: Record<string, string> = {};
      
      status.quick_questions.forEach((q: any) => {
        const answer = quickAnswers[q.id] || status.quick_responses?.[q.id] || '';
        if (q.type === 'multiple_choice' && q.options) {
          if (answer === '') {
            initialSelected[q.id] = '';
          } else if (q.options.includes(answer)) {
            initialSelected[q.id] = answer;
          } else {
            initialSelected[q.id] = 'Others';
            initialOthers[q.id] = answer;
          }
        }
      });
      
      setSelectedOptions(prev => {
        const next = { ...prev };
        Object.keys(initialSelected).forEach(k => {
          if (next[k] === undefined) {
            next[k] = initialSelected[k];
          }
        });
        return next;
      });

      setOtherTexts(prev => {
        const next = { ...prev };
        Object.keys(initialOthers).forEach(k => {
          if (next[k] === undefined) {
            next[k] = initialOthers[k];
          }
        });
        return next;
      });
    }
  }, [status]);

  const handleSectionComplete = async () => {
    setActiveSection(null);
    await loadData();
  };

  const handleTextFeedbackSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textFeedback.trim()) return;

    setSubmittingFeedback(true);
    const result = await submitTextFeedback(projectId, textFeedback, token);
    setSubmittingFeedback(false);

    if (result) {
      setTextFeedback('');
      alert('Feedback submitted successfully!');
      await loadData();
    } else {
      alert('Failed to submit feedback.');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSubmittingFeedback(true);
    const result = await uploadFeedbackFile(projectId, file, token);
    setSubmittingFeedback(false);

    if (result) {
      alert(`File "${file.name}" uploaded and parsed successfully!`);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await loadData();
    } else {
      alert('Failed to upload file.');
    }
  };

  const handleLockToggle = async (sectionName: string, isLocked: boolean) => {
    let success = false;
    if (isLocked) {
      success = await unlockSection(projectId, sectionName, token);
    } else {
      success = await lockSection(projectId, sectionName, 'client', token);
    }

    if (success) {
      await loadData();
    } else {
      alert('Failed to update section lock status.');
    }
  };

  const handleRegenerationRequest = async () => {
    setRegenerating(true);
    const preview = await fetchImpactPreview(projectId, token);
    setRegenerating(false);

    if (preview) {
      setImpactPreview(preview);
      setShowImpactModal(true);
    } else {
      alert('Failed to generate impact preview.');
    }
  };

  const confirmRegeneration = async () => {
    setShowImpactModal(false);
    setRegenerating(true);
    const success = await triggerRegeneration(projectId, token);
    setRegenerating(false);

    if (success) {
      alert('PRD regeneration started! We will notify you in Slack and refresh the page when it is ready.');
      await loadData();
    } else {
      alert('Failed to trigger regeneration.');
    }
  };

  const handleApprove = async () => {
    if (!window.confirm('Are you sure you want to approve this PRD? This will lock requirements and proceed to the Design phase.')) {
      return;
    }

    setApproving(true);
    const success = await approvePRD(projectId, token);
    setApproving(false);

    if (success) {
      alert('PRD approved! Moving to System Design & Architecture.');
      if (onApproveSuccess) onApproveSuccess();
      await loadData();
    } else {
      alert('Failed to approve PRD.');
    }
  };

  const handleQuickSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check if at least one question is answered
    const hasAnswers = Object.values(quickAnswers).some(val => val.trim().length > 0);
    if (!hasAnswers) {
      alert('Please answer at least one question before submitting.');
      return;
    }

    if (!window.confirm('Submitting these answers will save them and immediately start generating the next PRD version. Would you like to proceed?')) {
      return;
    }

    setSubmittingQuick(true);
    const success = await submitQuickResponses(projectId, quickAnswers, token);
    setSubmittingQuick(false);

    if (success) {
      alert('Your feedback has been saved and PRD regeneration has started! We will notify you in Slack and refresh the page when it is ready.');
      await loadData();
    } else {
      alert('Failed to submit quick responses.');
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="status-dot connected" style={{ width: 16, height: 16, marginBottom: 16 }} />
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Loading review session details...</span>
      </div>
    );
  }

  if (!status || !status.has_prd) {
    return (
      <div className="empty-state" style={{ padding: '40px 20px' }}>
        <h3>No PRD Available for Review</h3>
        <p>A requirements document has not been generated for this project yet.</p>
      </div>
    );
  }

  const currentQuestions = questionnaire?.sections?.find(
    (s: any) => s.section_name === activeSection
  )?.questions || [];

  const readiness = status.readiness;
  const sections = status.section_scores || [];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px', padding: '24px' }}>
      
      {/* Left Column: Questionnaire & Document Content */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* active questionnaire section */}
        {activeSection && (
          <QuestionnaireSection
            projectId={projectId}
            token={token}
            sectionName={activeSection}
            questions={currentQuestions}
            onComplete={handleSectionComplete}
            onClose={() => setActiveSection(null)}
          />
        )}

        {/* Understanding Scores List */}
        <div className="card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>Requirement Understanding</h2>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
                Validate the generated requirements using either a detailed section-by-section check or quick overall questions.
              </p>
            </div>
            {status.prd_approved && (
              <span style={{
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                color: '#10b981',
                padding: '4px 10px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.7rem',
                fontWeight: 700,
              }}>
                ✓ APPROVED
              </span>
            )}
          </div>

          {/* Mode Switcher */}
          <div style={{
            display: 'flex',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '4px',
            marginBottom: '20px',
          }}>
            <button
              type="button"
              onClick={() => setActiveMode('detailed')}
              style={{
                flex: 1,
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                fontWeight: 600,
                padding: '8px 16px',
                background: activeMode === 'detailed' ? 'var(--accent-blue)' : 'transparent',
                border: 'none',
                color: activeMode === 'detailed' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              Detailed Validation (Section-by-Section)
            </button>
            <button
              type="button"
              onClick={() => setActiveMode('quick')}
              style={{
                flex: 1,
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                fontWeight: 600,
                padding: '8px 16px',
                background: activeMode === 'quick' ? 'var(--accent-blue)' : 'transparent',
                border: 'none',
                color: activeMode === 'quick' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              Quick Validation (Global Open Questions)
            </button>
          </div>

          {activeMode === 'detailed' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {sections.map(section => {
                const displayScore = section.understanding_score ?? section.ai_confidence;
                const hasValidated = section.understanding_score !== null;
                
                return (
                  <div key={section.section_name} style={{
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    transition: 'border-color 0.2s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{section.section_name}</span>
                        {section.locked && (
                          <span style={{
                            background: 'rgba(79, 143, 255, 0.1)',
                            color: 'var(--accent-blue)',
                            fontSize: '0.65rem',
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: 'var(--radius-sm)',
                          }}>
                            🔒 Locked
                          </span>
                        )}
                      </div>
                      
                      {/* Score badge */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '0.85rem', fontWeight: 700, color: displayScore >= 85 ? 'var(--accent-green)' : displayScore >= 60 ? 'var(--accent-orange)' : '#ef4444' }}>
                            {displayScore.toFixed(0)}%
                          </div>
                          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
                            {hasValidated ? 'Understanding' : 'AI Confidence'}
                          </div>
                        </div>
                        
                        {/* Action buttons */}
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          {status.gdoc_url && (
                            <a
                              href={(() => {
                                if (!section.gdoc_heading_id) return status.gdoc_url;
                                const match = status.gdoc_url.match(/\/d\/([^/]+)/);
                                if (match && match[1]) {
                                  return `https://docs.google.com/document/d/${match[1]}/edit#heading=h.${section.gdoc_heading_id}`;
                                }
                                return status.gdoc_url;
                              })()}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-secondary"
                              style={{
                                padding: '6px 8px',
                                fontSize: '0.75rem',
                                textDecoration: 'none',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              📄 View in Doc ↗
                            </a>
                          )}
                          {!status.prd_approved && (
                            <>
                              {!section.locked && section.question_count > 0 && (
                                <button
                                  className="btn"
                                  onClick={() => {
                                    setActiveSection(section.section_name);
                                    const container = document.querySelector('.app-layout');
                                    if (container) {
                                      container.scrollTo({ top: 0, behavior: 'smooth' });
                                    }
                                  }}
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '0.75rem',
                                    background: hasValidated ? 'rgba(34, 197, 94, 0.12)' : 'var(--accent-blue)',
                                    border: hasValidated ? '1px solid rgba(34, 197, 94, 0.3)' : '1px solid var(--accent-blue)',
                                    color: hasValidated ? 'var(--accent-green)' : '#fff',
                                    cursor: 'pointer',
                                    borderRadius: 'var(--radius-sm)',
                                    fontWeight: 600,
                                    transition: 'all 0.2s',
                                  }}
                                >
                                  {hasValidated ? '✓ Validated' : 'Validate'}
                                </button>
                              )}
                              <button
                                className="btn btn-secondary"
                                onClick={() => handleLockToggle(section.section_name, section.locked)}
                                disabled={displayScore < 95 && !section.locked} // Lock only if score >= 95
                                style={{
                                  padding: '6px',
                                  fontSize: '0.75rem',
                                  opacity: displayScore < 95 && !section.locked ? 0.4 : 1,
                                }}
                                title={displayScore < 95 && !section.locked ? "Lock requires score ≥95%" : ""}
                              >
                                {section.locked ? '🔓 Unlock' : '🔒 Lock'}
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Why low explanation */}
                    {section.why_low && section.why_low.length > 0 && displayScore < 95 && (
                      <div style={{
                        background: 'rgba(239, 68, 68, 0.03)',
                        border: '1px solid rgba(239, 68, 68, 0.1)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '10px 14px',
                        fontSize: '0.75rem',
                        color: 'rgba(255,255,255,0.7)',
                      }}>
                        <div style={{ fontWeight: 600, color: '#ef4444', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>⚠️ Why is this score low?</span>
                        </div>
                        <ul style={{ margin: 0, paddingLeft: '16px' }}>
                          {section.why_low.map((reason, idx) => (
                            <li key={idx} style={{ marginBottom: '2px' }}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <form onSubmit={handleQuickSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{
                background: 'rgba(79, 143, 255, 0.03)',
                border: '1px solid rgba(79, 143, 255, 0.1)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
                fontSize: '0.8rem',
                color: 'var(--text-muted)',
                lineHeight: 1.4,
              }}>
                ℹ️ <strong>Quick Validation Mode:</strong> Answer the high-level open questions below. When you click <strong>Submit & Generate Next Version</strong>, we will save your responses and automatically start generating a revised version of the PRD incorporating your answers.
              </div>

              {(!status.quick_questions || status.quick_questions.length === 0) ? (
                <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No global open questions generated for this version.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {status.quick_questions.map((q, idx) => (
                    <div key={q.id} style={{
                      background: 'rgba(255, 255, 255, 0.01)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                    }}>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#fff' }}>
                        {idx + 1}. {q.text}
                      </div>
                      {q.context && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                          Context: {q.context}
                        </div>
                      )}
                      {q.type === 'multiple_choice' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
                          {q.options?.map((option: string) => {
                            const isSelected = selectedOptions[q.id] === option;
                            return (
                              <button
                                key={option}
                                type="button"
                                disabled={status.prd_approved || submittingQuick}
                                onClick={() => {
                                  setSelectedOptions(prev => ({ ...prev, [q.id]: option }));
                                  setQuickAnswers(prev => ({ ...prev, [q.id]: option }));
                                }}
                                style={{
                                  textAlign: 'left',
                                  padding: '12px 16px',
                                  background: isSelected ? 'rgba(79, 143, 255, 0.15)' : 'rgba(255,255,255,0.02)',
                                  border: isSelected ? '1px solid var(--accent-blue)' : '1px solid var(--border-subtle)',
                                  color: isSelected ? 'var(--accent-blue)' : 'var(--text-main)',
                                  borderRadius: 'var(--radius-md)',
                                  fontWeight: 500,
                                  cursor: 'pointer',
                                  transition: 'all 0.2s',
                                }}
                              >
                                <span style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  width: '18px',
                                  height: '18px',
                                  borderRadius: '50%',
                                  border: isSelected ? '5px solid var(--accent-blue)' : '2px solid var(--text-muted)',
                                  marginRight: '12px',
                                  verticalAlign: 'middle',
                                }} />
                                {option}
                              </button>
                            );
                          })}
                          
                          {/* Others Option */}
                          {(() => {
                            const isOthersSelected = selectedOptions[q.id] === 'Others';
                            return (
                              <>
                                <button
                                  type="button"
                                  disabled={status.prd_approved || submittingQuick}
                                  onClick={() => {
                                    setSelectedOptions(prev => ({ ...prev, [q.id]: 'Others' }));
                                    setQuickAnswers(prev => ({ ...prev, [q.id]: otherTexts[q.id] || '' }));
                                  }}
                                  style={{
                                    textAlign: 'left',
                                    padding: '12px 16px',
                                    background: isOthersSelected ? 'rgba(79, 143, 255, 0.15)' : 'rgba(255,255,255,0.02)',
                                    border: isOthersSelected ? '1px solid var(--accent-blue)' : '1px solid var(--border-subtle)',
                                    color: isOthersSelected ? 'var(--accent-blue)' : 'var(--text-main)',
                                    borderRadius: 'var(--radius-md)',
                                    fontWeight: 500,
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                  }}
                                >
                                  <span style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    width: '18px',
                                    height: '18px',
                                    borderRadius: '50%',
                                    border: isOthersSelected ? '5px solid var(--accent-blue)' : '2px solid var(--text-muted)',
                                    marginRight: '12px',
                                    verticalAlign: 'middle',
                                  }} />
                                  Others
                                </button>
                                
                                {isOthersSelected && (
                                  <textarea
                                    value={otherTexts[q.id] || ''}
                                    onChange={(e) => {
                                      const val = e.target.value;
                                      setOtherTexts(prev => ({ ...prev, [q.id]: val }));
                                      setQuickAnswers(prev => ({ ...prev, [q.id]: val }));
                                    }}
                                    placeholder="Please write your answer here..."
                                    rows={3}
                                    disabled={status.prd_approved || submittingQuick}
                                    style={{
                                      width: '100%',
                                      padding: '10px 12px',
                                      background: 'rgba(0, 0, 0, 0.2)',
                                      border: '1px solid var(--border-subtle)',
                                      borderRadius: 'var(--radius-sm)',
                                      color: 'var(--text-main)',
                                      fontSize: '0.8rem',
                                      resize: 'vertical',
                                      outline: 'none',
                                      marginTop: '8px',
                                    }}
                                  />
                                )}
                              </>
                            );
                          })()}
                        </div>
                      ) : (
                        <textarea
                          value={quickAnswers[q.id] || ''}
                          onChange={(e) => setQuickAnswers(prev => ({
                            ...prev,
                            [q.id]: e.target.value,
                          }))}
                          placeholder="Type your response here..."
                          rows={3}
                          disabled={status.prd_approved || submittingQuick}
                          style={{
                            width: '100%',
                            padding: '10px 12px',
                            background: 'rgba(0, 0, 0, 0.2)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-sm)',
                            color: 'var(--text-main)',
                            fontSize: '0.8rem',
                            resize: 'vertical',
                            outline: 'none',
                          }}
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {!status.prd_approved && status.quick_questions && status.quick_questions.length > 0 && (
                <button
                  type="submit"
                  disabled={submittingQuick}
                  className="btn btn-primary"
                  style={{
                    background: 'linear-gradient(135deg, var(--accent-blue), #9333ea)',
                    border: 'none',
                    padding: '12px 24px',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    borderRadius: 'var(--radius-md)',
                    cursor: 'pointer',
                    width: '100%',
                    boxShadow: '0 4px 12px rgba(147, 51, 234, 0.3)',
                    transition: 'all 0.2s',
                  }}
                >
                  {submittingQuick ? 'Submitting & Starting Regeneration...' : '🚀 Submit & Generate Next Version'}
                </button>
              )}
            </form>
          )}
        </div>

        {/* Change evidence section (if v2+) */}
        {versions.length > 1 && (
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '16px' }}>✓ Traced Changes (Version Evidence)</h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '-8px', marginBottom: '16px' }}>
              We keep a complete audit trail showing which client feedback drove each change.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {status.current_version && status.current_version > 1 ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No changes tracked yet in this version cycle. In future iterations, we will list matching change evidence here.
                </div>
              ) : (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Traced changes will appear here when PRD version 2 or higher is generated.
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Right Column: Feedback Upload & Action Panel */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Action Panel */}
        <div className="card" style={{ padding: '24px', textAlign: 'center', background: 'linear-gradient(180deg, var(--bg-card), rgba(79, 143, 255, 0.02))' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '6px' }}>PRD Review v{status.current_version}</h3>
          
          {readiness && (
            <div style={{ margin: '16px 0' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Overall Requirement Understanding</div>
              <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent-blue)', margin: '4px 0' }}>
                {(readiness.overall_understanding_score ?? readiness.overall_ai_confidence).toFixed(0)}%
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                {readiness.completed_sections} of {readiness.total_sections} sections validated
              </div>
            </div>
          )}

          {status.gdoc_url && (
            <a
              href={status.gdoc_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
              style={{ display: 'block', width: '100%', marginBottom: '12px', textAlign: 'center' }}
            >
              📄 Open Google Doc Tab
            </a>
          )}

          {!status.prd_approved ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '16px' }}>
              <button
                className="btn btn-primary"
                onClick={handleRegenerationRequest}
                disabled={regenerating}
                style={{ width: '100%' }}
              >
                🔄 {regenerating ? 'Analyzing...' : 'Generate Next Version'}
              </button>
              
              <button
                className="btn btn-primary"
                onClick={handleApprove}
                disabled={approving}
                style={{
                  width: '100%',
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  border: 'none',
                }}
              >
                {approving ? 'Approving...' : '✓ Approve PRD & Proceed'}
              </button>
            </div>
          ) : (
            <div style={{
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.2)',
              borderRadius: 'var(--radius-md)',
              padding: '12px',
              color: '#10b981',
              fontWeight: 600,
              fontSize: '0.8rem',
              marginTop: '16px',
            }}>
              PRD Approved! Moving to Design.
            </div>
          )}
        </div>

        {/* Upload/Comments Panel */}
        {!status.prd_approved && (
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '16px' }}>Provide Feedback</h3>
            
            {/* Text form */}
            <form onSubmit={handleTextFeedbackSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
              <textarea
                value={textFeedback}
                onChange={(e) => setTextFeedback(e.target.value)}
                placeholder="Paste comments, requirements, or list changes needed..."
                rows={5}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  background: 'rgba(0,0,0,0.2)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--text-main)',
                  fontSize: '0.8rem',
                  resize: 'none',
                  outline: 'none',
                }}
              />
              <button
                type="submit"
                className="btn btn-secondary"
                disabled={!textFeedback.trim() || submittingFeedback}
                style={{ alignSelf: 'flex-end', padding: '6px 12px', fontSize: '0.75rem' }}
              >
                {submittingFeedback ? 'Submitting...' : 'Send Comments'}
              </button>
            </form>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '16px 0', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              <div style={{ flex: 1, height: '1px', background: 'var(--border-subtle)' }} />
              <span>OR UPLOAD FILE</span>
              <div style={{ flex: 1, height: '1px', background: 'var(--border-subtle)' }} />
            </div>

            {/* File upload */}
            <div>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept=".pdf,.docx,.doc,.txt,.md"
                style={{ display: 'none' }}
              />
              <button
                className="btn btn-secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={submittingFeedback}
                style={{ width: '100%', borderStyle: 'dashed', borderWidth: '1px', textAlign: 'center' }}
              >
                📁 Upload PDF / DOCX / TXT
              </button>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '6px' }}>
                Files are automatically uploaded to Google Drive & parsed by AI.
              </div>
            </div>
          </div>
        )}

        {/* Version History Sidebar Card */}
        <div className="card" style={{ padding: '24px' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '16px' }}>Version History</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {versions.map(v => (
              <div key={v.version} style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                background: v.status === 'active' ? 'rgba(79, 143, 255, 0.05)' : 'transparent',
                border: `1px solid ${v.status === 'active' ? 'rgba(79, 143, 255, 0.2)' : 'var(--border-subtle)'}`,
                borderRadius: 'var(--radius-md)',
                fontSize: '0.75rem',
              }}>
                <div>
                  <span style={{ fontWeight: 700 }}>v{v.version}</span>
                  <span style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>
                    {v.status === 'active' ? 'Active' : 'Archived'}
                  </span>
                </div>
                <div style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
                  {((v.understanding_score ?? v.ai_confidence)).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Impact Preview Modal */}
      {showImpactModal && impactPreview && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px',
        }}>
          <div className="card" style={{ maxWidth: '550px', width: '100%', padding: '24px', maxHeight: '90vh', overflowY: 'auto', background: '#161623', border: '1px solid var(--border-subtle)' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '8px', color: 'var(--accent-blue)' }}>
              🔮 Impact Before Regeneration
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Here is what our AI estimates will change based on your responses and uploaded feedback:
            </p>

            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '12px',
              marginBottom: '20px',
            }}>
              {[
                { label: 'Sections Modified', val: impactPreview.sections_modified, color: 'var(--accent-blue)' },
                { label: 'Features Added', val: impactPreview.features_added, color: 'var(--accent-green)' },
                { label: 'Requirements Removed', val: impactPreview.requirements_removed, color: '#ef4444' },
                { label: 'Ambiguities Resolved', val: impactPreview.ambiguities_resolved, color: 'var(--accent-purple)' },
              ].map(stat => (
                <div key={stat.label} style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px',
                  textAlign: 'center',
                }}>
                  <div style={{ fontSize: '1.5rem', fontWeight: 800, color: stat.color }}>{stat.val}</div>
                  <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '2px' }}>{stat.label}</div>
                </div>
              ))}
            </div>

            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '8px' }}>Expected Change Items:</h4>
              <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)' }}>
                {impactPreview.changes_summary?.map((item: string, idx: number) => (
                  <li key={idx} style={{ marginBottom: '6px', lineHeight: 1.4 }}>{item}</li>
                ))}
              </ul>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button className="btn btn-secondary" onClick={() => setShowImpactModal(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={confirmRegeneration}
                style={{
                  background: 'linear-gradient(135deg, var(--accent-blue), #9333ea)',
                  border: 'none',
                }}
              >
                Confirm & Generate PRD v{(status.current_version ?? 1) + 1}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
