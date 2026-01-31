import { useState, useCallback } from "react";
import { useActivityFeed } from "./hooks/useActivityFeed";
import { FeedItem } from "./FeedItem";
import { FeedItemDetail } from "./FeedItemDetail";
import { FeedFilters } from "./FeedFilters";
import { ActivityEvent, FeedFilter } from "./types";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { RefreshCw, Loader2 } from "lucide-react";

export function ActivityFeed() {
  const [filters, setFilters] = useState<FeedFilter>({});
  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(
    null
  );
  const [detailOpen, setDetailOpen] = useState(false);

  const {
    events,
    isLoading,
    hasMore,
    unreadCount,
    loadMore,
    markAsRead,
    refresh,
  } = useActivityFeed({ filters });

  const handleItemClick = useCallback(
    (event: ActivityEvent) => {
      setSelectedEvent(event);
      setDetailOpen(true);
      if (!event.read) {
        markAsRead([event.id]);
      }
    },
    [markAsRead]
  );

  return (
    <div className="h-full flex flex-col">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center gap-4">
          <h1 className="text-sm font-semibold text-foreground uppercase tracking-wide">
            Events
          </h1>
          {unreadCount > 0 && (
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-primary/15 text-primary">
              {unreadCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={refresh}
            disabled={isLoading}
            className="h-8 px-3 text-xs font-mono"
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            <span className="ml-2">Refresh</span>
          </Button>
        </div>
      </div>

      {/* Filters bar */}
      <div className="px-4 py-2 border-b border-border bg-card/50">
        <FeedFilters activeFilters={filters} onFilterChange={setFilters} />
      </div>

      {/* Events list */}
      <div className="flex-1 overflow-y-auto bg-card">
        {isLoading && events.length === 0 ? (
          // Loading state
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">
              Loading events...
            </span>
          </div>
        ) : events.length === 0 ? (
          // Empty state
          <div className="flex flex-col items-center justify-center h-64 text-center px-4">
            <p className="text-muted-foreground text-sm">No events found.</p>
            <p className="text-muted-foreground text-xs mt-1">
              Events from syndicates and agents will appear here in real-time.
            </p>
          </div>
        ) : (
          <>
            {/* Event list */}
            <div className="divide-y divide-border">
              {events.map((event) => (
                <FeedItem
                  key={event.id}
                  event={event}
                  onClick={() => handleItemClick(event)}
                />
              ))}
            </div>

            {/* Load more */}
            {hasMore && (
              <div className="flex justify-center py-4 border-t border-border">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={loadMore}
                  disabled={isLoading}
                  className="text-xs font-mono"
                >
                  {isLoading ? "Loading..." : "Load more events"}
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Detail side panel */}
      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent
          side="right"
          className="w-full sm:w-[480px] p-0 bg-card border-l border-border"
        >
          {selectedEvent && (
            <FeedItemDetail
              event={selectedEvent}
              onClose={() => setDetailOpen(false)}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
