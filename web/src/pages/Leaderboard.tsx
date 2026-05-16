import { useState, useCallback, useMemo, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Trophy, Zap, Target, Award, ChevronDown, Percent, Crown, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../api/client';
import { useWebSocket, isLeaderboardUpdate } from '../api/websocket';
import ModuleSelector from '../components/ModuleSelector';
import type { LeaderboardEntry, LeaderboardTotals, WebSocketMessage, LeaderboardUpdate } from '../types';
import { formatRelativeTime } from '../utils/time';

type SortField = 'correct_answers' | 'total_answers' | 'current_streak' | 'max_streak' | 'approved_cards' | 'accuracy' | 'last_answer_time';

export default function Leaderboard() {
  const [sortBy, setSortBy] = useState<SortField>('correct_answers');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [selectedModule, setSelectedModule] = useState<string>('');
  const queryClient = useQueryClient();

  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.getModules,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard', sortBy, sortOrder, selectedModule],
    queryFn: () => api.getLeaderboard(sortBy, sortOrder, selectedModule || undefined),
  });

  const handleWebSocketMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'leaderboard_update' && isLeaderboardUpdate(message.data)) {
      const update = message.data as LeaderboardUpdate;

      queryClient.setQueryData<{ leaderboard: LeaderboardEntry[]; totals: LeaderboardTotals }>(
        ['leaderboard', sortBy, sortOrder, selectedModule],
        (oldData) => {
          if (!oldData) return oldData;

          const existingIndex = oldData.leaderboard.findIndex(
            (e) => e.user_id === update.user_id
          );

          let newLeaderboard: LeaderboardEntry[];

          if (existingIndex >= 0) {
            newLeaderboard = oldData.leaderboard.map((entry) =>
              entry.user_id === update.user_id
                ? {
                    ...entry,
                    username: update.username,
                    correct_answers: update.correct_answers,
                    total_answers: update.total_answers,
                    current_streak: update.current_streak,
                    max_streak: update.max_streak,
                    approved_cards: update.approved_cards,
                    last_answer_time: update.last_answer_time,
                  }
                : entry
            );
          } else {
            newLeaderboard = [
              ...oldData.leaderboard,
              {
                user_id: update.user_id,
                username: update.username,
                correct_answers: update.correct_answers,
                total_answers: update.total_answers,
                current_streak: update.current_streak,
                max_streak: update.max_streak,
                approved_cards: update.approved_cards,
                last_answer_time: update.last_answer_time,
              },
            ];
          }

          newLeaderboard.sort((a, b) => {
            let aVal: number, bVal: number;

            if (sortBy === 'accuracy') {
              aVal = a.total_answers > 0 ? a.correct_answers / a.total_answers : 0;
              bVal = b.total_answers > 0 ? b.correct_answers / b.total_answers : 0;
            } else if (sortBy === 'last_answer_time') {
              aVal = a.last_answer_time ? new Date(a.last_answer_time).getTime() : 0;
              bVal = b.last_answer_time ? new Date(b.last_answer_time).getTime() : 0;
            } else {
              aVal = a[sortBy];
              bVal = b[sortBy];
            }

            return sortOrder === 'desc' ? bVal - aVal : aVal - bVal;
          });

          // Optimistically increment totals
          const newTotals = oldData.totals ? {
            total_answers: oldData.totals.total_answers + 1,
            total_correct: update.current_streak > 0 ? oldData.totals.total_correct + 1 : oldData.totals.total_correct,
            total_users: existingIndex < 0 ? oldData.totals.total_users + 1 : oldData.totals.total_users,
          } : oldData.totals;

          return { leaderboard: newLeaderboard, totals: newTotals };
        }
      );
    }
  }, [queryClient, sortBy, sortOrder, selectedModule]);

  useWebSocket(handleWebSocketMessage);

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const getRankDisplay = (rank: number) => {
    if (rank === 1) return <Trophy className="h-6 w-6 text-amber-500" />;
    if (rank === 2) return <Trophy className="h-6 w-6 text-gray-400" />;
    if (rank === 3) return <Trophy className="h-6 w-6 text-amber-700" />;
    return <span className="text-gray-400 font-medium">{rank}</span>;
  };

  const SortHeader = ({
    field,
    label,
    icon: Icon,
  }: {
    field: SortField;
    label: string;
    icon: React.ElementType;
  }) => (
    <button
      onClick={() => handleSort(field)}
      className={`flex items-center justify-end gap-1 text-sm font-medium transition-colors ${
        sortBy === field ? 'text-blue-600' : 'text-gray-400 hover:text-gray-700'
      }`}
    >
      <Icon className="h-4 w-4" />
      <span className="hidden sm:inline">{label}</span>
      {sortBy === field && (
        <ChevronDown
          className={`h-4 w-4 transition-transform ${
            sortOrder === 'asc' ? 'rotate-180' : ''
          }`}
        />
      )}
    </button>
  );

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Trophy className="h-7 w-7 text-amber-500" />
          Leaderboard
        </h1>

        <div className="w-full sm:w-64">
          <ModuleSelector
            modules={modulesData?.modules || []}
            moduleGroups={modulesData?.module_groups || []}
            selectedModule={selectedModule}
            onSelect={setSelectedModule}
          />
        </div>
      </div>

      {data?.totals && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-center">
            <p className="text-sm font-medium text-blue-600">Total Questions Answered</p>
            <p className="text-2xl font-bold text-blue-700">{data.totals.total_answers.toLocaleString()}</p>
          </div>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-center">
            <p className="text-sm font-medium text-emerald-600">Total Correct</p>
            <p className="text-2xl font-bold text-emerald-700">{data.totals.total_correct.toLocaleString()}</p>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-center">
            <p className="text-sm font-medium text-amber-600">Overall Accuracy</p>
            <p className="text-2xl font-bold text-amber-700">
              {data.totals.total_answers > 0
                ? Math.round((data.totals.total_correct / data.totals.total_answers) * 100)
                : 0}%
            </p>
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="grid grid-cols-[3rem_1fr_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem] gap-2 p-4 bg-gray-50 border-b border-gray-100">
          <div className="text-sm font-medium text-gray-400 text-center">#</div>
          <div className="text-sm font-medium text-gray-400">Player</div>
          <SortHeader field="correct_answers" label="Correct" icon={Target} />
          <SortHeader field="total_answers" label="Total" icon={Award} />
          <SortHeader field="accuracy" label="Acc" icon={Percent} />
          <SortHeader field="current_streak" label="Streak" icon={Zap} />
          <SortHeader field="max_streak" label="Best" icon={Crown} />
          <SortHeader field="approved_cards" label="Cards" icon={Award} />
          <SortHeader field="last_answer_time" label="Active" icon={Clock} />
        </div>

        {isLoading ? (
          <div className="p-8 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
          </div>
        ) : data?.leaderboard.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            No entries yet. Start studying to appear on the leaderboard!
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            <AnimatePresence mode="popLayout">
              {data?.leaderboard.map((entry, index) => (
                <LeaderboardRow
                  key={entry.user_id}
                  entry={entry}
                  rank={index + 1}
                  getRankDisplay={getRankDisplay}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}

function LeaderboardRow({
  entry,
  rank,
  getRankDisplay,
}: {
  entry: LeaderboardEntry;
  rank: number;
  getRankDisplay: (rank: number) => React.ReactNode;
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const accuracy = useMemo(() =>
    entry.total_answers > 0
      ? Math.round((entry.correct_answers / entry.total_answers) * 100)
      : 0,
    [entry.correct_answers, entry.total_answers]
  );

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      className={`grid grid-cols-[3rem_1fr_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem] gap-2 p-4 items-center ${
        rank <= 3 ? 'bg-amber-50/50' : ''
      }`}
    >
      <div className="flex justify-center">{getRankDisplay(rank)}</div>

      <div className="min-w-0">
        <p className="font-semibold text-gray-900 truncate">{entry.username}</p>
      </div>

      <div className="text-right">
        <p className="font-bold text-blue-600">
          {entry.correct_answers.toLocaleString()}
        </p>
      </div>

      <div className="text-right">
        <p className="text-gray-600">{entry.total_answers.toLocaleString()}</p>
      </div>

      <div className="text-right">
        <p className={`font-medium ${
          accuracy >= 80 ? 'text-emerald-600' :
          accuracy >= 60 ? 'text-amber-600' :
          'text-gray-400'
        }`}>
          {accuracy}%
        </p>
      </div>

      <div className="text-right">
        {entry.current_streak > 0 ? (
          <span className="flex items-center justify-end gap-1 text-amber-600 font-medium">
            <Zap className="h-4 w-4" />
            {entry.current_streak}
          </span>
        ) : (
          <span className="text-gray-300">-</span>
        )}
      </div>

      <div className="text-right">
        {entry.max_streak > 0 ? (
          <span className="flex items-center justify-end gap-1 text-purple-600 font-medium">
            <Crown className="h-4 w-4" />
            {entry.max_streak}
          </span>
        ) : (
          <span className="text-gray-300">-</span>
        )}
      </div>

      <div className="text-right">
        <p className="text-gray-600">{entry.approved_cards}</p>
      </div>

      <div className="text-right">
        <p className="text-gray-400 text-sm">
          {formatRelativeTime(entry.last_answer_time)}
        </p>
      </div>
    </motion.div>
  );
}
