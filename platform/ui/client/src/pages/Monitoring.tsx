import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Server,
  Cpu,
  HardDrive,
  Network,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Clock,
  Layers,
  Loader2
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

// Types for cluster data
interface ClusterNode {
  name: string;
  status: string;
  role: string;
  cpu: number;
  memory: number;
  pods: number;
  ip: string;
}

interface Namespace {
  name: string;
  running: number;
  total: number;
  status: string;
}

interface ClusterEvent {
  time: string;
  type: string;
  reason: string;
  message: string;
  namespace: string;
}

interface Service {
  name: string;
  namespace: string;
  ready: string;
  status: string;
  type: string;
}

interface CollapsedService {
  name: string;
  namespace: string;
  readyCount: number;
  totalCount: number;
  status: string;
  type: string;
  instanceCount: number;
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "Ready":
    case "healthy":
      return <CheckCircle2 className="w-4 h-4 text-[oklch(0.70_0.18_155)]" />;
    case "degraded":
    case "NotReady":
      return <AlertTriangle className="w-4 h-4 text-[oklch(0.75_0.15_85)]" />;
    case "unhealthy":
      return <XCircle className="w-4 h-4 text-[oklch(0.65_0.2_15)]" />;
    default:
      return <Activity className="w-4 h-4 text-muted-foreground" />;
  }
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    Ready: "bg-[oklch(0.70_0.18_155/0.15)] text-[oklch(0.70_0.18_155)] border-[oklch(0.70_0.18_155/0.3)]",
    healthy: "bg-[oklch(0.70_0.18_155/0.15)] text-[oklch(0.70_0.18_155)] border-[oklch(0.70_0.18_155/0.3)]",
    degraded: "bg-[oklch(0.75_0.15_85/0.15)] text-[oklch(0.75_0.15_85)] border-[oklch(0.75_0.15_85/0.3)]",
    NotReady: "bg-[oklch(0.65_0.2_15/0.15)] text-[oklch(0.65_0.2_15)] border-[oklch(0.65_0.2_15/0.3)]",
    unhealthy: "bg-[oklch(0.65_0.2_15/0.15)] text-[oklch(0.65_0.2_15)] border-[oklch(0.65_0.2_15/0.3)]",
  };

  return (
    <Badge variant="outline" className={cn("font-medium", variants[status] || "")}>
      {status}
    </Badge>
  );
}

