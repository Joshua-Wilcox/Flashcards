import { useState, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Trophy, Zap, TrendingUp } from 'lucide-react';
import { api } from '../api/client';
import { useWebSocket, isLeaderboardUpdate } from '../api/websocket';
import type { LeaderboardEntry, WebSocketMessage } from '../types';

interface LiveLeaderboardProps {
  module?: string;
  maxItems?: number;
}

export default function LiveLeaderboard({ module, maxItems = 10 }: LiveLeaderboardProps) {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard', 'correct_answers', 'desc', module],
    queryFn: () => api.getLeaderboard('correct_answers', 'desc', module),
    refetchInterval: 60000,
  });

  useEffect(() => {
    if (data?.leaderboard) {
      setEntries(data.leaderboard.slice(0, maxItems));
    }
  }, [data, maxItems]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'leaderboard_update' && isLeaderboardUpdate(message.data)) {
      const update = message.data;
      setEntries((prev) => {
        const updated = prev.map((entry) =>
          entry.user_id === update.user_id
            ? {
                ...entry,
                correct_answers: update.correct_answers,
                current_streak: update.current_streak,
              }
            : entry
        );

        return updated.sort((a, b) => b.correct_answers - a.correct_answers);
      });
    }
  }, []);

  useWebSocket(handleMessage);

  const getRankIcon = (rank: number) => {
    if (rank === 1) return <Trophy className="h-5 w-5 text-yellow-400" />;
    if (rank === 2) return <Trophy className="h-5 w-5 text-slate-300" />;
    if (rank === 3) return <Trophy className="h-5 w-5 text-amber-600" />;
    return <span className="w-5 text-center text-slate-500">{rank}</span>;
  };

  if (isLoading) {
    return (
      <div className="card p-4">
        <div className="animate-pulse space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-slate-700 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2 mb-4">
        <TrendingUp className="h-4 w-4" />
        Top Players
      </h3>

      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {entries.map((entry, index) => (
            <motion.div
              key={entry.user_id}
              layout
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className={`flex items-center gap-3 p-3 rounded-lg ${
                index === 0
                  ? 'bg-yellow-900/20 border border-yellow-700/50'
                  : 'bg-slate-900/50'
              }`}
            >
              <div className="flex-shrink-0">{getRankIcon(index + 1)}</div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-200 truncate">
                  {entry.username}
                </p>
              </div>

              <div className="flex items-center gap-4 flex-shrink-0">
                {entry.current_streak > 0 && (
                  <span className="flex items-center gap-1 text-xs text-yellow-400">
                    <Zap className="h-3 w-3" />
                    {entry.current_streak}
                  </span>
                )}
                <span className="text-sm font-semibold text-blue-400">
                  {entry.correct_answers.toLocaleString()}
                </span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
