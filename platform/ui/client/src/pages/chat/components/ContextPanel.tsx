/**
 * Context Panel - shows what resources/tools the agent has accessed.
 */

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  Bot,
  Database,
  Wrench,
  Box,
  Layers,
  FileText,
  Clock,
} from "lucide-react";
import type { ContextPanelProps, ContextItem } from "../types";
import { formatDistanceToNow } from "date-fns";

const TYPE_ICONS: Record<
  ContextItem["type"],
  React.ComponentType<{ className?: string }>
> = {
  resource: Box,
  namespace: Layers,
  tool: Wrench,
  query: FileText,
};

export function ContextPanel({
  contextItems,
  currentAgent,
  availableTools,
}: ContextPanelProps) {
  return (
    <ScrollArea className="h-full">
      <div className="p-2 space-y-4">
        {/* Agent info */}
        <Section icon={Bot} title="Agent">
          {currentAgent ? (
            <div className="space-y-0.5 pl-4">
              <p className="text-xs font-mono text-primary">
                {currentAgent.name}
              </p>
              {currentAgent.description && (
                <p className="text-[10px] text-muted-foreground">
                  {currentAgent.description}
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground pl-4">None selected</p>
          )}
        </Section>

        {/* Accessed resources */}
        {contextItems.length > 0 && (
          <Section
            icon={Database}
            title={`Resources (${contextItems.length})`}
          >
            <div className="space-y-1 pl-4 max-h-[180px] overflow-y-auto">
              {contextItems.map((item) => {
                const Icon = TYPE_ICONS[item.type] || FileText;
                return (
                  <div
                    key={item.id}
                    className="flex items-center gap-2 py-0.5 group"
                  >
                    <Icon className="w-3 h-3 text-muted-foreground shrink-0" />
                    <span className="text-xs font-mono text-foreground/80 truncate flex-1">
                      {item.name}
                    </span>
                    <span className="text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                      {formatDistanceToNow(item.accessedAt, { addSuffix: true })}
                    </span>
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {/* Available tools */}
        {availableTools.length > 0 && (
          <Section icon={Wrench} title={`Tools (${availableTools.length})`}>
            <div className="space-y-0.5 pl-4 max-h-[140px] overflow-y-auto">
              {availableTools.slice(0, 12).map((tool, i) => (
                <p
                  key={i}
                  className="text-xs font-mono text-foreground/70 truncate"
                  title={tool.description}
                >
                  {tool.name}
                </p>
              ))}
              {availableTools.length > 12 && (
                <p className="text-[10px] text-muted-foreground">
                  +{availableTools.length - 12} more
                </p>
              )}
            </div>
          </Section>
        )}

        {/* Empty state */}
        {contextItems.length === 0 && availableTools.length === 0 && (
          <div className="text-center py-6">
            <Clock className="w-6 h-6 text-muted-foreground/30 mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">
              Context will appear here
            </p>
            <p className="text-[10px] text-muted-foreground/70">
              as you interact with the agent
            </p>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="text-[10px] font-medium mb-1.5 flex items-center gap-1.5 uppercase tracking-wide text-muted-foreground">
        <Icon className="w-3 h-3" />
        {title}
      </h4>
      {children}
    </div>
  );
}
