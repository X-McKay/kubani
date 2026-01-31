/**
 * Hook for managing artifacts extracted from tool results.
 */

import { useState, useCallback } from "react";
import type { Artifact } from "../types";
import { parseToolResultToArtifact } from "../artifact-parser";

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);

  /**
   * Add an artifact from a tool result.
   * Auto-selects the new artifact.
   */
  const addArtifact = useCallback(
    (toolCallId: string, toolName: string, result: string) => {
      const artifact = parseToolResultToArtifact(
        toolCallId,
        toolName,
        result,
        new Date()
      );

      if (artifact) {
        setArtifacts((prev) => {
          // Replace if same tool call, otherwise append
          const existingIdx = prev.findIndex(
            (a) => a.source.toolCallId === toolCallId
          );
          if (existingIdx >= 0) {
            const updated = [...prev];
            updated[existingIdx] = artifact;
            return updated;
          }
          // Keep max 10 artifacts to prevent memory issues
          const newArtifacts = [...prev, artifact];
          if (newArtifacts.length > 10) {
            return newArtifacts.slice(-10);
          }
          return newArtifacts;
        });

        // Auto-select new artifact
        setActiveArtifactId(artifact.id);
      }
    },
    []
  );

  /**
   * Close/remove an artifact.
   */
  const closeArtifact = useCallback(
    (id: string) => {
      setArtifacts((prev) => {
        const filtered = prev.filter((a) => a.id !== id);

        // If closing active artifact, select the previous one
        if (activeArtifactId === id && filtered.length > 0) {
          setActiveArtifactId(filtered[filtered.length - 1].id);
        } else if (filtered.length === 0) {
          setActiveArtifactId(null);
        }

        return filtered;
      });
    },
    [activeArtifactId]
  );

  /**
   * Clear all artifacts.
   */
  const clearArtifacts = useCallback(() => {
    setArtifacts([]);
    setActiveArtifactId(null);
  }, []);

  return {
    artifacts,
    activeArtifactId,
    setActiveArtifactId,
    addArtifact,
    closeArtifact,
    clearArtifacts,
  };
}
