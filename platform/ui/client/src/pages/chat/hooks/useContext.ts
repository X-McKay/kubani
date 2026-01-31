/**
 * Hook for tracking context - resources/tools the agent has accessed.
 */

import { useState, useCallback } from "react";
import type { ContextItem } from "../types";

export function useContextTracking() {
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);

  /**
   * Add a context item (resource, namespace, or tool access).
   * Deduplicates by type + name.
   */
  const addContextItem = useCallback((item: Omit<ContextItem, "id">) => {
    setContextItems((prev) => {
      // Check for existing item with same type and name
      const existingIdx = prev.findIndex(
        (i) => i.type === item.type && i.name === item.name
      );

      if (existingIdx >= 0) {
        // Update existing item with new access time
        const updated = [...prev];
        updated[existingIdx] = {
          ...updated[existingIdx],
          accessedAt: item.accessedAt,
          toolCallId: item.toolCallId,
        };
        return updated;
      }

      // Add new item
      const newItem: ContextItem = {
        ...item,
        id: `ctx-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      };

      // Keep max 20 context items
      const newItems = [...prev, newItem];
      if (newItems.length > 20) {
        return newItems.slice(-20);
      }
      return newItems;
    });
  }, []);

  /**
   * Remove a context item.
   */
  const removeContextItem = useCallback((id: string) => {
    setContextItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  /**
   * Clear all context items.
   */
  const clearContext = useCallback(() => {
    setContextItems([]);
  }, []);

  /**
   * Get context items sorted by most recent access.
   */
  const sortedContextItems = [...contextItems].sort(
    (a, b) => b.accessedAt.getTime() - a.accessedAt.getTime()
  );

  return {
    contextItems: sortedContextItems,
    addContextItem,
    removeContextItem,
    clearContext,
  };
}
