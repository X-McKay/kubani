/**
 * Executable code block with run/copy buttons.
 * Displays inline execution results.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Play,
  Copy,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { toast } from "sonner";
import type { CodeBlockProps, CodeExecutionResult } from "../types";

/** Languages that can be executed */
const EXECUTABLE_LANGUAGES = ["bash", "sh", "kubectl", "shell"];

export function CodeBlock({ code, language, onExecute }: CodeBlockProps) {
  const [execution, setExecution] = useState<CodeExecutionResult | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);

  const isExecutable =
    EXECUTABLE_LANGUAGES.includes(language.toLowerCase()) && onExecute;
  const lines = code.split("\n");

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    toast("Copied to clipboard");
  };

  const handleExecute = async () => {
    if (!onExecute) return;

    setExecution({
      id: Date.now().toString(),
      status: "running",
      executedAt: new Date(),
    });

    try {
      const result = await onExecute(code);
      setExecution(result);
    } catch (error) {
      setExecution({
        id: Date.now().toString(),
        status: "failed",
        error: error instanceof Error ? error.message : "Execution failed",
        executedAt: new Date(),
      });
    }
  };

  return (
    <div className="rounded border border-border my-2 overflow-hidden bg-black/20">
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 bg-secondary/30 border-b border-border">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-0.5 hover:bg-secondary rounded"
          >
            {isExpanded ? (
              <ChevronDown className="w-3 h-3 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-3 h-3 text-muted-foreground" />
            )}
          </button>
          <span className="text-[10px] font-mono text-muted-foreground uppercase">
            {language}
          </span>
          {execution?.status === "running" && (
            <Loader2 className="w-3 h-3 animate-spin text-primary" />
          )}
          {execution?.status === "completed" && (
            <CheckCircle2 className="w-3 h-3 text-success" />
          )}
          {execution?.status === "failed" && (
            <AlertCircle className="w-3 h-3 text-destructive" />
          )}
        </div>
        <div className="flex items-center gap-1">
          {isExecutable && (
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5"
              onClick={handleExecute}
              disabled={execution?.status === "running"}
              title="Run this code"
            >
              <Play className="w-3 h-3" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={handleCopy}
            title="Copy code"
          >
            <Copy className="w-3 h-3" />
          </Button>
        </div>
      </div>

      {/* Code content */}
      {isExpanded && (
        <>
          <pre className="p-0 overflow-x-auto font-mono text-xs">
            <code>
              {lines.map((line, i) => (
                <div key={i} className="flex hover:bg-secondary/20">
                  <span className="w-8 px-2 py-0.5 text-right text-muted-foreground/40 select-none border-r border-border/20 shrink-0">
                    {i + 1}
                  </span>
                  <span className="px-3 py-0.5 whitespace-pre text-foreground/80">
                    {line}
                  </span>
                </div>
              ))}
            </code>
          </pre>

          {/* Execution result */}
          {execution && execution.status !== "running" && (
            <div
              className={cn(
                "border-t border-border p-2",
                execution.status === "completed" && "bg-success/5",
                execution.status === "failed" && "bg-destructive/5"
              )}
            >
              <div className="flex items-center gap-2 mb-1">
                {execution.status === "completed" && (
                  <CheckCircle2 className="w-3 h-3 text-success" />
                )}
                {execution.status === "failed" && (
                  <AlertCircle className="w-3 h-3 text-destructive" />
                )}
                <span className="text-[10px] font-mono uppercase text-muted-foreground">
                  {execution.status}
                </span>
              </div>
              {execution.output && (
                <pre className="text-xs font-mono whitespace-pre-wrap text-foreground/80 max-h-[150px] overflow-y-auto">
                  {execution.output}
                </pre>
              )}
              {execution.error && (
                <pre className="text-xs font-mono text-destructive max-h-[100px] overflow-y-auto">
                  {execution.error}
                </pre>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
