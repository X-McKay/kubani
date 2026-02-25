import { useState, useRef } from "react";
import { Monitor, MonitorOff, Maximize2, Minimize2 } from "lucide-react";

interface ScreenViewerProps {
  novncUrl: string | null;
}

export function ScreenViewer({ novncUrl }: ScreenViewerProps) {
  const [expanded, setExpanded] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  if (!novncUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2 p-4">
        <MonitorOff className="w-8 h-8" />
        <p className="text-sm text-center">
          No active computer use session.
          <br />
          Ask Nexus to browse a website to start.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-2 py-1 border-b border-border">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Monitor className="w-3 h-3 text-green-500" />
          <span>Live Browser</span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 hover:bg-secondary rounded"
        >
          {expanded ? (
            <Minimize2 className="w-3 h-3" />
          ) : (
            <Maximize2 className="w-3 h-3" />
          )}
        </button>
      </div>
      <div className="flex-1 bg-black">
        <iframe
          ref={iframeRef}
          src={`${novncUrl}/vnc.html?autoconnect=true&resize=scale`}
          className="w-full h-full border-0"
          title="Browser View"
        />
      </div>
    </div>
  );
}
