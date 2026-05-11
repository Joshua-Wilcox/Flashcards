import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Settings,
  FileText,
  MessageSquare,
  Flag,
  FileKey,
  Check,
  X,
  Trash2,
  AlertTriangle,
  Eye,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  SubmittedFlashcard,
  SubmittedDistractor,
  ReportedQuestion,
  PDFAccessRequest,
} from '../types';
import type { SubmittedPDF } from '../api/client';

type Tab = 'flashcards' | 'distractors' | 'reports' | 'pdf_requests' | 'pdf_submissions';

export default function Admin() {
  const [activeTab, setActiveTab] = useState<Tab>('flashcards');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'submissions'],
    queryFn: api.getAdminSubmissions,
  });

  const { data: submittedPDFsData } = useQuery({
    queryKey: ['admin', 'submitted-pdfs'],
    queryFn: api.listSubmittedPDFs,
  });

  const tabs = [
    {
      id: 'flashcards' as Tab,
      label: 'Flashcards',
      icon: FileText,
      count: data?.flashcards?.length || 0,
    },
    {
      id: 'distractors' as Tab,
      label: 'Distractors',
      icon: MessageSquare,
      count: data?.distractors?.length || 0,
    },
    {
      id: 'reports' as Tab,
      label: 'Reports',
      icon: Flag,
      count: data?.reports?.length || 0,
    },
    {
      id: 'pdf_requests' as Tab,
      label: 'PDF Access',
      icon: FileKey,
      count: data?.pdf_requests?.length || 0,
    },
    {
      id: 'pdf_submissions' as Tab,
      label: 'PDF Submissions',
      icon: FileText,
      count: submittedPDFsData?.pdfs?.length || 0,
    },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Settings className="h-7 w-7 text-purple-600" />
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
              activeTab === tab.id
                ? 'bg-blue-600 text-gray-900'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <tab.icon className="h-4 w-4" />
            <span>{tab.label}</span>
            {tab.count > 0 && (
              <span
                className={`px-2 py-0.5 text-xs rounded-full ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-gray-900'
                    : 'bg-gray-200 text-gray-700'
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="card p-8 flex justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
        </div>
      ) : (
        <>
          {activeTab === 'flashcards' && (
            <FlashcardsList
              flashcards={data?.flashcards || []}
              queryClient={queryClient}
            />
          )}
          {activeTab === 'distractors' && (
            <DistractorsList
              distractors={data?.distractors || []}
              queryClient={queryClient}
            />
          )}
          {activeTab === 'reports' && (
            <ReportsList
              reports={data?.reports || []}
              queryClient={queryClient}
            />
          )}
          {activeTab === 'pdf_requests' && (
            <PDFRequestsList
              requests={data?.pdf_requests || []}
              queryClient={queryClient}
            />
          )}
          {activeTab === 'pdf_submissions' && (
            <PDFSubmissionsList
              pdfs={submittedPDFsData?.pdfs || []}
              queryClient={queryClient}
            />
          )}
        </>
      )}
    </div>
  );
}

function EditableFlashcardCard({
  fc,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: {
  fc: SubmittedFlashcard;
  onApprove: (data: {
    submission_id: number;
    question: string;
    answer: string;
    module: string;
    topic?: string;
    subtopic?: string;
    tags?: string[];
  }) => void;
  onReject: (id: number) => void;
  isApproving: boolean;
  isRejecting: boolean;
}) {
  const [question, setQuestion] = useState(fc.submitted_question);
  const [answer, setAnswer] = useState(fc.submitted_answer);
  const [topic, setTopic] = useState(fc.submitted_topic || '');
  const [subtopic, setSubtopic] = useState(fc.submitted_subtopic || '');
  const [tags, setTags] = useState(fc.submitted_tags_comma_separated || '');

  const edited =
    question !== fc.submitted_question ||
    answer !== fc.submitted_answer ||
    topic !== (fc.submitted_topic || '') ||
    subtopic !== (fc.submitted_subtopic || '') ||
    tags !== (fc.submitted_tags_comma_separated || '');

  const inputClass =
    'w-full bg-white text-gray-900 rounded px-3 py-1.5 border border-gray-200 focus:border-blue-500 focus:outline-none transition-colors';

  return (
    <div className="card p-4">
      <p className="text-sm text-gray-500 mb-3">
        {fc.username} • {fc.module}
      </p>

      <label className="block mb-3">
        <span className="text-xs text-gray-400 uppercase tracking-wide">Question</span>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          className={`${inputClass} mt-1 resize-y`}
        />
      </label>

      <label className="block mb-3">
        <span className="text-xs text-gray-400 uppercase tracking-wide">Answer</span>
        <input
          type="text"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          className={`${inputClass} mt-1`}
        />
      </label>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <label className="block">
          <span className="text-xs text-gray-400 uppercase tracking-wide">Topic</span>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className={`${inputClass} mt-1`}
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-400 uppercase tracking-wide">Subtopic</span>
          <input
            type="text"
            value={subtopic}
            onChange={(e) => setSubtopic(e.target.value)}
            className={`${inputClass} mt-1`}
          />
        </label>
      </div>

      <label className="block mb-3">
        <span className="text-xs text-gray-400 uppercase tracking-wide">Tags (comma-separated)</span>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          className={`${inputClass} mt-1`}
          placeholder="tag1, tag2, tag3"
        />
      </label>

      <div className="flex items-center gap-2">
        <button
          onClick={() =>
            onApprove({
              submission_id: fc.id,
              question,
              answer,
              module: fc.module,
              topic: topic || undefined,
              subtopic: subtopic || undefined,
              tags: tags
                ? tags.split(',').map((t) => t.trim()).filter(Boolean)
                : undefined,
            })
          }
          disabled={isApproving}
          className="btn-success flex items-center gap-2"
        >
          <Check className="h-4 w-4" />
          {edited ? 'Approve (edited)' : 'Approve'}
        </button>
        <button
          onClick={() => onReject(fc.id)}
          disabled={isRejecting}
          className="btn-danger flex items-center gap-2"
        >
          <X className="h-4 w-4" />
          Reject
        </button>
        {edited && (
          <span className="text-xs text-amber-600 ml-2">Modified</span>
        )}
      </div>
    </div>
  );
}

function FlashcardsList({
  flashcards,
  queryClient,
}: {
  flashcards: SubmittedFlashcard[];
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  const approveMutation = useMutation({
    mutationFn: (data: {
      submission_id: number;
      question: string;
      answer: string;
      module: string;
      topic?: string;
      subtopic?: string;
      tags?: string[];
    }) => api.approveFlashcard(data),
    onSuccess: () => {
      toast.success('Flashcard approved');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to approve');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => api.rejectFlashcard(id),
    onSuccess: () => {
      toast.success('Flashcard rejected');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to reject');
    },
  });

  if (flashcards.length === 0) {
    return (
      <div className="card p-8 text-center text-gray-500">
        No pending flashcards
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {flashcards.map((fc) => (
        <EditableFlashcardCard
          key={fc.id}
          fc={fc}
          onApprove={(data) => approveMutation.mutate(data)}
          onReject={(id) => rejectMutation.mutate(id)}
          isApproving={approveMutation.isPending}
          isRejecting={rejectMutation.isPending}
        />
      ))}
    </div>
  );
}

function DistractorRow({
  d,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: {
  d: SubmittedDistractor;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  isApproving: boolean;
  isRejecting: boolean;
}) {
  const [text, setText] = useState(d.distractor_text);

  return (
    <div className="flex items-center gap-3 py-2.5 border-t border-gray-200/50">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-400 mb-1">{d.username ?? 'Unknown'}</p>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full bg-white text-gray-900 rounded px-3 py-1.5 border border-gray-200 focus:border-blue-500 focus:outline-none transition-colors text-sm"
        />
      </div>
      <div className="flex gap-2 flex-shrink-0">
        <button
          onClick={() => onApprove(d.id)}
          disabled={isApproving}
          className="btn-success flex items-center gap-1.5 text-sm"
        >
          <Check className="h-3.5 w-3.5" />
          Approve
        </button>
        <button
          onClick={() => onReject(d.id)}
          disabled={isRejecting}
          className="btn-danger flex items-center gap-1.5 text-sm"
        >
          <X className="h-3.5 w-3.5" />
          Reject
        </button>
      </div>
    </div>
  );
}

function DistractorsList({
  distractors,
  queryClient,
}: {
  distractors: SubmittedDistractor[];
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  const approveMutation = useMutation({
    mutationFn: (id: number) => api.approveDistractor(id),
    onSuccess: () => {
      toast.success('Distractor approved');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to approve');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => api.rejectDistractor(id),
    onSuccess: () => {
      toast.success('Distractor rejected');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to reject');
    },
  });

  if (distractors.length === 0) {
    return (
      <div className="card p-8 text-center text-gray-500">
        No pending distractors
      </div>
    );
  }

  // Group by question_text (or question_id as fallback)
  const groups = new Map<string, { label: string; source: string; items: SubmittedDistractor[] }>();
  for (const d of distractors) {
    const key = d.question_text ?? d.question_id;
    if (!groups.has(key)) {
      groups.set(key, { label: d.question_text ?? d.question_id, source: d.question_source ?? 'live', items: [] });
    }
    groups.get(key)!.items.push(d);
  }

  return (
    <div className="space-y-4">
      {Array.from(groups.entries()).map(([key, group]) => (
        <div key={key} className="card p-4">
          <div className="flex items-start gap-2 mb-1">
            <p className="text-sm font-medium text-gray-800 flex-1">{group.label}</p>
            {group.source === 'pending' && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 flex-shrink-0">
                pending review
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mb-2">
            {group.items.length} pending distractor{group.items.length !== 1 ? 's' : ''}
          </p>
          {group.items.map((d) => (
            <DistractorRow
              key={d.id}
              d={d}
              onApprove={(id) => approveMutation.mutate(id)}
              onReject={(id) => rejectMutation.mutate(id)}
              isApproving={approveMutation.isPending}
              isRejecting={rejectMutation.isPending}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function ReportCard({
  r,
  queryClient,
}: {
  r: ReportedQuestion;
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  // Live question data from DB
  const [liveQuestion, setLiveQuestion] = useState<{ id: string; question: string; answer: string } | null>(null);
  const [liveDistractors, setLiveDistractors] = useState<{ id: number; distractor_text: string }[]>([]);
  const [loadingLive, setLoadingLive] = useState(false);

  // Edit state
  const [editedQuestion, setEditedQuestion] = useState('');
  const [editedAnswer, setEditedAnswer] = useState('');
  const [deleteQuestion, setDeleteQuestion] = useState(false);
  const [distractorEdits, setDistractorEdits] = useState<
    { id: number; text: string; delete: boolean }[]
  >([]);

  const resolveMutation = useMutation({
    mutationFn: (data: Parameters<typeof api.resolveReport>[0]) => api.resolveReport(data),
    onSuccess: () => {
      toast.success('Report resolved');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Failed to resolve'),
  });

  const discardMutation = useMutation({
    mutationFn: () => api.discardReport(r.id),
    onSuccess: () => {
      toast.success('Report discarded');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Failed to discard'),
  });

  // Fetch live question on mount if we have a question_id
  useEffect(() => {
    if (!r.question_id) return;
    setLoadingLive(true);
    api.getQuestionForReport(r.question_id)
      .then((data) => {
        setLiveQuestion(data.question);
        setEditedQuestion(data.question.question);
        setEditedAnswer(data.question.answer);
        setLiveDistractors(data.distractors);
        setDistractorEdits(data.distractors.map((d) => ({ id: d.id, text: d.distractor_text, delete: false })));
      })
      .catch(() => { /* question may have been deleted */ })
      .finally(() => setLoadingLive(false));
  }, [r.question_id]);

  const handleSaveChanges = () => {
    resolveMutation.mutate({
      report_id: r.id,
      question_id: liveQuestion?.id,
      new_question_text: editedQuestion !== liveQuestion?.question ? editedQuestion : undefined,
      new_question_answer: editedAnswer !== liveQuestion?.answer ? editedAnswer : undefined,
      delete_question: deleteQuestion,
      distractors: distractorEdits.map((d) => ({
        id: d.id,
        type: 'manual_distractor',
        new_text: d.text !== liveDistractors.find((ld) => ld.id === d.id)?.distractor_text ? d.text : undefined,
        delete: d.delete,
      })),
    });
  };

  const inputClass = 'w-full bg-white text-gray-900 rounded px-3 py-1.5 border border-gray-200 focus:border-blue-500 focus:outline-none transition-colors text-sm mt-1 resize-y';

  return (
    <div className="card p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <p className="text-sm font-medium text-gray-700">{r.username}</p>
        {r.question_id && (
          <code className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded font-mono">
            {r.question_id.substring(0, 8)}
          </code>
        )}
      </div>

      {/* Reporter's message */}
      {r.message && (
        <div className="bg-amber-50 rounded-lg px-3 py-2">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Complaint</p>
          <p className="text-sm text-amber-700">&ldquo;{r.message}&rdquo;</p>
        </div>
      )}

      {/* Live question editing */}
      {loadingLive && (
        <p className="text-xs text-gray-400 animate-pulse">Loading live question data...</p>
      )}

      {liveQuestion && !loadingLive && (
        <div className="space-y-3">
          <div className="border border-gray-200 rounded-lg p-3 space-y-3">
            <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">Correct Answer</p>

            <label className="block">
              <span className="text-xs text-gray-400 uppercase tracking-wide">Question</span>
              <textarea
                value={editedQuestion}
                onChange={(e) => setEditedQuestion(e.target.value)}
                rows={2}
                disabled={deleteQuestion}
                className={`${inputClass} disabled:opacity-40`}
              />
            </label>

            <label className="block">
              <span className="text-xs text-gray-400 uppercase tracking-wide">Answer</span>
              <input
                type="text"
                value={editedAnswer}
                onChange={(e) => setEditedAnswer(e.target.value)}
                disabled={deleteQuestion}
                className={`${inputClass} disabled:opacity-40`}
              />
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={deleteQuestion}
                onChange={(e) => setDeleteQuestion(e.target.checked)}
                className="rounded border-gray-200"
              />
              <span className="text-sm text-red-600">Delete this question from the database</span>
            </label>
          </div>

          {/* Manual distractors */}
          {distractorEdits.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Manual Distractors
              </p>
              {distractorEdits.map((d, i) => (
                <div key={d.id} className="border border-gray-200/50 rounded-lg p-3 space-y-2">
                  <p className="text-xs text-gray-400">Distractor {i + 1}</p>
                  <input
                    type="text"
                    value={d.text}
                    onChange={(e) =>
                      setDistractorEdits((prev) =>
                        prev.map((item) => item.id === d.id ? { ...item, text: e.target.value } : item)
                      )
                    }
                    disabled={d.delete}
                    className={`${inputClass} disabled:opacity-40`}
                  />
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={d.delete}
                      onChange={(e) =>
                        setDistractorEdits((prev) =>
                          prev.map((item) => item.id === d.id ? { ...item, delete: e.target.checked } : item)
                        )
                      }
                      className="rounded border-gray-200"
                    />
                    <span className="text-xs text-red-600">Delete this distractor</span>
                  </label>
                </div>
              ))}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSaveChanges}
              disabled={resolveMutation.isPending || discardMutation.isPending}
              className="btn-success flex items-center gap-2 flex-1"
            >
              <Check className="h-4 w-4" />
              Save Changes &amp; Resolve
            </button>
            <button
              onClick={() => discardMutation.mutate()}
              disabled={resolveMutation.isPending || discardMutation.isPending}
              className="btn-danger flex items-center gap-2"
            >
              <Trash2 className="h-4 w-4" />
              Discard
            </button>
          </div>
        </div>
      )}

      {/* No question_id — just show reported text and discard */}
      {!r.question_id && !loadingLive && (
        <div className="space-y-3">
          <div className="bg-gray-100/50 rounded-lg p-3">
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Reported question text</p>
            <p className="text-gray-800 text-sm">{r.question}</p>
          </div>
          <p className="text-xs text-gray-400 italic">
            No question ID — the question may have changed or been deleted.
          </p>
          <button
            onClick={() => discardMutation.mutate()}
            disabled={discardMutation.isPending}
            className="btn-secondary flex items-center gap-2"
          >
            <Trash2 className="h-4 w-4" />
            Discard Report
          </button>
        </div>
      )}
    </div>
  );
}

function ReportsList({
  reports,
  queryClient,
}: {
  reports: ReportedQuestion[];
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  if (reports.length === 0) {
    return (
      <div className="card p-8 text-center text-gray-500">
        No pending reports
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {reports.map((r) => (
        <ReportCard key={r.id} r={r} queryClient={queryClient} />
      ))}
    </div>
  );
}

function PDFSubmissionsList({
  pdfs,
  queryClient,
}: {
  pdfs: SubmittedPDF[];
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  const approveMutation = useMutation({
    mutationFn: (id: number) => api.approvePDF(id),
    onSuccess: () => {
      toast.success('PDF approved and published');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submitted-pdfs'] });
      queryClient.invalidateQueries({ queryKey: ['pdfs'] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Failed to approve'),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => api.rejectPDF(id),
    onSuccess: () => {
      toast.success('PDF rejected and removed');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submitted-pdfs'] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Failed to reject'),
  });

  if (pdfs.length === 0) {
    return (
      <div className="card p-8 text-center text-gray-500">
        No pending PDF submissions
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {pdfs.map((pdf) => (
        <div key={pdf.id} className="card p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <FileText className="h-4 w-4 text-blue-600 flex-shrink-0" />
                <p className="text-gray-900 font-medium truncate">{pdf.original_filename}</p>
              </div>
              <p className="text-xs text-gray-500 mb-2">
                {pdf.module_name && <span className="mr-2">{pdf.module_name}</span>}
                Submitted by <span className="text-gray-700">{pdf.uploaded_by}</span>
                {pdf.submitted_at && (
                  <span className="ml-2 text-gray-400">
                    {new Date(pdf.submitted_at).toLocaleDateString()}
                  </span>
                )}
              </p>

              {/* Metadata chips */}
              <div className="flex flex-wrap gap-1 mt-2">
                {pdf.topic_names?.map(t => (
                  <span key={t} className="px-2 py-0.5 text-xs rounded-full bg-purple-50 text-purple-700">{t}</span>
                ))}
                {pdf.subtopic_names?.map(s => (
                  <span key={s} className="px-2 py-0.5 text-xs rounded-full bg-blue-900/30 text-blue-700">{s}</span>
                ))}
                {pdf.tag_names?.map(t => (
                  <span key={t} className="px-2 py-0.5 text-xs rounded bg-gray-200 text-gray-700">{t}</span>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2 flex-shrink-0">
              <a
                href={`/api/admin/pdf/submitted/${pdf.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-200 hover:bg-gray-200 text-gray-800 rounded-lg transition-colors"
              >
                <Eye className="h-3.5 w-3.5" /> View
              </a>
              <button
                onClick={() => approveMutation.mutate(pdf.id)}
                disabled={approveMutation.isPending}
                className="btn-success flex items-center gap-1.5 text-sm"
              >
                <Check className="h-3.5 w-3.5" /> Approve
              </button>
              <button
                onClick={() => rejectMutation.mutate(pdf.id)}
                disabled={rejectMutation.isPending}
                className="btn-danger flex items-center gap-1.5 text-sm"
              >
                <X className="h-3.5 w-3.5" /> Reject
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PDFRequestsList({
  requests,
  queryClient,
}: {
  requests: PDFAccessRequest[];
  queryClient: ReturnType<typeof useQueryClient>;
}) {
  const approveMutation = useMutation({
    mutationFn: (id: number) => api.approvePDFAccess(id),
    onSuccess: () => {
      toast.success('Access granted');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to approve');
    },
  });

  const denyMutation = useMutation({
    mutationFn: (id: number) => api.denyPDFAccess(id),
    onSuccess: () => {
      toast.success('Access denied');
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to deny');
    },
  });

  if (requests.length === 0) {
    return (
      <div className="card p-8 text-center text-gray-500">
        No pending PDF access requests
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {requests.map((r) => (
        <div key={r.id} className="card p-4">
          <p className="text-gray-900 font-medium mb-1">{r.username}</p>
          <p className="text-sm text-gray-500 mb-2">Discord ID: {r.discord_id}</p>
          {r.message && (
            <p className="text-sm text-gray-700 mb-3">"{r.message}"</p>
          )}

          <div className="flex gap-2">
            <button
              onClick={() => approveMutation.mutate(r.id)}
              disabled={approveMutation.isPending}
              className="btn-success flex items-center gap-2"
            >
              <Check className="h-4 w-4" />
              Grant Access
            </button>
            <button
              onClick={() => denyMutation.mutate(r.id)}
              disabled={denyMutation.isPending}
              className="btn-danger flex items-center gap-2"
            >
              <X className="h-4 w-4" />
              Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
