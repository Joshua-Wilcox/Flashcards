import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Zap, Users } from 'lucide-react';
import { useWebSocket, isActivityEvent } from '../api/websocket';
import { api } from '../api/client';
import type { ActivityEvent, WebSocketMessage } from '../types';

interface LiveActivityProps {
  maxItems?: number;
}

export default function LiveActivity({ maxItems }: LiveActivityProps) {
  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [visibleCount, setVisibleCount] = useState(maxItems ?? 50);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (maxItems) return;
    const el = cardRef.current?.parentElement;
    if (!el) return;
    const calculate = () => {
      const available = el.clientHeight - 80;
      const count = Math.max(3, Math.floor(available / 68));
      setVisibleCount(count);
    };
    setTimeout(calculate, 50);
    const observer = new ResizeObserver(calculate);
    observer.observe(el);
    return () => observer.disconnect();
  }, [maxItems]);

  useEffect(() => {
    api.getRecentActivity(visibleCount).then((data) => {
      if (data.activities?.length) {
        setActivities(data.activities.slice(0, visibleCount));
      }
    }).catch(() => {});
  }, [visibleCount]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'activity' && isActivityEvent(message.data)) {
      setActivities((prev) => {
        const filtered = prev.filter((a) => a.user_id !== message.data.user_id);
        return [message.data as ActivityEvent, ...filtered].slice(0, visibleCount);
      });
    }
  }, [visibleCount]);

  useWebSocket(handleMessage);

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
    <div ref={cardRef} className="card p-5 w-full flex flex-col overflow-hidden">
      <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4 flex-shrink-0">
        <Users className="h-4 w-4 text-blue-600" />
        Recent Activity
      </h3>

      <div className="flex flex-col gap-2 flex-1 overflow-hidden">
        <AnimatePresence mode="popLayout">
          {activities.slice(0, visibleCount).map((activity) => (
            <motion.div
              key={`${activity.user_id}-${activity.answered_at}`}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="p-3 bg-gray-50 rounded-xl space-y-1 flex-shrink-0"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-900 truncate">
                  {activity.username}
                </span>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {activity.streak > 1 && (
                    <span className="flex items-center gap-1 text-xs font-semibold text-amber-600">
                      <Zap className="h-3 w-3" />
                      {activity.streak}
                    </span>
                  )}
                  <span className="text-xs text-gray-400">
                    {formatTime(activity.answered_at)}
                  </span>
                </div>
              </div>
              <div className="text-xs text-gray-500 truncate">
                {activity.module_name}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {activities.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
            No recent activity yet
          </div>
        )}
      </div>
    </div>
  );
}
