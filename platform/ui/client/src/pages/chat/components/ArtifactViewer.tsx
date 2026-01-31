/**
 * Artifact Viewer - displays tool results as code, tables, logs, etc.
 * Similar to VSCode tabs with content viewer below.
 */

import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  X,
  FileJson,
  FileText,
  Table,
  Terminal,
  FileCode,
  Copy,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import type { Artifact, ArtifactViewerProps } from "../types";
import { ArtifactContent } from "./ArtifactContent";

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> =
  {
    yaml: FileCode,
    json: FileJson,
    log: Terminal,
    table: Table,
    text: FileText,
    code: FileCode,
  };

export function ArtifactViewer({
  artifacts,
  activeArtifactId,
  onArtifactSelect,
  onClose,
}: ArtifactViewerProps) {
  const activeArtifact = artifacts.find((a) => a.id === activeArtifactId);

  const handleCopy = () => {
    if (activeArtifact) {
      navigator.clipboard.writeText(activeArtifact.content);
      toast("Copied to clipboard");
    }
  };

  const handleDownload = () => {
    if (activeArtifact) {
      const extension = getFileExtension(activeArtifact.type);
      const filename = `${activeArtifact.title.replace(/[^a-z0-9]/gi, "-")}.${extension}`;
      const blob = new Blob([activeArtifact.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast(`Downloaded ${filename}`);
    }
  };

  if (artifacts.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-4">
        <FileText className="w-8 h-8 text-muted-foreground/50 mb-3" />
        <p className="text-xs text-muted-foreground">No artifacts yet</p>
        <p className="text-[10px] text-muted-foreground/70 mt-1">
          Tool results will appear here
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="h-8 border-b border-border flex items-center gap-0.5 px-1 overflow-x-auto bg-secondary/30">
        {artifacts.map((artifact) => {
          const Icon = TYPE_ICONS[artifact.type] || FileText;
          const isActive = artifact.id === activeArtifactId;

          return (
            <button
              key={artifact.id}
              onClick={() => onArtifactSelect(artifact.id)}
              className={cn(
                "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-mono",
                "hover:bg-secondary/50 transition-colors group min-w-0",
                isActive && "bg-card text-foreground",
                !isActive && "text-muted-foreground"
              )}
            >
              <Icon className="w-3 h-3 shrink-0" />
              <span className="truncate max-w-[80px]">{artifact.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onClose(artifact.id);
                }}
                className={cn(
                  "w-4 h-4 flex items-center justify-center rounded",
                  "hover:bg-muted-foreground/20 transition-colors",
                  "opacity-0 group-hover:opacity-100",
                  isActive && "opacity-100"
                )}
              >
                <X className="w-2.5 h-2.5" />
              </button>
            </button>
          );
        })}
      </div>

      {/* Content area */}
      <ScrollArea className="flex-1">
        {activeArtifact ? (
          <ArtifactContent artifact={activeArtifact} />
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-muted-foreground">Select an artifact</p>
          </div>
        )}
      </ScrollArea>

      {/* Toolbar */}
      {activeArtifact && (
        <div className="h-8 border-t border-border flex items-center justify-between px-2 bg-secondary/30">
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
            <span className="uppercase">{activeArtifact.type}</span>
            {activeArtifact.metadata?.lineCount && (
              <>
                <span className="text-border">|</span>
                <span>{activeArtifact.metadata.lineCount} lines</span>
              </>
            )}
            {activeArtifact.metadata?.namespace && (
              <>
                <span className="text-border">|</span>
                <span>ns: {activeArtifact.metadata.namespace}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleCopy}
              title="Copy content"
            >
              <Copy className="w-3 h-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleDownload}
              title="Download file"
            >
              <Download className="w-3 h-3" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function getFileExtension(type: Artifact["type"]): string {
  switch (type) {
    case "yaml":
      return "yaml";
    case "json":
      return "json";
    case "log":
      return "log";
    case "table":
      return "txt";
    case "code":
      return "txt";
    default:
      return "txt";
  }
}
