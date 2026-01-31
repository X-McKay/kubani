import { cn } from "@/lib/utils";
import { FeedFilter, SOURCE_CONFIG, EVENT_TYPE_CONFIG } from "./types";

interface FeedFiltersProps {
  activeFilters: FeedFilter;
  onFilterChange: (filters: FeedFilter) => void;
  className?: string;
}

export function FeedFilters({
  activeFilters,
  onFilterChange,
  className,
}: FeedFiltersProps) {
  const sources = Object.entries(SOURCE_CONFIG);
  const eventTypes = Object.entries(EVENT_TYPE_CONFIG);

  const toggleSource = (source: string) => {
    onFilterChange({
      ...activeFilters,
      source: activeFilters.source === source ? undefined : source,
    });
  };

  const toggleEventType = (eventType: string) => {
    onFilterChange({
      ...activeFilters,
      event_type: activeFilters.event_type === eventType ? undefined : eventType,
    });
  };

  const clearAll = () => onFilterChange({});

  const hasActiveFilters = activeFilters.source || activeFilters.event_type;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {/* All filter */}
      <button
        onClick={clearAll}
        className={cn(
          "px-2.5 py-1 rounded text-xs font-medium transition-colors",
          !hasActiveFilters
            ? "bg-primary/15 text-primary"
            : "text-muted-foreground hover:text-foreground hover:bg-secondary"
        )}
      >
        All
      </button>

      {/* Separator */}
      <span className="text-border">|</span>

      {/* Source filters */}
      {sources.map(([key, config]) => (
        <button
          key={key}
          onClick={() => toggleSource(key)}
          className={cn(
            "px-2.5 py-1 rounded text-xs font-medium font-mono transition-colors",
            activeFilters.source === key
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-secondary"
          )}
        >
          {config.shortLabel}
        </button>
      ))}

      {/* Separator */}
      <span className="text-border">|</span>

      {/* Event type filters */}
      {eventTypes.map(([key, config]) => (
        <button
          key={key}
          onClick={() => toggleEventType(key)}
          className={cn(
            "px-2.5 py-1 rounded text-xs font-medium transition-colors",
            activeFilters.event_type === key
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-secondary"
          )}
        >
          {config.label}
        </button>
      ))}
    </div>
  );
}
