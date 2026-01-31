import { useState } from "react";
import { cn } from "@/lib/utils";
import { ActivityEvent, EVENT_TYPE_CONFIG, SOURCE_CONFIG } from "./types";
import { RichContent } from "./RichContent";
import { InlineApprovalActions } from "./InlineApprovalActions";
import { formatDistanceToNow, format } from "date-fns";
import {
  FileText,
  Bot,
  AlertTriangle,
  ShieldCheck,
  Workflow,
  Brain,
  Settings,
  Activity,
  ChevronRight,
  ChevronDown,
  Circle,
  CheckCircle2,
} from "lucide-react";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  FileText,
  Bot,
  AlertTriangle,
  ShieldCheck,
  Workflow,
  Brain,
  Settings,
  Activity,
};

interface FeedItemProps {
  event: ActivityEvent;
  onClick: () => void;
  className?: string;
}

export function FeedItem({ event, onClick, className }: FeedItemProps) {
  const [expanded, setExpanded] = useState(false);
  const typeConfig =
    EVENT_TYPE_CONFIG[event.event_type] || EVENT_TYPE_CONFIG.system;
  const sourceConfig = SOURCE_CONFIG[event.source] || {
    label: event.source,
    shortLabel: event.source,
  };
  const Icon = ICONS[typeConfig.icon] || Activity;

  const timeAgo = formatDistanceToNow(new Date(event.created_at), {
    addSuffix: false,
  });
  const fullTime = format(new Date(event.created_at), "h:mm:ss a");

  // Determine status color based on event type and severity
  const getStatusColor = () => {
    if (event.event_type === "approval") return "text-warning";
    if (event.severity === "error") return "text-error";
    if (event.severity === "success") return "text-success";
    return "text-primary";
  };

  const hasContent = event.content && event.content.length > 0;
  const hasMetadata =
    event.metadata && Object.keys(event.metadata).length > 0;
  const isExpandable = hasContent || hasMetadata;

  const handleExpand = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isExpandable) {
      setExpanded(!expanded);
    }
  };

  return (
    <div
      className={cn(
        "border-b border-border last:border-b-0",
        !event.read && "bg-primary/5",
        className
      )}
    >
      {/* Main row - always visible */}
      <div
        className={cn(
          "flex items-start gap-3 px-4 py-3 cursor-pointer",
          "hover:bg-secondary/50 transition-colors duration-100"
        )}
        onClick={isExpandable ? handleExpand : onClick}
      >
        {/* Expand/collapse chevron or status indicator */}
        <div className="flex items-center justify-center w-5 h-5 mt-0.5">
          {isExpandable ? (
            expanded ? (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            )
          ) : event.read ? (
            <CheckCircle2 className="w-4 h-4 text-muted-foreground/50" />
          ) : (
            <Circle className="w-3 h-3 text-primary fill-primary" />
          )}
        </div>

        {/* Status badge */}
        <div
          className={cn(
            "px-2 py-0.5 rounded text-xs font-medium uppercase tracking-wide",
            "bg-primary/15",
            getStatusColor()
          )}
        >
          {typeConfig.label.toUpperCase()}
        </div>

        {/* Timestamp */}
        <span className="text-xs text-muted-foreground font-mono">
          {fullTime}
        </span>

        {/* Event ID / Description */}
        <div className="flex-1 min-w-0">
          <span className="text-sm text-foreground">
            Event #{event.id.slice(0, 8)}
          </span>
          <span className="text-sm text-muted-foreground mx-2">—</span>
          <span className="text-sm text-muted-foreground">
            {sourceConfig.shortLabel}
          </span>
          {event.metadata?.seq !== undefined && (
            <>
              <span className="text-sm text-muted-foreground mx-1">—</span>
              <span className="text-sm text-muted-foreground">
                seq {String(event.metadata.seq)}
              </span>
            </>
          )}
        </div>

        {/* Relative time */}
        <span className="text-xs text-muted-foreground">{timeAgo}</span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="pl-12 pr-4 pb-4">
          {/* Title if different from generic */}
          {event.title && (
            <h4 className="text-sm font-medium text-foreground mb-2">
              {event.title}
            </h4>
          )}

          {/* Rich content */}
          {hasContent && (
            <div className="bg-background rounded border border-border p-3 mb-3">
              <RichContent content={event.content} />
            </div>
          )}

          {/* Metadata as JSON */}
          {hasMetadata && (
            <div className="bg-background rounded border border-border p-3">
              <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(event.metadata, null, 2)}
              </pre>
            </div>
          )}

          {/* Inline approval actions */}
          {event.event_type === "approval" && (
            <div className="mt-3">
              <InlineApprovalActions approvalId={event.id} expanded />
            </div>
          )}

          {/* View full details link */}
          <button
            onClick={onClick}
            className="mt-3 text-xs text-primary hover:underline"
          >
            View full details →
          </button>
        </div>
      )}
    </div>
  );
}
