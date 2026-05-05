import { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Zap, Users } from 'lucide-react';
import { useWebSocket, isActivityEvent } from '../api/websocket';
import { api } from '../api/client';
import type { ActivityEvent, WebSocketMessage } from '../types';

interface LiveActivityProps {
  maxItems?: number;
}

export default function LiveActivity({ maxItems = 5 }: LiveActivityProps) {
  const [activities, setActivities] = useState<ActivityEvent[]>([]);

  useEffect(() => {
    api.getRecentActivity().then((data) => {
      if (data.activities?.length) {
        setActivities(data.activities.slice(0, maxItems));
      }
    }).catch(() => {});
  }, [maxItems]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'activity' && isActivityEvent(message.data)) {
      setActivities((prev) => {
        const filtered = prev.filter((a) => a.user_id !== message.data.user_id);
        return [message.data as ActivityEvent, ...filtered].slice(0, maxItems);
      });
    }
  }, [maxItems]);

  const { isConnected } = useWebSocket(handleMessage);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
          <Users className="h-4 w-4" />
          Live Activity
        </h3>
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

      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {activities.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-4">
              No recent activity
            </p>
          ) : (
            activities.map((activity) => (
              <motion.div
                key={`${activity.user_id}-${activity.answered_at}`}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="p-2.5 bg-slate-900/50 rounded-lg space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-200">
                    {activity.username}
                  </span>
                  <div className="flex items-center gap-2">
                    {activity.streak > 1 && (
                      <span className="flex items-center gap-1 text-xs text-yellow-400">
                        <Zap className="h-3 w-3" />
                        {activity.streak}
                      </span>
                    )}
                    <span className="text-xs text-slate-500">
                      {formatTime(activity.answered_at)}
                    </span>
                  </div>
                </div>
                <div className="text-xs text-slate-400">
                  {activity.module_name}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
