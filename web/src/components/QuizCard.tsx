import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Check, X, ArrowRight, FileText, Flag, Edit3, Lightbulb, Save } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../api/client';
import type { QuestionResponse, PDF } from '../types';
import type { QuizState } from '../hooks/useQuiz';
import ReportForm from './ReportForm';
import DistractorForm from './DistractorForm';

interface QuizCardProps {
  question: QuestionResponse;
  state: QuizState;
  selectedAnswer: string | null;
  incorrectAnswers: Set<string>;
  onAnswerSelect: (answer: string) => void;
  onNextQuestion: () => void;
  onReportQuestion?: (data: {
    question: string;
    question_id: string;
    message: string;
    distractors: string;
  }) => Promise<void> | void;
  onSubmitDistractors?: (data: {
    question_id: string;
    distractors: string[];
  }) => Promise<void> | void;
  onAnswerEdited?: () => void;
  isAdmin?: boolean;
}

export default function QuizCard({
  question,
  state,
  selectedAnswer,
  incorrectAnswers,
  onAnswerSelect,
  onNextQuestion,
  onReportQuestion,
  onSubmitDistractors,
  onAnswerEdited,
  isAdmin,
}: QuizCardProps) {
  const [showReportForm, setShowReportForm] = useState(false);
  const [showDistractorForm, setShowDistractorForm] = useState(false);

  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (editingIdx !== null) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (state === 'correct' && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        onNextQuestion();
        return;
      }

      const num = parseInt(e.key, 10);
      if (!isNaN(num) && num >= 1 && num <= question.answers.length) {
        const answer = question.answers[num - 1];
        if (state !== 'correct' && !incorrectAnswers.has(answer)) {
          onAnswerSelect(answer);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [question.answers, state, incorrectAnswers, editingIdx, onAnswerSelect, onNextQuestion]);

  const getAnswerButtonClass = (answer: string, idx: number) => {
    if (editingIdx !== null && editingIdx !== idx) return 'answer-btn-disabled opacity-40';
    if (state === 'correct' && answer === selectedAnswer) return 'answer-btn-correct animate-pulse-green';
    if (incorrectAnswers.has(answer)) return 'answer-btn-incorrect';
    if (state === 'correct') return 'answer-btn-disabled';
    return 'answer-btn-default';
  };

  const getAnswerIcon = (answer: string) => {
    if (state === 'correct' && answer === selectedAnswer) return <Check className="h-5 w-5 text-emerald-600" />;
    if (incorrectAnswers.has(answer)) return <X className="h-5 w-5 text-red-500" />;
    return null;
  };

  const startEdit = (idx: number, currentText: string) => {
    setEditingIdx(idx);
    setEditText(currentText);
    setTimeout(() => editInputRef.current?.focus(), 0);
  };

  const cancelEdit = () => {
    setEditingIdx(null);
    setEditText('');
  };

  const saveEdit = async (idx: number) => {
    if (!editText.trim() || savingEdit) return;
    setSavingEdit(true);
    try {
      const answerType = question.answer_types?.[idx];
      const answerId = question.answer_ids?.[idx];
      const answerMeta = question.answer_metadata?.[idx];

      const payload =
        answerType === 'manual_distractor' && answerMeta != null
          ? { manual_distractor_id: answerMeta, new_text: editText.trim(), edit_type: 'manual_distractor' }
          : { question_id: answerId, new_text: editText.trim(), edit_type: answerType ?? 'question' };

      await api.editAnswer(payload);
      toast.success('Answer updated');
      setEditingIdx(null);
      setEditText('');
      onAnswerEdited?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update answer');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleReport = async (data: Parameters<NonNullable<typeof onReportQuestion>>[0]) => {
    if (onReportQuestion) await onReportQuestion(data);
    setShowReportForm(false);
  };

  const handleDistractors = async (data: Parameters<NonNullable<typeof onSubmitDistractors>>[0]) => {
    if (onSubmitDistractors) await onSubmitDistractors(data);
    setShowDistractorForm(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex flex-wrap gap-2 mb-4">
            {question.topic && (
              <span className="tag">{question.topic}</span>
            )}
            {question.subtopic && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700">
                {question.subtopic}
              </span>
            )}
          </div>
          <h2 className="text-2xl md:text-3xl font-bold text-gray-900 leading-snug">
            {question.question}
          </h2>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          {onReportQuestion && (
            <button
              onClick={() => { setShowReportForm((v) => !v); setShowDistractorForm(false); cancelEdit(); }}
              className={`p-2 rounded-lg transition-colors ${showReportForm ? 'text-amber-600 bg-amber-50' : 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'}`}
              title="Report question"
            >
              <Flag className="h-5 w-5" />
            </button>
          )}
          {onSubmitDistractors && state !== 'correct' && (
            <button
              onClick={() => { setShowDistractorForm((v) => !v); setShowReportForm(false); cancelEdit(); }}
              className={`p-2 rounded-lg transition-colors ${showDistractorForm ? 'text-amber-600 bg-amber-50' : 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'}`}
              title="Suggest distractors (Obvious Answer?)"
            >
              <Lightbulb className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>

      {showReportForm && onReportQuestion && (
        <ReportForm
          question={question}
          onSubmit={handleReport}
          onCancel={() => setShowReportForm(false)}
        />
      )}

      {showDistractorForm && onSubmitDistractors && (
        <DistractorForm
          question={question}
          onSubmit={handleDistractors}
          onCancel={() => setShowDistractorForm(false)}
        />
      )}

      <div className="space-y-3">
        {question.answers.map((answer, index) => (
          <div key={`${answer}-${index}`} className="flex items-center gap-2">
            {editingIdx === index ? (
              <div className="flex items-center gap-2 w-full">
                <input
                  ref={editInputRef}
                  type="text"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); void saveEdit(index); }
                    if (e.key === 'Escape') cancelEdit();
                  }}
                  className="flex-1 bg-white text-gray-900 rounded-xl px-4 py-3 border-2 border-blue-500 focus:outline-none text-base"
                />
                <button
                  onClick={() => void saveEdit(index)}
                  disabled={savingEdit || !editText.trim()}
                  className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-sm font-semibold flex items-center gap-1.5 transition-colors flex-shrink-0"
                  title="Save"
                >
                  {savingEdit ? (
                    <div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save
                </button>
                <button
                  onClick={cancelEdit}
                  className="px-3 py-2 rounded-lg bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm font-medium transition-colors flex-shrink-0"
                  title="Cancel"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <motion.button
                  onClick={() => {
                    if (editingIdx !== null) return;
                    onAnswerSelect(answer);
                  }}
                  disabled={state === 'correct' || incorrectAnswers.has(answer) || editingIdx !== null}
                  className={`${getAnswerButtonClass(answer, index)} flex-1`}
                  initial={false}
                  animate={
                    incorrectAnswers.has(answer) && answer === selectedAnswer
                      ? { x: [0, -10, 10, -10, 10, 0] }
                      : {}
                  }
                  transition={{ duration: 0.4 }}
                >
                  <div className="flex items-center justify-between">
                    <span className="flex items-center">
                      <span className="hidden sm:inline-flex items-center justify-center w-5 h-5 rounded bg-gray-200 text-xs font-mono font-bold text-gray-500 mr-2 flex-shrink-0">{index + 1}</span>
                      {answer}
                    </span>
                    {getAnswerIcon(answer)}
                  </div>
                </motion.button>

                {isAdmin && state !== 'correct' && (
                  <button
                    onClick={() => startEdit(index, answer)}
                    disabled={editingIdx !== null && editingIdx !== index}
                    className="p-2 rounded-lg bg-gray-100 hover:bg-amber-50 text-gray-400 hover:text-amber-600 transition-colors flex-shrink-0 disabled:opacity-30"
                    title="Edit this answer"
                  >
                    <Edit3 className="h-4 w-4" />
                  </button>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {question.pdfs && question.pdfs.length > 0 && (
        <PDFDropdown pdfs={question.pdfs} />
      )}

      {state === 'correct' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-center pt-4"
        >
          <button
            onClick={onNextQuestion}
            className="btn-primary flex items-center gap-2 text-lg px-8 py-3.5"
          >
            Next Question
            <ArrowRight className="h-5 w-5" />
          </button>
        </motion.div>
      )}
    </div>
  );
}

function PDFDropdown({ pdfs }: { pdfs: PDF[] }) {
  const handlePDFClick = async (e: React.MouseEvent<HTMLAnchorElement>, pdf: PDF) => {
    e.preventDefault();
    const url = `/api/pdf/${pdf.id}`;
    try {
      const res = await fetch(url, { credentials: 'include' });
      if (res.status === 403) {
        const data = await res.json().catch(() => ({}));
        toast.error(data.message || 'You do not have permission to view PDFs.', {
          action: {
            label: 'Request access',
            onClick: () => { void requestPDFAccess(); },
          },
          duration: 8000,
        });
        return;
      }
      if (!res.ok) { toast.error('Failed to load PDF'); return; }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, '_blank');
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load PDF');
    }
  };

  return (
    <div className="border-t border-gray-100 pt-5">
      <h3 className="text-sm font-semibold text-gray-500 mb-3 flex items-center gap-2">
        <FileText className="h-4 w-4" />
        Related Lecture Notes
      </h3>
      <div className="space-y-2">
        {pdfs.map((pdf) => (
          <a
            key={pdf.id}
            href={`/api/pdf/${pdf.id}`}
            onClick={(e) => handlePDFClick(e, pdf)}
            className="flex items-center justify-between p-3 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-red-500" />
              <span className="text-gray-700 font-medium">{pdf.original_filename}</span>
            </div>
            {pdf.match_percent && (
              <span className="text-xs text-gray-400 font-medium">
                {Math.round(pdf.match_percent)}% match
              </span>
            )}
          </a>
        ))}
      </div>
    </div>
  );
}

async function requestPDFAccess() {
  try {
    const res = await fetch('/api/request-pdf-access', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'Requesting access from quiz' }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      toast.error(data.error || 'Failed to request access');
      return;
    }
    toast.success('Access request submitted! An admin will review it.');
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Failed to request access');
  }
}
