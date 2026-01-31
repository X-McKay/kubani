/**
 * Parse tool results into displayable artifacts.
 * Detects content type (YAML, JSON, logs, tables) from content patterns.
 */

import type { Artifact, ArtifactType } from "./types";

/**
 * Parse a tool result into a displayable artifact.
 * Returns null if the content shouldn't be displayed as an artifact.
 */
export function parseToolResultToArtifact(
  toolCallId: string,
  toolName: string,
  result: string,
  timestamp: Date
): Artifact | null {
  // Skip empty or very short results
  if (!result || result.trim().length < 10) {
    return null;
  }

  // Skip simple status messages
  if (isSimpleStatusMessage(result)) {
    return null;
  }

  const type = detectContentType(result, toolName);
  const title = generateArtifactTitle(toolName, result, type);
  const metadata = extractMetadata(toolName, result);

  return {
    id: `artifact-${toolCallId}`,
    type,
    title,
    content: result,
    source: { toolCallId, toolName, timestamp },
    metadata: {
      ...metadata,
      lineCount: result.split("\n").length,
    },
  };
}

/**
 * Detect the content type from the result text.
 */
function detectContentType(content: string, toolName: string): ArtifactType {
  const trimmed = content.trim();

  // YAML detection - Kubernetes resources
  if (
    trimmed.startsWith("apiVersion:") ||
    trimmed.startsWith("kind:") ||
    trimmed.match(/^---\s*$/m)
  ) {
    return "yaml";
  }

  // JSON detection
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      JSON.parse(trimmed);
      return "json";
    } catch {
      // Not valid JSON, continue detection
    }
  }

  // Log detection - timestamps, log levels
  if (
    trimmed.match(/\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}/) ||
    trimmed.match(/level=(info|debug|warn|error|warning)/i) ||
    trimmed.match(/\[(INFO|DEBUG|WARN|ERROR|WARNING)\]/i)
  ) {
    return "log";
  }

  // Table detection - kubectl output format
  // Multiple columns with consistent spacing, header row
  const lines = trimmed.split("\n").filter((l) => l.trim());
  if (lines.length > 1) {
    const firstLineColumns = lines[0].split(/\s{2,}/).length;
    // kubectl tables typically have 3+ columns
    if (firstLineColumns >= 3) {
      // Check if subsequent lines have similar structure
      const secondLineColumns = lines[1]?.split(/\s{2,}/).length || 0;
      if (Math.abs(firstLineColumns - secondLineColumns) <= 1) {
        return "table";
      }
    }
  }

  // Tool-specific detection
  if (toolName.includes("log") || toolName.includes("events")) {
    return "log";
  }

  if (toolName.includes("get") || toolName.includes("describe")) {
    // Single resource get often returns YAML-like output
    if (trimmed.includes(":") && trimmed.split("\n").length > 5) {
      return "yaml";
    }
  }

  return "text";
}

/**
 * Generate a meaningful title for the artifact.
 */
function generateArtifactTitle(
  toolName: string,
  content: string,
  type: ArtifactType
): string {
  // Try to extract resource name from content
  const nameMatch = content.match(/name:\s*["']?([^"'\n\s]+)["']?/i);
  const namespaceMatch = content.match(/namespace:\s*["']?([^"'\n\s]+)["']?/i);
  const kindMatch = content.match(/kind:\s*["']?([^"'\n\s]+)["']?/i);

  // Parse tool name for resource type
  const toolParts = toolName.replace(/^mcp__[^_]+__/, "").split("_");
  const resourceType = toolParts[0]; // e.g., "pods", "nodes", "resources"
  const action = toolParts[1]; // e.g., "list", "get", "log"

  // Build title based on what we found
  if (kindMatch && nameMatch) {
    const ns = namespaceMatch ? `${namespaceMatch[1]}/` : "";
    return `${kindMatch[1]}: ${ns}${nameMatch[1]}`;
  }

  if (nameMatch) {
    const ns = namespaceMatch ? `${namespaceMatch[1]}/` : "";
    return `${resourceType}: ${ns}${nameMatch[1]}`;
  }

  // For list operations, show the type
  if (action === "list") {
    return `${resourceType} list`;
  }

  // For logs
  if (action === "log" || type === "log") {
    return `${resourceType} logs`;
  }

  // Fallback
  return `${toolParts.join(" ")}`;
}

/**
 * Extract metadata from tool result.
 */
function extractMetadata(
  toolName: string,
  content: string
): Artifact["metadata"] {
  const metadata: Artifact["metadata"] = {};

  // Extract namespace
  const nsMatch = content.match(/namespace:\s*["']?([^"'\n\s]+)["']?/i);
  if (nsMatch) {
    metadata.namespace = nsMatch[1];
  }

  // Extract resource name
  const nameMatch = content.match(/name:\s*["']?([^"'\n\s]+)["']?/i);
  if (nameMatch) {
    metadata.resourceName = nameMatch[1];
  }

  // Extract kind/resource type
  const kindMatch = content.match(/kind:\s*["']?([^"'\n\s]+)["']?/i);
  if (kindMatch) {
    metadata.resourceType = kindMatch[1];
  }

  return metadata;
}

/**
 * Check if result is a simple status message that shouldn't be an artifact.
 */
function isSimpleStatusMessage(content: string): boolean {
  const trimmed = content.trim().toLowerCase();

  // Common simple responses
  const simplePatterns = [
    /^(ok|success|done|completed)\.?$/i,
    /^(error|failed|failure):/i,
    /^pod .+ deleted$/i,
    /^(created|updated|deleted)$/i,
    /^no resources found/i,
  ];

  return simplePatterns.some((p) => p.test(trimmed));
}

/**
 * Extract resource name from tool name and result for context tracking.
 */
export function extractResourceName(toolName: string, result: string): string {
  // Try to get name from content
  const nameMatch = result.match(/name:\s*["']?([^"'\n\s]+)["']?/i);
  const namespaceMatch = result.match(/namespace:\s*["']?([^"'\n\s]+)["']?/i);

  if (nameMatch) {
    const ns = namespaceMatch ? `${namespaceMatch[1]}/` : "";
    return `${ns}${nameMatch[1]}`;
  }

  // Parse from tool name
  const toolParts = toolName.replace(/^mcp__[^_]+__/, "").split("_");
  return toolParts.join(" ");
}
