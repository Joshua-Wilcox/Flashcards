import { useState, useCallback } from 'react';
import { toast } from 'sonner';
import { api } from '../api/client';
import type { QuestionResponse } from '../types';

export type QuizState = 'idle' | 'loading' | 'answering' | 'correct' | 'incorrect';

interface QuizFilters {
  module: string;
  topics: string[];
  subtopics: string[];
  tags: string[];
}

export function useQuiz() {
  const [state, setState] = useState<QuizState>('idle');
  const [question, setQuestion] = useState<QuestionResponse | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [incorrectAnswers, setIncorrectAnswers] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<QuizFilters>({
    module: '',
    topics: [],
    subtopics: [],
    tags: [],
  });
  const [error, setError] = useState<string | null>(null);

  const fetchQuestion = useCallback(async (specificQuestionId?: string) => {
    if (!filters.module) return;

    setState('loading');
    setError(null);
    setSelectedAnswer(null);
    setIncorrectAnswers(new Set());

    try {
      const response = await api.getQuestion({
        module: filters.module,
        topics: filters.topics.length > 0 ? filters.topics : undefined,
        subtopics: filters.subtopics.length > 0 ? filters.subtopics : undefined,
        tags: filters.tags.length > 0 ? filters.tags : undefined,
        question_id: specificQuestionId,
      });

      if (response.error) {
        setError(response.error);
        setState('idle');
        setQuestion(null);
      } else {
        setQuestion(response);
        setState('answering');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load question');
      setState('idle');
    }
  }, [filters]);

  const submitAnswer = useCallback(async (answer: string) => {
    if (!question || state !== 'answering') return;

    setSelectedAnswer(answer);

    try {
      const response = await api.checkAnswer(question.token, answer);

      if (response.error) {
        setError(response.error);
        return;
      }

      if (response.correct) {
        setState('correct');
      } else {
        setIncorrectAnswers(prev => new Set(prev).add(answer));
        setState('answering');
        toast.error('Incorrect! Your streak has been reset.', {
          duration: 3000,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to check answer');
    }
  }, [question, state]);

  const nextQuestion = useCallback(() => {
    fetchQuestion();
  }, [fetchQuestion]);

  const setModule = useCallback((module: string) => {
    setFilters(prev => ({
      ...prev,
      module,
      topics: [],
      subtopics: [],
      tags: [],
    }));
    setQuestion(null);
    if (module) {
      setState('loading');
      setError(null);
      setSelectedAnswer(null);
      setIncorrectAnswers(new Set());
      api.getQuestion({ module }).then((response) => {
        if (response.error) {
          setError(response.error);
          setState('idle');
          setQuestion(null);
        } else {
          setQuestion(response);
          setState('answering');
        }
      }).catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load question');
        setState('idle');
      });
    } else {
      setState('idle');
    }
  }, []);

  const setTopics = useCallback((topics: string[]) => {
    setFilters(prev => ({ ...prev, topics, subtopics: [] }));
  }, []);

  const setSubtopics = useCallback((subtopics: string[]) => {
    setFilters(prev => ({ ...prev, subtopics }));
  }, []);

  const setTags = useCallback((tags: string[]) => {
    setFilters(prev => ({ ...prev, tags }));
  }, []);

  const startQuiz = useCallback(() => {
    if (filters.module) {
      fetchQuestion();
    }
  }, [filters.module, fetchQuestion]);

  return {
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
    setTags,
    startQuiz,
  };
}
