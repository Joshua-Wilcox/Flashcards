import { useState } from 'react';
import { Flag, Send } from 'lucide-react';
import type { QuestionResponse } from '../types';

interface ReportFormProps {
  question: QuestionResponse;
  onSubmit: (data: {
    question: string;
    question_id: string;
    message: string;
    distractors: string;
  }) => Promise<void> | void;
  onCancel: () => void;
}

const MIN_MESSAGE_LENGTH = 10;

export default function ReportForm({ question, onSubmit, onCancel }: ReportFormProps) {
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const trimmedMessage = message.trim();
  const isTooShort = trimmedMessage.length > 0 && trimmedMessage.length < MIN_MESSAGE_LENGTH;
  const showError = touched && isTooShort;

  const distractorObjects = question.answers
    .map((answer, i) => ({
      answer,
      id: question.answer_ids?.[i] ?? '',
      type: question.answer_types?.[i] ?? 'unknown',
      metadata: question.answer_metadata?.[i] ?? null,
    }))
    .filter((d) => !(d.type === 'question' && d.id === question.question_id));

  const correctAnswer = question.answers.find(
    (_, i) =>
      question.answer_types?.[i] === 'question' &&
      question.answer_ids?.[i] === question.question_id
  ) ?? '';

  const handleSubmit = async () => {
    setTouched(true);
    if (trimmedMessage.length < MIN_MESSAGE_LENGTH) return;
    setSubmitting(true);
    try {
      await onSubmit({
        question: question.question,
        question_id: question.question_id,
        message: message.trim(),
        distractors: JSON.stringify(
          distractorObjects.map((d) => ({
            question: question.question,
            answer: d.answer,
            type: d.type,
          }))
        ),
      });
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = trimmedMessage.length >= MIN_MESSAGE_LENGTH && !submitting;

  const SubmitButtons = () => (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="btn-primary text-sm flex items-center gap-1.5"
      >
        <Send className="h-3.5 w-3.5" />
        Submit Report
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="btn-secondary text-sm"
      >
        Cancel
      </button>
    </div>
  );

  return (
    <div className="rounded-xl bg-amber-50 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Flag className="h-5 w-5 text-amber-600" />
        <h3 className="text-base font-bold text-amber-700">Report a Question</h3>
        <span className="text-sm text-gray-500">Please provide details about the issue.</span>
      </div>

      <SubmitButtons />

      <div className="rounded-lg bg-blue-50 p-3 text-sm text-gray-600 space-y-1">
        <p className="font-semibold text-blue-700 mb-2">Reporting Guidelines</p>
        <ul className="space-y-1 list-disc list-inside text-gray-500">
          <li>What is incorrect about the question or answer</li>
          <li>If distractors are problematic, mention them by number</li>
          <li>Provide any corrections or suggestions</li>
        </ul>
      </div>

      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1">
          Describe the issue:
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onBlur={() => setTouched(true)}
          rows={6}
          placeholder="Please describe what's wrong with this question, answer, or distractors."
          className={`input text-sm leading-relaxed ${showError ? 'border-red-400' : ''}`}
        />
        {showError && (
          <p className="mt-1 text-xs text-red-600">
            Message must be at least {MIN_MESSAGE_LENGTH} characters (currently {trimmedMessage.length}).
          </p>
        )}
      </div>

      <div className="rounded-xl bg-white p-4 space-y-3">
        <p className="text-sm font-semibold text-gray-700">Correct Answer</p>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Question</p>
          <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700">
            {question.question}
          </div>
        </div>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Answer</p>
          <div className="bg-emerald-50 rounded-lg p-3 text-sm text-emerald-700">
            {correctAnswer}
          </div>
        </div>
      </div>

      {distractorObjects.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-gray-700">Distractors</p>
          {distractorObjects.map((d, i) => (
            <div
              key={`${d.id}-${i}`}
              className="rounded-lg bg-white p-3 space-y-2"
            >
              <p className="text-xs text-gray-400 uppercase tracking-wide">Distractor {i + 1}</p>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Question</p>
                <div className="bg-gray-50 rounded p-2 text-xs text-gray-600">
                  {question.question}
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Answer</p>
                <div className="bg-red-50 rounded p-2 text-xs text-red-700">
                  {d.answer}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <SubmitButtons />
    </div>
  );
}
