export interface ActivityEvent {
  id: string;
  source: string;
  event_type: string;
  title: string;
  content: string;
  metadata: Record<string, unknown>;
  severity: "info" | "warning" | "error" | "success";
  created_at: string;
  read: boolean;
}

export interface FeedFilter {
  source?: string;
  event_type?: string;
}

export const EVENT_TYPE_CONFIG: Record<
  string,
  { label: string; icon: string; color: string }
> = {
  syndicate_output: { label: "Output", icon: "FileText", color: "text-accent" },
  agent_activity: { label: "Agent", icon: "Bot", color: "text-primary" },
  alert: { label: "Alert", icon: "AlertTriangle", color: "text-warning" },
  approval: { label: "Approval", icon: "ShieldCheck", color: "text-warning" },
  workflow: { label: "Workflow", icon: "Workflow", color: "text-info" },
  learning: { label: "Learning", icon: "Brain", color: "text-accent" },
  system: { label: "System", icon: "Settings", color: "text-muted-foreground" },
};

export const SOURCE_CONFIG: Record<
  string,
  { label: string; shortLabel: string }
> = {
  "k8s-monitor": { label: "Kubernetes Monitor", shortLabel: "k8s" },
  "news-digest": { label: "News Digest", shortLabel: "news" },
  "learning-system": { label: "Learning System", shortLabel: "learn" },
  system: { label: "System", shortLabel: "sys" },
  nexus: { label: "Nexus Agent", shortLabel: "nex" },
};
