import React, { useState } from 'react';
import { submitSectionResponses } from '../reviewApi';

interface Question {
  id: string;
  text: string;
  type: 'yes_no' | 'multiple_choice' | 'short_text';
  options: string[] | null;
  context?: string;
}

interface QuestionnaireSectionProps {
  projectId: string;
  token?: string;
  sectionName: string;
  questions: Question[];
  onComplete: (score: number) => void;
  onClose: () => void;
}

export function QuestionnaireSection({
  projectId,
  token,
  sectionName,
  questions,
  onComplete,
  onClose,
}: QuestionnaireSectionProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, { answer: any; confidence: number }>>({});
  const [submitting, setSubmitting] = useState(false);

  const currentQuestion = questions[currentIndex];

  if (!questions || questions.length === 0) {
    return (
      <div className="card" style={{ padding: '24px', textAlign: 'center' }}>
        <p>No questions generated for this section.</p>
        <button className="btn btn-secondary" onClick={onClose}>Close</button>
      </div>
    );
  }

  const handleAnswerChange = (val: any) => {
    setAnswers(prev => ({
      ...prev,
      [currentQuestion.id]: {
        answer: val,
        confidence: prev[currentQuestion.id]?.confidence || 3, // Default average confidence (1-5 scale)
      },
    }));
  };

  const handleConfidenceChange = (val: number) => {
    if (!answers[currentQuestion.id]) return;
    setAnswers(prev => ({
      ...prev,
      [currentQuestion.id]: {
        ...prev[currentQuestion.id],
        confidence: val,
      },
    }));
  };

  const handleNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  const currentAnswer = answers[currentQuestion.id]?.answer ?? '';
  const currentConfidence = answers[currentQuestion.id]?.confidence ?? 3;
  const isAnswered = currentAnswer !== '';

  const handleSubmit = async () => {
    setSubmitting(true);
    const payload = Object.entries(answers).map(([id, data]) => ({
      id,
      answer: data.answer,
      confidence: data.confidence,
    }));

    const success = await submitSectionResponses(projectId, sectionName, payload, token);
    setSubmitting(false);

    if (success) {
      // Complete section
      onComplete(90); // Dummy fallback value, the parent component will re-fetch actual score from backend
    } else {
      alert('Failed to submit responses. Please try again.');
    }
  };

  const progressPercent = Math.round(((currentIndex + 1) / questions.length) * 100);

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      padding: '24px',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>
            Validating Section
          </span>
          <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: '2px 0 0 0' }}>{sectionName}</h3>
        </div>
        <button className="btn btn-secondary" onClick={onClose} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
          ✕ Close
        </button>
      </div>

      {/* Progress Bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
        <div style={{
          flex: 1,
          height: '6px',
          background: 'rgba(255,255,255,0.05)',
          borderRadius: 'var(--radius-full)',
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${progressPercent}%`,
            height: '100%',
            background: 'linear-gradient(90deg, var(--accent-blue), #9333ea)',
            transition: 'width 0.3s ease',
          }} />
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, minWidth: '40px', textAlign: 'right' }}>
          {currentIndex + 1} of {questions.length}
        </span>
      </div>

      {/* Question Card */}
      <div style={{
        background: 'var(--bg-glass)',
        border: '1px solid rgba(255,255,255,0.03)',
        borderRadius: 'var(--radius-md)',
        padding: '20px',
        marginBottom: '20px',
      }}>
        {currentQuestion.context && (
          <div style={{
            fontSize: '0.75rem',
            color: 'var(--text-muted)',
            background: 'rgba(255,255,255,0.02)',
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '12px',
            borderLeft: '3px solid var(--accent-blue)',
          }}>
            ℹ️ {currentQuestion.context}
          </div>
        )}

        <h4 style={{ fontSize: '1rem', fontWeight: 600, lineHeight: 1.5, marginBottom: '20px' }}>
          {currentQuestion.text}
        </h4>

        {/* Input elements based on type */}
        {currentQuestion.type === 'yes_no' && (
          <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
            {['Yes', 'No'].map(option => (
              <button
                key={option}
                onClick={() => handleAnswerChange(option)}
                style={{
                  flex: 1,
                  padding: '12px',
                  background: currentAnswer === option ? 'rgba(79, 143, 255, 0.15)' : 'rgba(255,255,255,0.02)',
                  border: currentAnswer === option ? '1px solid var(--accent-blue)' : '1px solid var(--border-subtle)',
                  color: currentAnswer === option ? 'var(--accent-blue)' : 'var(--text-main)',
                  borderRadius: 'var(--radius-md)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                {option === 'Yes' ? '👍 Yes, correct' : '👎 No, incorrect'}
              </button>
            ))}
          </div>
        )}

        {currentQuestion.type === 'multiple_choice' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px' }}>
            {currentQuestion.options?.map(option => (
              <button
                key={option}
                onClick={() => handleAnswerChange(option)}
                style={{
                  textAlign: 'left',
                  padding: '12px 16px',
                  background: currentAnswer === option ? 'rgba(79, 143, 255, 0.15)' : 'rgba(255,255,255,0.02)',
                  border: currentAnswer === option ? '1px solid var(--accent-blue)' : '1px solid var(--border-subtle)',
                  color: currentAnswer === option ? 'var(--accent-blue)' : 'var(--text-main)',
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
                  border: currentAnswer === option ? '5px solid var(--accent-blue)' : '2px solid var(--text-muted)',
                  marginRight: '12px',
                  verticalAlign: 'middle',
                }} />
                {option}
              </button>
            ))}
          </div>
        )}

        {currentQuestion.type === 'short_text' && (
          <div style={{ marginBottom: '20px' }}>
            <textarea
              value={currentAnswer}
              onChange={(e) => handleAnswerChange(e.target.value)}
              placeholder="Type your explanation or changes needed..."
              rows={4}
              style={{
                width: '100%',
                padding: '12px 16px',
                background: 'rgba(0,0,0,0.2)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-main)',
                fontSize: '0.85rem',
                lineHeight: 1.4,
                resize: 'vertical',
                outline: 'none',
              }}
            />
          </div>
        )}

        {/* Confidence rating slider (only if answered) */}
        {isAnswered && (
          <div style={{
            marginTop: '16px',
            paddingTop: '16px',
            borderTop: '1px solid rgba(255,255,255,0.03)',
          }}>
            <label style={{
              display: 'block',
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              marginBottom: '8px',
              fontWeight: 600,
            }}>
              How important is this requirement to you?
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <input
                type="range"
                min="1"
                max="5"
                value={currentConfidence}
                onChange={(e) => handleConfidenceChange(Number(e.target.value))}
                style={{ flex: 1, accentColor: 'var(--accent-blue)' }}
              />
              <span style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--accent-blue)',
                background: 'rgba(79, 143, 255, 0.1)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
                minWidth: '70px',
                textAlign: 'center',
              }}>
                {currentConfidence === 1 && 'Low Priority'}
                {currentConfidence === 2 && 'Optional'}
                {currentConfidence === 3 && 'Medium'}
                {currentConfidence === 4 && 'High Priority'}
                {currentConfidence === 5 && 'Critical (P0)'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Navigation Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button
          className="btn btn-secondary"
          onClick={handlePrev}
          disabled={currentIndex === 0}
        >
          ← Previous
        </button>

        {currentIndex === questions.length - 1 ? (
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!isAnswered || submitting}
            style={{
              background: 'linear-gradient(135deg, #10b981, #059669)',
              border: 'none',
              boxShadow: '0 4px 12px rgba(16, 185, 129, 0.2)',
            }}
          >
            {submitting ? 'Submitting...' : '✓ Complete Section'}
          </button>
        ) : (
          <button
            className="btn btn-primary"
            onClick={handleNext}
            disabled={!isAnswered}
          >
            Next Question →
          </button>
        )}
      </div>
    </div>
  );
}