export default function Monitoring() {
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Real cluster data states
  const [nodes, setNodes] = useState<ClusterNode[]>([]);
  const [namespaces, setNamespaces] = useState<Namespace[]>([]);
  const [events, setEvents] = useState<ClusterEvent[]>([]);
  const [services, setServices] = useState<Service[]>([]);

  // Fetch all monitoring data
  const fetchData = useCallback(async () => {
    try {
      const [nodesRes, nsRes, eventsRes, servicesRes] = await Promise.all([
        fetch("/api/monitoring/nodes"),
        fetch("/api/monitoring/namespaces"),
        fetch("/api/monitoring/events"),
        fetch("/api/monitoring/services"),
      ]);

      if (nodesRes.ok) {
        setNodes(await nodesRes.json());
      }

      if (nsRes.ok) {
        setNamespaces(await nsRes.json());
      }

      if (eventsRes.ok) {
        setEvents(await eventsRes.json());
      }

      if (servicesRes.ok) {
        setServices(await servicesRes.json());
      }

      setLastUpdated(new Date());
    } catch (error) {
      console.error("Failed to fetch monitoring data:", error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Initial load and auto-refresh
  useEffect(() => {
    fetchData();

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // Calculate summary stats
  const healthyNodes = nodes.filter(n => n.status === "Ready").length;
  const totalNodes = nodes.length;
  const totalPods = nodes.reduce((acc, n) => acc + n.pods, 0);
  const avgCpu = healthyNodes > 0
    ? Math.round(nodes.filter(n => n.status === "Ready").reduce((acc, n) => acc + n.cpu, 0) / healthyNodes)
    : 0;
  const avgMemory = healthyNodes > 0
    ? Math.round(nodes.filter(n => n.status === "Ready").reduce((acc, n) => acc + n.memory, 0) / healthyNodes)
    : 0;

  // Collapse duplicate services (same name + namespace) into single rows
  const collapsedServices: CollapsedService[] = (() => {
    const groups = new Map<string, CollapsedService>();
    for (const svc of services) {
      const key = `${svc.namespace}/${svc.name}`;
      const [ready, total] = svc.ready.split("/").map(n => parseInt(n) || 0);
      const existing = groups.get(key);
      if (existing) {
        existing.readyCount += ready;
        existing.totalCount += total;
        existing.instanceCount += 1;
        // Worst status wins
        if (svc.status === "unhealthy" || (svc.status === "degraded" && existing.status === "healthy")) {
          existing.status = svc.status;
        }
      } else {
        groups.set(key, {
          name: svc.name,
          namespace: svc.namespace,
          readyCount: ready,
          totalCount: total,
          status: svc.status,
          type: svc.type,
          instanceCount: 1,
        });
      }
    }
    return Array.from(groups.values());
  })();

  // Format last updated time
  const lastUpdatedStr = lastUpdated
    ? `${lastUpdated.toLocaleTimeString()}`
    : "Never";

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Cluster Monitoring</h1>
          <p className="text-muted-foreground mt-1">Real-time overview of your Kubani cluster</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="w-4 h-4" />
            <span>Last updated: {lastUpdatedStr}</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            className="glass"
          >
            <RefreshCw className={cn("w-4 h-4 mr-2", refreshing && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="ml-3 text-muted-foreground">Loading cluster data...</span>
        </div>
      )}

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="glass gradient-border">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Cluster Health</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  {totalNodes === 0 ? "Unknown" : healthyNodes === totalNodes ? "Healthy" : "Degraded"}
                </p>
              </div>
              <div className={cn(
                "w-12 h-12 rounded-xl flex items-center justify-center",
                healthyNodes === totalNodes && totalNodes > 0
                  ? "bg-[oklch(0.70_0.18_155/0.15)]"
                  : "bg-[oklch(0.75_0.15_85/0.15)]"
              )}>
                <Activity className={cn(
                  "w-6 h-6",
                  healthyNodes === totalNodes && totalNodes > 0
                    ? "text-[oklch(0.70_0.18_155)]"
                    : "text-[oklch(0.75_0.15_85)]"
                )} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              {healthyNodes}/{totalNodes} nodes ready
            </p>
          </CardContent>
        </Card>

        <Card className="glass gradient-border">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Pods</p>
                <p className="text-2xl font-bold text-foreground mt-1">{totalPods}</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center">
                <Layers className="w-6 h-6 text-primary" />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              Across {namespaces.length} namespaces
            </p>
          </CardContent>
        </Card>

        <Card className="glass gradient-border">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Avg CPU Usage</p>
                <p className="text-2xl font-bold text-foreground mt-1">{avgCpu}%</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-accent/15 flex items-center justify-center">
                <Cpu className="w-6 h-6 text-accent" />
              </div>
            </div>
            <Progress value={avgCpu} className="mt-3 h-1.5" />
          </CardContent>
        </Card>

        <Card className="glass gradient-border">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Avg Memory</p>
                <p className="text-2xl font-bold text-foreground mt-1">{avgMemory}%</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-[oklch(0.75_0.15_85/0.15)] flex items-center justify-center">
                <HardDrive className="w-6 h-6 text-[oklch(0.75_0.15_85)]" />
              </div>
            </div>
            <Progress value={avgMemory} className="mt-3 h-1.5" />
          </CardContent>
        </Card>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Nodes & Services */}
        <div className="lg:col-span-2 space-y-6">
          {/* Nodes Table */}
          <Card className="glass gradient-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <Server className="w-5 h-5 text-primary" />
                Cluster Nodes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Node</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Status</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Role</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">CPU</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Memory</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Pods</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">IP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nodes.map((node) => (
                      <tr
                        key={node.name}
                        className="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer"
                      >
                        <td className="py-3 px-2">
                          <div className="flex items-center gap-2">
                            <Server className="w-4 h-4 text-muted-foreground" />
                            <span className="font-mono text-sm">{node.name}</span>
                          </div>
                        </td>
                        <td className="py-3 px-2">
                          <StatusBadge status={node.status} />
                        </td>
                        <td className="py-3 px-2">
                          <Badge variant="secondary" className="font-mono text-xs">
                            {node.role}
                          </Badge>
                        </td>
                        <td className="py-3 px-2">
                          <div className="flex items-center gap-2">
                            <Progress value={node.cpu} className="w-16 h-1.5" />
                            <span className="text-sm text-muted-foreground">{node.cpu}%</span>
                          </div>
                        </td>
                        <td className="py-3 px-2">
                          <div className="flex items-center gap-2">
                            <Progress value={node.memory} className="w-16 h-1.5" />
                            <span className="text-sm text-muted-foreground">{node.memory}%</span>
                          </div>
                        </td>
                        <td className="py-3 px-2 text-sm">{node.pods}</td>
                        <td className="py-3 px-2">
                          <code className="text-xs bg-white/5 px-2 py-1 rounded">{node.ip}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Services Table */}
          <Card className="glass gradient-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <Network className="w-5 h-5 text-primary" />
                Services
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Service</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Namespace</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Ready</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Status</th>
                      <th className="text-left py-3 px-2 text-sm font-medium text-muted-foreground">Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {collapsedServices.map((service) => (
                      <tr
                        key={`${service.namespace}/${service.name}`}
                        className="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer"
                      >
                        <td className="py-3 px-2">
                          <span className="font-mono text-sm">{service.name}</span>
                        </td>
                        <td className="py-3 px-2">
                          <Badge variant="secondary" className="font-mono text-xs">
                            {service.namespace}
                          </Badge>
                        </td>
                        <td className="py-3 px-2 font-mono text-sm">{service.readyCount}/{service.totalCount}</td>
                        <td className="py-3 px-2">
                          <div className="flex items-center gap-2">
                            <StatusIcon status={service.status} />
                            <span className="text-sm capitalize">{service.status}</span>
                          </div>
                        </td>
                        <td className="py-3 px-2">
                          <code className="text-xs bg-white/5 px-2 py-1 rounded">{service.type}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column - Events & Namespaces */}
        <div className="space-y-6">
          {/* Namespace Status */}
          <Card className="glass gradient-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <Layers className="w-5 h-5 text-primary" />
                Namespaces
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                {namespaces.map((ns) => (
                  <div
                    key={ns.name}
                    className={cn(
                      "p-3 rounded-lg border cursor-pointer transition-all hover:scale-[1.02]",
                      ns.status === "healthy" && "bg-[oklch(0.70_0.18_155/0.05)] border-[oklch(0.70_0.18_155/0.2)]",
                      ns.status === "degraded" && "bg-[oklch(0.75_0.15_85/0.05)] border-[oklch(0.75_0.15_85/0.2)]",
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-xs truncate">{ns.name}</span>
                      <StatusIcon status={ns.status} />
                    </div>
                    <p className="text-lg font-semibold">
                      {ns.running}/{ns.total}
                    </p>
                    <p className="text-xs text-muted-foreground">pods running</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Events Feed */}
          <Card className="glass gradient-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" />
                Recent Events
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px] pr-4">
                <div className="space-y-3">
                  {events.map((event, i) => (
                    <div
                      key={i}
                      className={cn(
                        "p-3 rounded-lg border-l-2 bg-white/5",
                        event.type === "Normal" && "border-l-[oklch(0.70_0.18_155)]",
                        event.type === "Warning" && "border-l-[oklch(0.75_0.15_85)]",
                      )}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-xs",
                            event.type === "Normal" && "border-[oklch(0.70_0.18_155/0.3)] text-[oklch(0.70_0.18_155)]",
                            event.type === "Warning" && "border-[oklch(0.75_0.15_85/0.3)] text-[oklch(0.75_0.15_85)]",
                          )}
                        >
                          {event.reason}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{event.time}</span>
                      </div>
                      <p className="text-sm text-foreground/90 mb-1">{event.message}</p>
                      <code className="text-xs text-muted-foreground">{event.namespace}</code>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
