import { useState } from 'react';
import { Lightbulb, Send } from 'lucide-react';
import { toast } from 'sonner';
import AIPromptHelper from './AIPromptHelper';
import type { QuestionResponse } from '../types';

interface DistractorFormProps {
  question: QuestionResponse;
  onSubmit: (data: { question_id: string; distractors: string[] }) => Promise<void> | void;
  onCancel: () => void;
}

export default function DistractorForm({ question, onSubmit, onCancel }: DistractorFormProps) {
  const [distractors, setDistractors] = useState(['', '', '', '']);
  const [submitting, setSubmitting] = useState(false);

  // Find the correct answer text
  const correctAnswer = question.answers.find(
    (_, i) =>
      question.answer_types?.[i] === 'question' &&
      question.answer_ids?.[i] === question.question_id
  ) ?? question.answers[0] ?? '';

  const update = (i: number, value: string) => {
    setDistractors((prev) => prev.map((d, idx) => (idx === i ? value : d)));
  };

  const handleSubmit = async () => {
    const filtered = distractors.map((d) => d.trim()).filter((d) => d.length > 0);
    if (filtered.length === 0) {
      toast.error('Please enter at least one distractor');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({ question_id: question.question_id, distractors: filtered });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-amber-700/40 bg-amber-950/10 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Lightbulb className="h-5 w-5 text-amber-400" />
        <h3 className="text-base font-semibold text-amber-400">Suggest Distractors</h3>
        <span className="text-sm text-slate-400">Help improve this question with better wrong answers.</span>
      </div>

      {/* Question + Correct Answer display */}
      <div className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-4 space-y-3">
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Question</p>
          <div className="bg-slate-800/60 rounded-lg p-3 text-sm text-slate-200">
            {question.question}
          </div>
        </div>
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Correct Answer</p>
          <div className="bg-blue-950/30 border border-blue-800/30 rounded-lg p-3 text-sm text-blue-300">
            {correctAnswer}
          </div>
        </div>
      </div>

      {/* AI prompt helper */}
      <AIPromptHelper question={question.question} answer={correctAnswer} />

      {/* Guidance */}
      <p className="text-xs text-slate-400">
        You can submit 1–4 distractors. Good distractors are wrong but believable answers that test understanding.
      </p>

      {/* Distractor inputs */}
      <div className="space-y-2">
        {distractors.map((d, i) => (
          <div key={i}>
            <label className="block text-xs text-slate-500 mb-1">Distractor {i + 1}:</label>
            <textarea
              value={d}
              onChange={(e) => update(i, e.target.value)}
              rows={2}
              placeholder="Enter a plausible wrong answer..."
              className="w-full bg-slate-900 text-white rounded-lg px-3 py-2 border border-slate-700 focus:border-amber-500 focus:outline-none resize-y text-sm"
            />
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting}
          className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm font-medium flex items-center gap-1.5 transition-colors"
        >
          <Send className="h-3.5 w-3.5" />
          Submit Distractors for Review
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
