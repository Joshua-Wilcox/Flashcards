import { useState, useCallback, useEffect, useRef } from 'react';
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

const ITEM_HEIGHT = 48;

export default function LiveLeaderboard({ module, maxItems }: LiveLeaderboardProps) {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [visibleCount, setVisibleCount] = useState(maxItems ?? 10);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (maxItems) return;
    const el = containerRef.current;
    if (!el) return;
    const calculate = () => {
      const available = el.clientHeight;
      setVisibleCount(Math.max(3, Math.floor(available / ITEM_HEIGHT)));
    };
    calculate();
    const observer = new ResizeObserver(calculate);
    observer.observe(el);
    return () => observer.disconnect();
  }, [maxItems]);

  const { data } = useQuery({
    queryKey: ['leaderboard', 'correct_answers', 'desc', module],
    queryFn: () => api.getLeaderboard('correct_answers', 'desc', module),
    refetchInterval: 60000,
  });

  useEffect(() => {
    if (data?.leaderboard) {
      setEntries(data.leaderboard.slice(0, visibleCount));
    }
  }, [data, visibleCount]);

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

        return updated.sort((a, b) => b.correct_answers - a.correct_answers).slice(0, visibleCount);
      });
    }
  }, [visibleCount]);

  useWebSocket(handleMessage);

  const getRankIcon = (rank: number) => {
    if (rank === 1) return <Trophy className="h-5 w-5 text-amber-500" />;
    if (rank === 2) return <Trophy className="h-5 w-5 text-gray-400" />;
    if (rank === 3) return <Trophy className="h-5 w-5 text-amber-700" />;
    return <span className="w-5 text-center text-gray-400 text-sm font-medium">{rank}</span>;
  };

  return (
    <div className="card p-5 w-full flex flex-col overflow-hidden">
      <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4 flex-shrink-0">
        <TrendingUp className="h-4 w-4 text-blue-600" />
        Top Players
      </h3>

      <div ref={containerRef} className="flex flex-col gap-2 flex-1 overflow-hidden">
        <AnimatePresence mode="sync">
          {entries.slice(0, visibleCount).map((entry, index) => (
            <motion.div
              key={entry.user_id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className={`flex items-center gap-3 p-2.5 rounded-xl flex-shrink-0 ${
                index === 0
                  ? 'bg-amber-50'
                  : 'bg-gray-50'
              }`}
            >
              <div className="flex-shrink-0">{getRankIcon(index + 1)}</div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {entry.username}
                </p>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                {entry.current_streak > 0 && (
                  <span className="flex items-center gap-1 text-xs font-semibold text-amber-600">
                    <Zap className="h-3 w-3" />
                    {entry.current_streak}
                  </span>
                )}
                <span className="text-sm font-bold text-blue-600">
                  {entry.correct_answers.toLocaleString()}
                </span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {entries.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
            No leaderboard entries yet
          </div>
        )}

        <div className="flex-1 bg-gradient-to-b from-gray-50 to-transparent rounded-xl min-h-[1rem]" />
      </div>
    </div>
  );
}
