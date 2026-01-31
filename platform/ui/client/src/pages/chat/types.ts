/**
 * Types for Factory.ai-style chat features.
 */

/** Content type for artifacts extracted from tool results */
export type ArtifactType = "yaml" | "json" | "log" | "table" | "text" | "code";

/** Artifact represents displayable content extracted from tool results */
export interface Artifact {
  id: string;
  type: ArtifactType;
  title: string;
  content: string;
  source: {
    toolCallId: string;
    toolName: string;
    timestamp: Date;
  };
  metadata?: {
    namespace?: string;
    resourceType?: string;
    resourceName?: string;
    language?: string;
    lineCount?: number;
  };
}

/** Context item represents something the agent has accessed */
export interface ContextItem {
  id: string;
  type: "resource" | "namespace" | "tool" | "query";
  name: string;
  description?: string;
  accessedAt: Date;
  toolCallId?: string;
}

/** Code execution result for inline execution */
export interface CodeExecutionResult {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  output?: string;
  error?: string;
  executedAt: Date;
}

/** Props for artifact viewer */
export interface ArtifactViewerProps {
  artifacts: Artifact[];
  activeArtifactId: string | null;
  onArtifactSelect: (id: string) => void;
  onClose: (id: string) => void;
}

/** Props for context panel */
export interface ContextPanelProps {
  contextItems: ContextItem[];
  currentAgent?: {
    id: string;
    name: string;
    description?: string;
  } | null;
  availableTools: Array<{ name: string; description?: string }>;
}

/** Props for code block with execution */
export interface CodeBlockProps {
  code: string;
  language: string;
  onExecute?: (code: string) => Promise<CodeExecutionResult>;
}
