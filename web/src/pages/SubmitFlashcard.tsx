import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Send, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import ModuleSelector from '../components/ModuleSelector';
import SuggestField from '../components/SuggestField';
import TagInput from '../components/TagInput';
import AIPromptHelper from '../components/AIPromptHelper';

interface DuplicateMatch {
  id: string;
  question: string;
  answer: string;
  similarity: number;
}

const MIN_TAGS = 3;

export default function SubmitFlashcard() {
  const queryClient = useQueryClient();

  // Core form state
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [module, setModuleState] = useState('');
  const [topic, setTopicState] = useState('');
  const [subtopic, setSubtopicState] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [distractors, setDistractors] = useState(['', '', '', '']);

  // Duplicate detection
  const [duplicates, setDuplicates] = useState<DuplicateMatch[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const dupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Modules
  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.getModules,
  });

  // Sequential enabling
  const topicEnabled = !!module;
  const subtopicEnabled = topicEnabled && topic.trim().length > 0;
  const tagsEnabled = subtopicEnabled && subtopic.trim().length > 0;

  // All required fields complete → show distractor section
  const allComplete =
    question.trim() &&
    answer.trim() &&
    module &&
    topic.trim() &&
    subtopic.trim() &&
    tags.length >= MIN_TAGS;

  // Reset downstream when module changes
  const handleModuleChange = (m: string) => {
    setModuleState(m);
    setTopicState('');
    setSubtopicState('');
    setTags([]);
  };

  // Reset subtopic + tags when topic changes
  const handleTopicChange = (t: string) => {
    setTopicState(t);
    setSubtopicState('');
    setTags([]);
  };

  // Reset tags when subtopic changes
  const handleSubtopicChange = (st: string) => {
    setSubtopicState(st);
    setTags([]);
  };

  // Suggestion fetchers
  const fetchTopics = useCallback(
    (q: string) => api.suggestTopics(module, q).then((r) => r.suggestions),
    [module]
  );
  const fetchSubtopics = useCallback(
    (q: string) => api.suggestSubtopics(module, topic, q).then((r) => r.suggestions),
    [module, topic]
  );
  const fetchTagSuggestions = useCallback(
    (q: string) => api.suggestTags(module, q).then((r) => r.suggestions),
    [module]
  );

  // Duplicate detection
  useEffect(() => {
    if (dupTimerRef.current) clearTimeout(dupTimerRef.current);
    if (question.length < 10 || !module) {
      setDuplicates([]);
      return;
    }
    setIsChecking(true);
    dupTimerRef.current = setTimeout(async () => {
      try {
        const result = await api.checkDuplicates(question, module);
        setDuplicates(result.matches ?? []);
      } catch {
        setDuplicates([]);
      } finally {
        setIsChecking(false);
      }
    }, 800);
    return () => {
      if (dupTimerRef.current) clearTimeout(dupTimerRef.current);
    };
  }, [question, module]);

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: () =>
      api.submitFlashcard({
        question,
        answer,
        module,
        topic,
        subtopic,
        tags: tags.join(', '),
        distractors: distractors.filter((d) => d.trim() !== ''),
      }),
    onSuccess: (data) => {
      toast.success(data.message);
      setQuestion('');
      setAnswer('');
      setModuleState('');
      setTopicState('');
      setSubtopicState('');
      setTags([]);
      setDistractors(['', '', '', '']);
      setDuplicates([]);
      queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to submit');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (tags.length < MIN_TAGS) {
      toast.error(`Please add at least ${MIN_TAGS} tags`);
      return;
    }
    submitMutation.mutate();
  };

  const updateDistractor = (i: number, value: string) =>
    setDistractors((prev) => prev.map((d, idx) => (idx === i ? value : d)));

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold text-white">Submit a Flashcard</h1>
        <p className="text-slate-400 mt-1">
          Contribute your own flashcard for review! Please fill in all required fields.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card p-6 space-y-6">
        {/* Question */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Question <span className="text-red-400">*</span>
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            className="input min-h-[80px]"
            placeholder="Enter your question..."
            required
          />

          {isChecking && (
            <p className="mt-2 text-xs text-slate-400 animate-pulse">Checking for duplicates...</p>
          )}

          {!isChecking && duplicates.length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-950/20 p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
                <span className="text-sm font-medium text-amber-400">Potential duplicates found</span>
              </div>
              <div className="space-y-2">
                {duplicates.map((dup) => {
                  const pct = Math.round(dup.similarity * 100);
                  const color = pct > 60 ? 'text-red-400' : pct >= 30 ? 'text-yellow-400' : 'text-green-400';
                  return (
                    <div key={dup.id} className="rounded-md bg-slate-800/60 border border-slate-700/50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-slate-200 leading-snug">{dup.question}</p>
                          <p className="mt-1 text-xs text-slate-400">Answer: {dup.answer}</p>
                        </div>
                        <span className={`shrink-0 text-xs font-semibold ${color}`}>{pct}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-xs text-slate-500">
                You can still submit — these are just warnings.
              </p>
            </div>
          )}
        </div>

        {/* Answer */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Answer <span className="text-red-400">*</span>
          </label>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={2}
            className="input"
            placeholder="Enter the correct answer..."
            required
          />
        </div>

        {/* Module */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Module <span className="text-red-400">*</span>
          </label>
          <ModuleSelector
            modules={modulesData?.modules || []}
            moduleGroups={modulesData?.module_groups || []}
            selectedModule={module}
            onSelect={handleModuleChange}
          />
        </div>

        {/* Topic */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Topic <span className="text-red-400">*</span>
          </label>
          <SuggestField
            value={topic}
            onChange={handleTopicChange}
            onFetch={fetchTopics}
            placeholder="Choose or create a topic..."
            disabled={!topicEnabled}
            required
          />
        </div>

        {/* Subtopic */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Subtopic <span className="text-red-400">*</span>
          </label>
          <SuggestField
            value={subtopic}
            onChange={handleSubtopicChange}
            onFetch={fetchSubtopics}
            placeholder="Choose or create a subtopic..."
            disabled={!subtopicEnabled}
            required
          />
        </div>

        {/* Tags */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Tags <span className="text-red-400">*</span>{' '}
            <span className="text-slate-500 font-normal">(at least {MIN_TAGS} required)</span>
          </label>
          <TagInput
            tags={tags}
            onChange={setTags}
            onFetch={tagsEnabled ? fetchTagSuggestions : undefined}
            minCount={MIN_TAGS}
            disabled={!tagsEnabled}
          />
        </div>

        {/* Distractor section — only shown once all fields complete */}
        {allComplete && (
          <div className="rounded-lg border border-slate-700 overflow-hidden">
            <details>
              <summary className="px-4 py-3 cursor-pointer bg-slate-800/50 hover:bg-slate-800 transition-colors flex items-center justify-between select-none">
                <div>
                  <span className="text-sm font-semibold text-purple-300">Submit Distractors</span>
                  <span className="text-sm text-slate-400 ml-2">(optional – help improve the question)</span>
                </div>
              </summary>

              <div className="p-4 space-y-4 bg-slate-900/30">
                <p className="text-sm text-slate-400">
                  Help improve this question by suggesting plausible wrong answers that are challenging but clearly incorrect.
                </p>

                {/* AI Prompt helper */}
                <AIPromptHelper question={question} answer={answer} />

                {/* 4 distractor inputs */}
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">
                      Suggested Distractors{' '}
                      <span className="text-slate-500 font-normal">(wrong answers that are plausible but incorrect)</span>
                    </label>
                    <p className="text-xs text-slate-500 mb-3">
                      You can submit 1–4 distractors. Good distractors are wrong but believable answers that test understanding.
                    </p>
                  </div>
                  {distractors.map((d, i) => (
                    <div key={i}>
                      <label className="block text-xs text-slate-500 mb-1">Distractor {i + 1}:</label>
                      <textarea
                        value={d}
                        onChange={(e) => updateDistractor(i, e.target.value)}
                        rows={2}
                        placeholder="Enter a plausible wrong answer..."
                        className="w-full bg-slate-900 text-white rounded-lg px-3 py-2 border border-slate-700 focus:border-blue-500 focus:outline-none resize-y text-sm"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </details>
          </div>
        )}

        {/* Submit button */}
        <button
          type="submit"
          disabled={submitMutation.isPending || tags.length < MIN_TAGS}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3 disabled:opacity-50"
        >
          {submitMutation.isPending ? (
            <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-white" />
          ) : (
            <>
              <Send className="h-5 w-5" />
              Submit for Review
            </>
          )}
        </button>
      </form>
    </div>
  );
}
