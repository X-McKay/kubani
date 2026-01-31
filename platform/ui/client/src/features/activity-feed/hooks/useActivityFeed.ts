import { useState, useEffect, useCallback, useRef } from "react";
import { ActivityEvent, FeedFilter } from "../types";

interface UseActivityFeedOptions {
  filters?: FeedFilter;
  pageSize?: number;
}

interface UseActivityFeedResult {
  events: ActivityEvent[];
  isLoading: boolean;
  hasMore: boolean;
  unreadCount: number;
  loadMore: () => void;
  markAsRead: (ids: string[]) => void;
  refresh: () => void;
}

export function useActivityFeed(
  options: UseActivityFeedOptions = {}
): UseActivityFeedResult {
  const { filters, pageSize = 50 } = options;
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const offsetRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );

  // Initial load from REST API
  const loadEvents = useCallback(
    async (offset: number = 0) => {
      setIsLoading(true);
      try {
        const params = new URLSearchParams();
        if (filters?.source) params.set("source", filters.source);
        if (filters?.event_type) params.set("event_type", filters.event_type);
        params.set("limit", String(pageSize));
        params.set("offset", String(offset));

        const response = await fetch(`/api/activity?${params}`);
        const data: ActivityEvent[] = await response.json();

        if (offset === 0) {
          setEvents(data);
        } else {
          setEvents((prev) => [...prev, ...data]);
        }
        setHasMore(data.length === pageSize);
        offsetRef.current = offset + data.length;
      } catch (error) {
        console.error("Failed to load activity events:", error);
      } finally {
        setIsLoading(false);
      }
    },
    [filters, pageSize]
  );

  // Load unread count
  const loadUnreadCount = useCallback(async () => {
    try {
      const response = await fetch("/api/activity/unread-count");
      const data = await response.json();
      setUnreadCount(data.count);
    } catch {
      // Ignore errors
    }
  }, []);

  // WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "activity_item") {
          // Apply client-side filter
          const matchesFilter =
            (!filters?.source || data.source === filters.source) &&
            (!filters?.event_type || data.event_type === filters.event_type);

          if (matchesFilter) {
            setEvents((prev) => [
              {
                id: data.id,
                source: data.source,
                event_type: data.event_type,
                title: data.title,
                content: data.content,
                metadata: data.metadata,
                severity: "info",
                created_at: data.timestamp,
                read: false,
              },
              ...prev,
            ]);
          }

          setUnreadCount((prev) => prev + 1);
        }

        if (data.type === "new_approval") {
          // Also add approvals to the feed
          const matchesFilter =
            (!filters?.source || data.source === filters.source) &&
            (!filters?.event_type || filters.event_type === "approval");

          if (matchesFilter) {
            setEvents((prev) => [
              {
                id: data.id,
                source: data.source,
                event_type: "approval",
                title: data.title,
                content: data.summary,
                metadata: { approval_type: data.approval_type },
                severity: "warning",
                created_at: data.timestamp,
                read: false,
              },
              ...prev,
            ]);
          }
          setUnreadCount((prev) => prev + 1);
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      // Auto-reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket();
      }, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [filters]);

  // WebSocket effect
  useEffect(() => {
    connectWebSocket();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWebSocket]);

  // Initial data load
  useEffect(() => {
    loadEvents(0);
    loadUnreadCount();
  }, [loadEvents, loadUnreadCount]);

  const loadMore = useCallback(() => {
    loadEvents(offsetRef.current);
  }, [loadEvents]);

  const markAsRead = useCallback(async (ids: string[]) => {
    try {
      await fetch("/api/activity/mark-read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      setEvents((prev) =>
        prev.map((e) => (ids.includes(e.id) ? { ...e, read: true } : e))
      );
      setUnreadCount((prev) => Math.max(0, prev - ids.length));
    } catch {
      // Ignore errors
    }
  }, []);

  const refresh = useCallback(() => {
    offsetRef.current = 0;
    loadEvents(0);
    loadUnreadCount();
  }, [loadEvents, loadUnreadCount]);

  return {
    events,
    isLoading,
    hasMore,
    unreadCount,
    loadMore,
    markAsRead,
    refresh,
  };
}
