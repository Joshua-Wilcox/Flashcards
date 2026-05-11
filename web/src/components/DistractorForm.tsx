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
    <div className="rounded-xl bg-amber-50 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Lightbulb className="h-5 w-5 text-amber-600" />
        <h3 className="text-base font-bold text-amber-700">Suggest Distractors</h3>
        <span className="text-sm text-gray-500">Help improve this question with better wrong answers.</span>
      </div>

      <div className="rounded-xl bg-white p-4 space-y-3">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Question</p>
          <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700">
            {question.question}
          </div>
        </div>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Correct Answer</p>
          <div className="bg-blue-50 rounded-lg p-3 text-sm text-blue-700">
            {correctAnswer}
          </div>
        </div>
      </div>

      <AIPromptHelper question={question.question} answer={correctAnswer} />

      <p className="text-xs text-gray-500">
        You can submit 1-4 distractors. Good distractors are wrong but believable answers that test understanding.
      </p>

      <div className="space-y-2">
        {distractors.map((d, i) => (
          <div key={i}>
            <label className="block text-xs text-gray-500 mb-1">Distractor {i + 1}:</label>
            <textarea
              value={d}
              onChange={(e) => update(i, e.target.value)}
              rows={2}
              placeholder="Enter a plausible wrong answer..."
              className="input text-sm"
            />
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting}
          className="btn-primary text-sm flex items-center gap-1.5"
        >
          <Send className="h-3.5 w-3.5" />
          Submit Distractors for Review
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-secondary text-sm"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
