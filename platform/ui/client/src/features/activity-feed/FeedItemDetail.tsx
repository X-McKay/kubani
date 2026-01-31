import { ActivityEvent, EVENT_TYPE_CONFIG, SOURCE_CONFIG } from "./types";
import { RichContent } from "./RichContent";
import { InlineApprovalActions } from "./InlineApprovalActions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { X } from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";

interface FeedItemDetailProps {
  event: ActivityEvent;
  onClose: () => void;
}

export function FeedItemDetail({ event, onClose }: FeedItemDetailProps) {
  const typeConfig =
    EVENT_TYPE_CONFIG[event.event_type] || EVENT_TYPE_CONFIG.system;
  const sourceConfig = SOURCE_CONFIG[event.source] || { label: event.source };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-border-subtle">
        <div className="flex-1 min-w-0 pr-4">
          <Badge variant="secondary" className="mb-2">
            {typeConfig.label}
          </Badge>
          <h2 className="text-heading-3 break-words">{event.title}</h2>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="shrink-0"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Metadata */}
      <div className="px-4 py-3 border-b border-border-subtle text-caption flex flex-wrap gap-x-4 gap-y-1">
        <span>
          Source: <strong className="text-foreground">{sourceConfig.label}</strong>
        </span>
        <span>
          Time:{" "}
          <strong className="text-foreground">
            {format(new Date(event.created_at), "PPp")}
          </strong>
        </span>
        <span className="text-muted-foreground">
          ({formatDistanceToNow(new Date(event.created_at), { addSuffix: true })})
        </span>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 p-4">
        {event.content ? (
          <RichContent content={event.content} />
        ) : (
          <p className="text-muted-foreground text-sm">No content available.</p>
        )}

        {/* Full metadata */}
        {event.metadata && Object.keys(event.metadata).length > 0 && (
          <div className="mt-6">
            <h4 className="text-label mb-2">Metadata</h4>
            <div className="surface-inset p-3 rounded-lg">
              <pre className="text-mono text-xs whitespace-pre-wrap text-muted-foreground">
                {JSON.stringify(event.metadata, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Actions footer */}
      {event.event_type === "approval" && (
        <div className="p-4 border-t border-border-subtle">
          <InlineApprovalActions approvalId={event.id} expanded />
        </div>
      )}
    </div>
  );
}
