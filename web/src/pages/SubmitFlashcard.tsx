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

  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [module, setModuleState] = useState('');
  const [topic, setTopicState] = useState('');
  const [subtopic, setSubtopicState] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [distractors, setDistractors] = useState(['', '', '', '']);

  const [duplicates, setDuplicates] = useState<DuplicateMatch[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const dupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.getModules,
  });

  const topicEnabled = !!module;
  const subtopicEnabled = topicEnabled && topic.trim().length > 0;
  const tagsEnabled = subtopicEnabled && subtopic.trim().length > 0;

  const allComplete =
    question.trim() &&
    answer.trim() &&
    module &&
    topic.trim() &&
    subtopic.trim() &&
    tags.length >= MIN_TAGS;

  const handleModuleChange = (m: string) => {
    setModuleState(m);
    setTopicState('');
    setSubtopicState('');
    setTags([]);
  };

  const handleTopicChange = (t: string) => {
    setTopicState(t);
    setSubtopicState('');
    setTags([]);
  };

  const handleSubtopicChange = (st: string) => {
    setSubtopicState(st);
    setTags([]);
  };

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

  const submitMutation = useMutation({
    mutationFn: () =>
      api.submitFlashcard({
        question: question.trim(),
        answer: answer.trim(),
        module,
        topic: topic.trim(),
        subtopic: subtopic.trim(),
        tags: tags.join(', '),
        distractors: distractors.filter((d) => d.trim() !== '').map((d) => d.trim()),
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
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Submit a Flashcard</h1>
        <p className="text-gray-500 mt-2">
          Contribute your own flashcard for review. Fill in all required fields.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card p-6 space-y-6">
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Question <span className="text-red-500">*</span>
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
            <p className="mt-2 text-xs text-gray-400 animate-pulse">Checking for duplicates...</p>
          )}

          {!isChecking && duplicates.length > 0 && (
            <div className="mt-3 rounded-xl bg-amber-50 p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                <span className="text-sm font-semibold text-amber-700">Potential duplicates found</span>
              </div>
              <div className="space-y-2">
                {duplicates.map((dup) => {
                  const pct = Math.round(dup.similarity * 100);
                  const color = pct > 60 ? 'text-red-600' : pct >= 30 ? 'text-amber-600' : 'text-emerald-600';
                  return (
                    <div key={dup.id} className="rounded-lg bg-white p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-gray-700 leading-snug">{dup.question}</p>
                          <p className="mt-1 text-xs text-gray-400">Answer: {dup.answer}</p>
                        </div>
                        <span className={`shrink-0 text-xs font-bold ${color}`}>{pct}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-3 text-xs text-gray-500">
                You can still submit — these are just warnings.
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Answer <span className="text-red-500">*</span>
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

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Module <span className="text-red-500">*</span>
          </label>
          <ModuleSelector
            modules={modulesData?.modules || []}
            moduleGroups={modulesData?.module_groups || []}
            selectedModule={module}
            onSelect={handleModuleChange}
          />
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Topic <span className="text-red-500">*</span>
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

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Subtopic <span className="text-red-500">*</span>
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

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Tags <span className="text-red-500">*</span>{' '}
            <span className="text-gray-400 font-normal">(at least {MIN_TAGS} required)</span>
          </label>
          <TagInput
            tags={tags}
            onChange={setTags}
            onFetch={tagsEnabled ? fetchTagSuggestions : undefined}
            minCount={MIN_TAGS}
            disabled={!tagsEnabled}
          />
        </div>

        {allComplete && (
          <div className="rounded-xl bg-gray-50 overflow-hidden">
            <details>
              <summary className="px-4 py-3 cursor-pointer hover:bg-gray-100 transition-colors flex items-center justify-between select-none">
                <div>
                  <span className="text-sm font-bold text-purple-700">Submit Distractors</span>
                  <span className="text-sm text-gray-400 ml-2">(optional)</span>
                </div>
              </summary>

              <div className="p-4 space-y-4">
                <p className="text-sm text-gray-500">
                  Help improve this question by suggesting plausible wrong answers that are challenging but clearly incorrect.
                </p>

                <AIPromptHelper question={question} answer={answer} />

                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-600 mb-1">
                      Suggested Distractors{' '}
                      <span className="text-gray-400 font-normal">(wrong answers that are plausible)</span>
                    </label>
                    <p className="text-xs text-gray-400 mb-3">
                      You can submit 1-4 distractors. Good distractors are wrong but believable.
                    </p>
                  </div>
                  {distractors.map((d, i) => (
                    <div key={i}>
                      <label className="block text-xs text-gray-400 mb-1">Distractor {i + 1}:</label>
                      <textarea
                        value={d}
                        onChange={(e) => updateDistractor(i, e.target.value)}
                        rows={2}
                        placeholder="Enter a plausible wrong answer..."
                        className="input text-sm"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </details>
          </div>
        )}

        <button
          type="submit"
          disabled={submitMutation.isPending || tags.length < MIN_TAGS}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-50"
        >
          {submitMutation.isPending ? (
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent" />
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
