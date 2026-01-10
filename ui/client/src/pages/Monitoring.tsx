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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";

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

interface MetricPoint {
  time: string;
  cpu: number;
  memory: number;
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
  const [metricsHistory, setMetricsHistory] = useState<MetricPoint[]>([]);

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
        const nodesData = await nodesRes.json();
        setNodes(nodesData);

        // Update metrics history with current values
        const readyNodes = nodesData.filter((n: ClusterNode) => n.status === "Ready");
        if (readyNodes.length > 0) {
          const avgCpu = Math.round(readyNodes.reduce((acc: number, n: ClusterNode) => acc + n.cpu, 0) / readyNodes.length);
          const avgMem = Math.round(readyNodes.reduce((acc: number, n: ClusterNode) => acc + n.memory, 0) / readyNodes.length);

          setMetricsHistory(prev => {
            const now = new Date();
            const timeStr = `${now.getHours()}:${now.getMinutes().toString().padStart(2, '0')}`;
            const newPoint = { time: timeStr, cpu: avgCpu, memory: avgMem };

            // Keep last 24 data points
            const updated = [...prev, newPoint].slice(-24);
            return updated;
          });
        }
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
          {/* Resource Charts */}
          <Card className="glass gradient-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" />
                Resource Utilization
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="cpu" className="w-full">
                <TabsList className="glass mb-4">
                  <TabsTrigger value="cpu">CPU</TabsTrigger>
                  <TabsTrigger value="memory">Memory</TabsTrigger>
                </TabsList>
                <TabsContent value="cpu" className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={metricsHistory.length > 0 ? metricsHistory : [{ time: "now", cpu: avgCpu, memory: avgMemory }]}>
                      <defs>
                        <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="oklch(0.65 0.25 285)" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="oklch(0.65 0.25 285)" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis dataKey="time" stroke="rgba(255,255,255,0.5)" fontSize={12} />
                      <YAxis stroke="rgba(255,255,255,0.5)" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'oklch(0.16 0.015 285)',
                          border: '1px solid rgba(255,255,255,0.1)',
                          borderRadius: '8px'
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="cpu"
                        stroke="oklch(0.65 0.25 285)"
                        fill="url(#cpuGradient)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </TabsContent>
                <TabsContent value="memory" className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={metricsHistory.length > 0 ? metricsHistory : [{ time: "now", cpu: avgCpu, memory: avgMemory }]}>
                      <defs>
                        <linearGradient id="memGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="oklch(0.75 0.15 195)" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="oklch(0.75 0.15 195)" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis dataKey="time" stroke="rgba(255,255,255,0.5)" fontSize={12} />
                      <YAxis stroke="rgba(255,255,255,0.5)" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'oklch(0.16 0.015 285)',
                          border: '1px solid rgba(255,255,255,0.1)',
                          borderRadius: '8px'
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="memory"
                        stroke="oklch(0.75 0.15 195)"
                        fill="url(#memGradient)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

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
                    {services.map((service) => (
                      <tr
                        key={service.name}
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
                        <td className="py-3 px-2 font-mono text-sm">{service.ready}</td>
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
