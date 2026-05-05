import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Play } from 'lucide-react';
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
      <div className="max-w-3xl mx-auto px-4 py-16">
        <div className="text-center space-y-6">
          <h1 className="text-3xl md:text-4xl font-bold text-white">
            flashcards.josh.software
          </h1>
          <p className="text-lg text-slate-400">
            You must be logged in to use the flashcards.
            <br />
            Click "Login with Discord" to begin.
          </p>

          <a
            href="/login"
            className="inline-block px-8 py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
          >
            Login with Discord
          </a>
        </div>

        <div className="mt-12 grid md:grid-cols-2 gap-6">
          <LiveActivity />
          <LiveLeaderboard maxItems={5} />
        </div>

        <SponsorWidget />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="grid lg:grid-cols-[1fr_320px] gap-6">
        <div className="space-y-6">
          <div className="card p-6 space-y-4">
            <ModuleSelector
              modules={modulesData?.modules || []}
              moduleGroups={modulesData?.module_groups || []}
              selectedModule={filters.module}
              onSelect={setModule}
            />

            {filters.module && (
              <>
                <FilterBar
                  filters={filterData}
                  selectedTopics={filters.topics}
                  selectedSubtopics={filters.subtopics}
                  onTopicsChange={setTopics}
                  onSubtopicsChange={setSubtopics}
                  isLoading={filtersLoading}
                />

                {state === 'idle' && (
                  <button
                    onClick={startQuiz}
                    className="btn-primary w-full flex items-center justify-center gap-2 py-3"
                  >
                    <Play className="h-5 w-5" />
                    Start Quiz
                  </button>
                )}
              </>
            )}

            {!filters.module && (
              <div className="py-8 text-center">
                <h2 className="text-2xl font-bold text-white mb-2">flashcards.josh.software</h2>
                <p className="text-slate-400">
                  Select a module to begin practicing.
                  <br />
                  Use the filters above to narrow down your questions.
                </p>
              </div>
            )}
          </div>

          {state === 'loading' && (
            <div className="card p-12 flex items-center justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
            </div>
          )}

          {question && (state === 'answering' || state === 'correct') && (
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
          )}

          {error && state === 'idle' && (
            <div className="card p-6 text-center">
              <p className="text-slate-400">{error}</p>
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

        <div className="space-y-6">
          <LiveActivity />
          <LiveLeaderboard module={filters.module} maxItems={5} />
        </div>
      </div>

      <SponsorWidget />
    </div>
  );
}
