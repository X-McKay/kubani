/**
 * Content renderers for different artifact types.
 * Displays YAML, JSON, logs, tables, and text with appropriate formatting.
 */

import { cn } from "@/lib/utils";
import type { Artifact } from "../types";

interface ArtifactContentProps {
  artifact: Artifact;
}

export function ArtifactContent({ artifact }: ArtifactContentProps) {
  switch (artifact.type) {
    case "yaml":
    case "json":
    case "code":
      return <CodeContent content={artifact.content} type={artifact.type} />;

    case "log":
      return <LogContent content={artifact.content} />;

    case "table":
      return <TableContent content={artifact.content} />;

    default:
      return <TextContent content={artifact.content} />;
  }
}

/**
 * Code content with line numbers and syntax-appropriate styling.
 */
function CodeContent({
  content,
  type,
}: {
  content: string;
  type: "yaml" | "json" | "code";
}) {
  const lines = content.split("\n");

  return (
    <div className="relative">
      <pre className="p-0 overflow-x-auto font-mono text-xs bg-black/20">
        <code>
          {lines.map((line, i) => (
            <div key={i} className="flex hover:bg-secondary/30">
              <span className="w-10 px-2 py-0.5 text-right text-muted-foreground/50 select-none border-r border-border/30 shrink-0">
                {i + 1}
              </span>
              <span className="px-3 py-0.5 whitespace-pre">
                <HighlightedLine line={line} type={type} />
              </span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}

/**
 * Simple syntax highlighting for YAML/JSON lines.
 */
function HighlightedLine({
  line,
  type,
}: {
  line: string;
  type: "yaml" | "json" | "code";
}) {
  if (type === "yaml") {
    // Highlight YAML keys, strings, and special values
    const parts: React.ReactNode[] = [];
    let remaining = line;
    let key = 0;

    // Match key: value patterns
    const keyMatch = remaining.match(/^(\s*)([a-zA-Z_][a-zA-Z0-9_-]*)(:)/);
    if (keyMatch) {
      parts.push(
        <span key={key++} className="text-foreground/50">
          {keyMatch[1]}
        </span>
      );
      parts.push(
        <span key={key++} className="text-primary">
          {keyMatch[2]}
        </span>
      );
      parts.push(
        <span key={key++} className="text-muted-foreground">
          {keyMatch[3]}
        </span>
      );
      remaining = remaining.slice(keyMatch[0].length);

      // Check for value
      if (remaining.trim()) {
        const value = remaining;
        // Strings in quotes
        if (/^\s*["']/.test(value)) {
          parts.push(
            <span key={key++} className="text-success">
              {value}
            </span>
          );
        }
        // Numbers
        else if (/^\s*-?\d+(\.\d+)?$/.test(value.trim())) {
          parts.push(
            <span key={key++} className="text-info">
              {value}
            </span>
          );
        }
        // Booleans
        else if (/^\s*(true|false)$/i.test(value.trim())) {
          parts.push(
            <span key={key++} className="text-warning">
              {value}
            </span>
          );
        }
        // null
        else if (/^\s*null$/i.test(value.trim())) {
          parts.push(
            <span key={key++} className="text-muted-foreground">
              {value}
            </span>
          );
        } else {
          parts.push(
            <span key={key++} className="text-foreground/80">
              {value}
            </span>
          );
        }
        return <>{parts}</>;
      }
      return <>{parts}</>;
    }

    // List items
    if (/^\s*-\s/.test(line)) {
      const match = line.match(/^(\s*)(-\s)(.*)/);
      if (match) {
        return (
          <>
            <span className="text-foreground/50">{match[1]}</span>
            <span className="text-muted-foreground">{match[2]}</span>
            <span className="text-foreground/80">{match[3]}</span>
          </>
        );
      }
    }

    // Comments
    if (/^\s*#/.test(line)) {
      return <span className="text-muted-foreground/60">{line}</span>;
    }

    return <span className="text-foreground/80">{line}</span>;
  }

  if (type === "json") {
    // Simple JSON highlighting
    // Keys
    const keyMatch = line.match(/^(\s*)("[\w_-]+")(\s*:\s*)/);
    if (keyMatch) {
      const rest = line.slice(keyMatch[0].length);
      return (
        <>
          <span className="text-foreground/50">{keyMatch[1]}</span>
          <span className="text-primary">{keyMatch[2]}</span>
          <span className="text-muted-foreground">{keyMatch[3]}</span>
          <HighlightJsonValue value={rest} />
        </>
      );
    }

    return <HighlightJsonValue value={line} />;
  }

  return <span className="text-foreground/80">{line}</span>;
}

function HighlightJsonValue({ value }: { value: string }) {
  const trimmed = value.trim();

  // String
  if (/^".*"[,\s]*$/.test(trimmed)) {
    return <span className="text-success">{value}</span>;
  }

  // Number
  if (/^-?\d+(\.\d+)?[,\s]*$/.test(trimmed)) {
    return <span className="text-info">{value}</span>;
  }

  // Boolean
  if (/^(true|false)[,\s]*$/i.test(trimmed)) {
    return <span className="text-warning">{value}</span>;
  }

  // null
  if (/^null[,\s]*$/i.test(trimmed)) {
    return <span className="text-muted-foreground">{value}</span>;
  }

  return <span className="text-foreground/80">{value}</span>;
}

/**
 * Log content with level-based coloring.
 */
function LogContent({ content }: { content: string }) {
  const lines = content.split("\n");

  return (
    <div className="p-2 font-mono text-xs space-y-0">
      {lines.map((line, i) => {
        const level = detectLogLevel(line);
        return (
          <div
            key={i}
            className={cn(
              "flex gap-2 py-0.5 hover:bg-secondary/30",
              level === "error" && "text-destructive",
              level === "warn" && "text-warning",
              level === "info" && "text-info",
              level === "debug" && "text-muted-foreground",
              !level && "text-foreground/80"
            )}
          >
            <span className="w-8 text-right text-muted-foreground/50 select-none shrink-0">
              {i + 1}
            </span>
            <span className="whitespace-pre-wrap break-all">{line}</span>
          </div>
        );
      })}
    </div>
  );
}

function detectLogLevel(
  line: string
): "error" | "warn" | "info" | "debug" | null {
  const lower = line.toLowerCase();

  if (
    lower.includes("error") ||
    lower.includes("fatal") ||
    lower.includes("panic")
  ) {
    return "error";
  }
  if (lower.includes("warn") || lower.includes("warning")) {
    return "warn";
  }
  if (lower.includes("info")) {
    return "info";
  }
  if (lower.includes("debug") || lower.includes("trace")) {
    return "debug";
  }

  return null;
}

/**
 * Table content parsed from kubectl output.
 */
function TableContent({ content }: { content: string }) {
  const lines = content.trim().split("\n");
  if (lines.length < 2) {
    return <TextContent content={content} />;
  }

  // Parse header row - kubectl uses multiple spaces as separators
  const headerLine = lines[0];
  const headers = headerLine.split(/\s{2,}/).map((h) => h.trim());

  // Parse data rows
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(/\s{2,}/).map((c) => c.trim());
    // Pad cells to match header count
    while (cells.length < headers.length) {
      cells.push("");
    }
    return cells;
  });

  return (
    <div className="overflow-x-auto p-2">
      <table className="w-full text-xs font-mono border-collapse">
        <thead>
          <tr className="border-b border-border">
            {headers.map((h, i) => (
              <th
                key={i}
                className="text-left p-2 text-muted-foreground uppercase text-[10px] font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-border/30 hover:bg-secondary/30"
            >
              {row.map((cell, j) => (
                <td key={j} className={cn("p-2", getCellStyle(headers[j], cell))}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Get styling for table cells based on column name and value.
 */
function getCellStyle(header: string, value: string): string {
  const headerLower = header?.toLowerCase() || "";
  const valueLower = value.toLowerCase();

  // Status column
  if (headerLower === "status") {
    if (valueLower === "running" || valueLower === "ready") {
      return "text-success";
    }
    if (
      valueLower === "pending" ||
      valueLower === "containercreating" ||
      valueLower === "terminating"
    ) {
      return "text-warning";
    }
    if (
      valueLower.includes("error") ||
      valueLower.includes("crash") ||
      valueLower === "failed"
    ) {
      return "text-destructive";
    }
  }

  // Ready column (e.g., "1/1", "0/1")
  if (headerLower === "ready") {
    const parts = value.split("/");
    if (parts.length === 2 && parts[0] === parts[1]) {
      return "text-success";
    }
    if (parts.length === 2 && parts[0] !== parts[1]) {
      return "text-warning";
    }
  }

  // Restarts column
  if (headerLower === "restarts") {
    const num = parseInt(value, 10);
    if (num > 5) return "text-destructive";
    if (num > 0) return "text-warning";
  }

  // Name column - primary color
  if (headerLower === "name") {
    return "text-primary";
  }

  return "text-foreground/80";
}

/**
 * Plain text content.
 */
function TextContent({ content }: { content: string }) {
  return (
    <div className="p-4">
      <pre className="text-xs font-mono text-foreground/80 whitespace-pre-wrap break-words">
        {content}
      </pre>
    </div>
  );
}
