import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '../api/client';
import { useQuiz } from '../hooks/useQuiz';
import ModuleSelector from '../components/ModuleSelector';
import FilterBar from '../components/FilterBar';
import QuizCard from '../components/QuizCard';
import LiveActivity from '../components/LiveActivity';
import LiveLeaderboard from '../components/LiveLeaderboard';
import SponsorWidget from '../components/SponsorWidget';
import type { User, FilterData } from '../types';

interface HomeProps {
  user?: User;
}

export default function Home({ user }: HomeProps) {
  const {
    state,
    question,
    selectedAnswer,
    incorrectAnswers,
    filters,
    error,
    fetchQuestion,
    submitAnswer,
    nextQuestion,
    setModule,
    setTopics,
    setSubtopics,
    startQuiz,
  } = useQuiz();

  const [filterData, setFilterData] = useState<FilterData>({
    topics: [],
    subtopics: [],
    tags: [],
  });

  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.getModules,
  });

  const { data: filtersResponse, isLoading: filtersLoading } = useQuery({
    queryKey: ['filters', filters.module, filters.topics],
    queryFn: () => api.getFilters(filters.module, filters.topics),
    enabled: !!filters.module,
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    if (filtersResponse) {
      setFilterData({
        topics: filtersResponse.topics ?? [],
        subtopics: filtersResponse.subtopics ?? [],
        tags: filtersResponse.tags ?? [],
      });
    }
  }, [filtersResponse]);

  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  useEffect(() => {
    const handleReset = () => setModule('');
    window.addEventListener('reset-quiz', handleReset);
    return () => window.removeEventListener('reset-quiz', handleReset);
  }, [setModule]);

  const handleReportQuestion = async (data: {
    question: string;
    question_id: string;
    message: string;
    distractors: string;
  }) => {
    try {
      await api.reportQuestion(data);
      toast.success('Report submitted. Thank you!');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to submit report');
    }
  };

  const handleSubmitDistractors = async (data: {
    question_id: string;
    distractors: string[];
  }) => {
    try {
      await api.submitDistractor(data.question_id, data.distractors);
      toast.success('Distractors submitted for review!');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to submit distractors');
    }
  };

  if (!user?.authenticated) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-20">
        <div className="text-center space-y-6">
          <img src="/favicon.png" alt="" className="h-16 w-16 mx-auto" />
          <h1 className="text-4xl font-extrabold text-gray-900">
            flashcards.josh.software
          </h1>
          <p className="text-lg text-gray-500 max-w-md mx-auto">
            A smarter way to study. Log in to start practising with flashcards tailored to your modules.
          </p>

          <a
            href="/login"
            className="inline-block px-8 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors shadow-sm text-lg"
          >
            Login with Discord
          </a>
        </div>

        <div className="mt-16 grid md:grid-cols-2 gap-6">
          <LiveActivity />
          <LiveLeaderboard maxItems={5} />
        </div>

        <SponsorWidget />
      </div>
    );
  }

  return (
    <div className="px-4 lg:px-6 flex flex-col h-full overflow-hidden">
      <div className="grid lg:grid-cols-[260px_1fr_260px] gap-6 flex-1 min-h-0 py-6 items-stretch">
        <div className="hidden lg:flex min-h-0 overflow-hidden">
          <LiveActivity />
        </div>

        <div className="card flex flex-col overflow-hidden min-h-0">
          <div className="p-6 flex-shrink-0 space-y-5">
            <ModuleSelector
              modules={modulesData?.modules || []}
              moduleGroups={modulesData?.module_groups || []}
              selectedModule={filters.module}
              onSelect={setModule}
            />

            {filters.module && (
              <FilterBar
                filters={filterData}
                selectedTopics={filters.topics}
                selectedSubtopics={filters.subtopics}
                onTopicsChange={setTopics}
                onSubtopicsChange={setSubtopics}
                isLoading={filtersLoading}
              />
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-6 pb-6">
            {!filters.module && (
              <div className="h-full flex flex-col items-center justify-center text-center space-y-4">
                <img src="/favicon.png" alt="" className="h-12 w-12" />
                <h2 className="text-xl font-bold text-gray-900">flashcards.josh.software</h2>
                <p className="text-gray-400 text-sm">Select a module above to begin studying.</p>
                <div className="flex items-center justify-center gap-4 pt-2">
                  <a
                    href="https://josh.software"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    josh.software
                  </a>
                  <span className="text-gray-300">|</span>
                  <a
                    href="https://github.com/Joshua-Wilcox/Flashcards"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    GitHub
                  </a>
                </div>
              </div>
            )}

            {state === 'loading' && (
              <div className="h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-10 w-10 border-2 border-blue-600 border-t-transparent"></div>
              </div>
            )}

            {question && (state === 'answering' || state === 'correct') && (
              <div className="space-y-6">
                <QuizCard
                  question={question}
                  state={state}
                  selectedAnswer={selectedAnswer}
                  incorrectAnswers={incorrectAnswers}
                  onAnswerSelect={submitAnswer}
                  onNextQuestion={nextQuestion}
                  onReportQuestion={handleReportQuestion}
                  onSubmitDistractors={handleSubmitDistractors}
                  onAnswerEdited={() => fetchQuestion(question.question_id)}
                  isAdmin={user?.is_admin}
                />
              </div>
            )}

            {error && state === 'idle' && (
              <div className="h-full flex flex-col items-center justify-center text-center">
                <p className="text-gray-500">{error}</p>
                {filters.module && (
                  <button
                    onClick={startQuiz}
                    className="btn-secondary mt-4"
                  >
                    Try Again
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="hidden lg:flex min-h-0 overflow-hidden">
          <LiveLeaderboard module={filters.module} />
        </div>
      </div>

      <SponsorWidget />
    </div>
  );
}
