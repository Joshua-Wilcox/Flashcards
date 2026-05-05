import { useEffect, useRef, useCallback, useState } from 'react';
import type { WebSocketMessage, ActivityEvent, LeaderboardUpdate } from '../types';

type MessageHandler = (message: WebSocketMessage) => void;

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number>();
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const lines = event.data.split('\n');
        for (const line of lines) {
          if (line.trim()) {
            const message = JSON.parse(line) as WebSocketMessage;
            onMessage(message);
          }
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      wsRef.current = null;

      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    wsRef.current = ws;
  }, [onMessage]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { isConnected };
}

export function isActivityEvent(data: unknown): data is ActivityEvent {
  return (
    typeof data === 'object' &&
    data !== null &&
    'username' in data &&
    'module_name' in data &&
    'streak' in data
  );
}

export function isLeaderboardUpdate(data: unknown): data is LeaderboardUpdate {
  return (
    typeof data === 'object' &&
    data !== null &&
    'user_id' in data &&
    'correct_answers' in data &&
    'current_streak' in data
  );
}
