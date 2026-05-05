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

export default function ReportForm({ question, onSubmit, onCancel }: ReportFormProps) {
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Build rich distractor objects matching the original schema
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
    if (!message.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit({
        question: question.question,
        question_id: question.question_id,
        message,
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

  const canSubmit = message.trim().length > 0 && !submitting;

  const SubmitButtons = () => (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-medium flex items-center gap-1.5 transition-colors"
      >
        <Send className="h-3.5 w-3.5" />
        Submit Report
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm transition-colors"
      >
        Cancel
      </button>
    </div>
  );

  return (
    <div className="rounded-xl border border-yellow-700/40 bg-yellow-950/10 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Flag className="h-5 w-5 text-yellow-400" />
        <h3 className="text-base font-semibold text-yellow-400">Report a Question</h3>
        <span className="text-sm text-slate-400">Please provide details about the issue.</span>
      </div>

      {/* Top submit buttons */}
      <SubmitButtons />

      {/* Reporting guidelines */}
      <div className="rounded-lg bg-blue-950/30 border border-blue-800/40 p-3 text-sm text-slate-300 space-y-1">
        <p className="font-semibold text-blue-300 mb-2">Reporting Guidelines</p>
        <ul className="space-y-1 list-disc list-inside text-slate-400">
          <li>What is incorrect about the question or answer</li>
          <li>If distractors are problematic, mention them by number</li>
          <li>Provide any corrections or suggestions</li>
        </ul>
      </div>

      {/* Message textarea */}
      <div>
        <label className="block text-sm font-semibold text-blue-300 mb-1">
          Describe the issue:
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={6}
          placeholder="Please describe what's wrong with this question, answer, or distractors."
          className="w-full bg-slate-900 text-white rounded-lg px-3 py-2 border border-blue-700/50 focus:border-blue-500 focus:outline-none resize-y text-sm leading-relaxed"
        />
      </div>

      {/* Question + Correct Answer */}
      <div className="rounded-lg bg-blue-950/20 border border-blue-800/30 p-4 space-y-3">
        <p className="text-sm font-semibold text-blue-300">Correct Answer</p>
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Question</p>
          <div className="bg-slate-800/60 rounded-lg p-3 text-sm text-slate-200">
            {question.question}
          </div>
        </div>
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Answer</p>
          <div className="bg-green-950/40 border border-green-800/30 rounded-lg p-3 text-sm text-green-300">
            {correctAnswer}
          </div>
        </div>
      </div>

      {/* Distractors */}
      {distractorObjects.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-slate-300">Distractors</p>
          {distractorObjects.map((d, i) => (
            <div
              key={`${d.id}-${i}`}
              className="rounded-lg bg-slate-800/40 border border-slate-700/50 p-3 space-y-2"
            >
              <p className="text-xs text-slate-500 uppercase tracking-wide">Distractor {i + 1}</p>
              <div>
                <p className="text-xs text-slate-600 mb-0.5">Question</p>
                <div className="bg-slate-800/60 rounded p-2 text-xs text-slate-300">
                  {question.question}
                </div>
              </div>
              <div>
                <p className="text-xs text-slate-600 mb-0.5">Answer</p>
                <div className="bg-red-950/30 border border-red-900/30 rounded p-2 text-xs text-red-300">
                  {d.answer}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bottom submit buttons */}
      <SubmitButtons />
    </div>
  );
}
