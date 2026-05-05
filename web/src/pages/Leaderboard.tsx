import { useState, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Trophy, Zap, Target, Award, ChevronDown, Percent } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../api/client';
import { useWebSocket, isLeaderboardUpdate } from '../api/websocket';
import ModuleSelector from '../components/ModuleSelector';
import type { LeaderboardEntry, WebSocketMessage, LeaderboardUpdate } from '../types';

type SortField = 'correct_answers' | 'total_answers' | 'current_streak' | 'approved_cards' | 'accuracy';

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
      
      queryClient.setQueryData<{ leaderboard: LeaderboardEntry[] }>(
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
                    approved_cards: update.approved_cards,
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
                approved_cards: update.approved_cards,
              },
            ];
          }
          
          newLeaderboard.sort((a, b) => {
            let aVal: number, bVal: number;
            
            if (sortBy === 'accuracy') {
              aVal = a.total_answers > 0 ? a.correct_answers / a.total_answers : 0;
              bVal = b.total_answers > 0 ? b.correct_answers / b.total_answers : 0;
            } else {
              aVal = a[sortBy];
              bVal = b[sortBy];
            }
            
            return sortOrder === 'desc' ? bVal - aVal : aVal - bVal;
          });
          
          return { leaderboard: newLeaderboard };
        }
      );
    }
  }, [queryClient, sortBy, sortOrder, selectedModule]);

  const { isConnected } = useWebSocket(handleWebSocketMessage);

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const getRankDisplay = (rank: number) => {
    if (rank === 1) return <Trophy className="h-6 w-6 text-yellow-400" />;
    if (rank === 2) return <Trophy className="h-6 w-6 text-slate-300" />;
    if (rank === 3) return <Trophy className="h-6 w-6 text-amber-600" />;
    return <span className="text-slate-400 font-medium">{rank}</span>;
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
        sortBy === field ? 'text-blue-400' : 'text-slate-400 hover:text-white'
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
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Trophy className="h-7 w-7 text-yellow-400" />
            Leaderboard
          </h1>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
              }`}
            />
            <span className="text-xs text-slate-400">
              {isConnected ? 'Live' : 'Connecting...'}
            </span>
          </div>
        </div>

        <div className="w-full sm:w-64">
          <ModuleSelector
            modules={modulesData?.modules || []}
            moduleGroups={modulesData?.module_groups || []}
            selectedModule={selectedModule}
            onSelect={setSelectedModule}
          />
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="grid grid-cols-[3rem_1fr_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem] gap-2 p-4 bg-slate-900/50 border-b border-slate-700">
          <div className="text-sm font-medium text-slate-400 text-center">#</div>
          <div className="text-sm font-medium text-slate-400">Player</div>
          <SortHeader field="correct_answers" label="Correct" icon={Target} />
          <SortHeader field="total_answers" label="Total" icon={Award} />
          <SortHeader field="accuracy" label="Acc" icon={Percent} />
          <SortHeader field="current_streak" label="Streak" icon={Zap} />
          <SortHeader field="approved_cards" label="Cards" icon={Award} />
        </div>

        {isLoading ? (
          <div className="p-8 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        ) : data?.leaderboard.length === 0 ? (
          <div className="p-8 text-center text-slate-400">
            No entries yet. Start studying to appear on the leaderboard!
          </div>
        ) : (
          <div className="divide-y divide-slate-700">
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
      className={`grid grid-cols-[3rem_1fr_4.5rem_4.5rem_4.5rem_4.5rem_4.5rem] gap-2 p-4 items-center ${
        rank <= 3 ? 'bg-slate-800/50' : ''
      }`}
    >
      <div className="flex justify-center">{getRankDisplay(rank)}</div>

      <div className="min-w-0">
        <p className="font-medium text-white truncate">{entry.username}</p>
      </div>

      <div className="text-right">
        <p className="font-semibold text-blue-400">
          {entry.correct_answers.toLocaleString()}
        </p>
      </div>

      <div className="text-right">
        <p className="text-slate-300">{entry.total_answers.toLocaleString()}</p>
      </div>

      <div className="text-right">
        <p className={`font-medium ${
          accuracy >= 80 ? 'text-green-400' : 
          accuracy >= 60 ? 'text-yellow-400' : 
          'text-slate-400'
        }`}>
          {accuracy}%
        </p>
      </div>

      <div className="text-right">
        {entry.current_streak > 0 ? (
          <span className="flex items-center justify-end gap-1 text-yellow-400">
            <Zap className="h-4 w-4" />
            {entry.current_streak}
          </span>
        ) : (
          <span className="text-slate-500">-</span>
        )}
      </div>

      <div className="text-right">
        <p className="text-slate-300">{entry.approved_cards}</p>
      </div>
    </motion.div>
  );
}
