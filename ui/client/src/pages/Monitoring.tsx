import { useState } from "react";
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
  Layers
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";

// Mock data for demonstration
const mockNodes = [
  { name: "control-plane-01", status: "Ready", role: "control-plane", cpu: 45, memory: 62, pods: 28, ip: "100.64.0.5" },
  { name: "worker-01", status: "Ready", role: "worker", cpu: 72, memory: 58, pods: 45, ip: "100.64.0.10" },
  { name: "worker-02", status: "Ready", role: "worker", cpu: 38, memory: 71, pods: 32, ip: "100.64.0.11" },
  { name: "gpu-worker-01", status: "Ready", role: "gpu-worker", cpu: 85, memory: 89, pods: 12, ip: "100.64.0.15" },
  { name: "worker-03", status: "NotReady", role: "worker", cpu: 0, memory: 0, pods: 0, ip: "100.64.0.12" },
];

const mockNamespaces = [
  { name: "ai-agents", running: 8, total: 8, status: "healthy" },
  { name: "monitoring", running: 5, total: 5, status: "healthy" },
  { name: "databases", running: 3, total: 4, status: "degraded" },
  { name: "default", running: 2, total: 2, status: "healthy" },
  { name: "flux-system", running: 4, total: 4, status: "healthy" },
  { name: "infrastructure", running: 6, total: 6, status: "healthy" },
];

const mockEvents = [
  { time: "2 min ago", type: "Normal", reason: "Scheduled", message: "Successfully assigned ai-agents/k8s-monitor-abc123 to worker-01", namespace: "ai-agents" },
  { time: "5 min ago", type: "Warning", reason: "BackOff", message: "Back-off restarting failed container", namespace: "databases" },
  { time: "8 min ago", type: "Normal", reason: "Pulled", message: "Container image pulled successfully", namespace: "ai-agents" },
  { time: "12 min ago", type: "Normal", reason: "Created", message: "Created container news-monitor", namespace: "ai-agents" },
  { time: "15 min ago", type: "Normal", reason: "Started", message: "Started container backup-agent", namespace: "ai-agents" },
  { time: "20 min ago", type: "Warning", reason: "FailedMount", message: "MountVolume.SetUp failed for volume", namespace: "databases" },
];

const mockMetricsData = Array.from({ length: 24 }, (_, i) => ({
  time: `${i}:00`,
  cpu: Math.floor(40 + Math.random() * 30),
  memory: Math.floor(50 + Math.random() * 25),
}));

const mockServices = [
  { name: "kubani-registry", namespace: "ai-agents", ready: "3/3", status: "healthy", type: "ClusterIP" },
  { name: "vllm-inference", namespace: "ai-agents", ready: "2/2", status: "healthy", type: "ClusterIP" },
  { name: "temporal-frontend", namespace: "infrastructure", ready: "1/1", status: "healthy", type: "ClusterIP" },
  { name: "qdrant", namespace: "databases", ready: "1/1", status: "healthy", type: "ClusterIP" },
  { name: "postgresql", namespace: "databases", ready: "0/1", status: "unhealthy", type: "ClusterIP" },
  { name: "traefik", namespace: "infrastructure", ready: "2/2", status: "healthy", type: "LoadBalancer" },
];

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

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 1000);
  };

  const healthyNodes = mockNodes.filter(n => n.status === "Ready").length;
  const totalPods = mockNodes.reduce((acc, n) => acc + n.pods, 0);
  const avgCpu = Math.round(mockNodes.filter(n => n.status === "Ready").reduce((acc, n) => acc + n.cpu, 0) / healthyNodes);
  const avgMemory = Math.round(mockNodes.filter(n => n.status === "Ready").reduce((acc, n) => acc + n.memory, 0) / healthyNodes);

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
            <span>Last updated: Just now</span>
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

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="glass gradient-border">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Cluster Health</p>
                <p className="text-2xl font-bold text-foreground mt-1">
                  {healthyNodes === mockNodes.length ? "Healthy" : "Degraded"}
                </p>
              </div>
              <div className={cn(
                "w-12 h-12 rounded-xl flex items-center justify-center",
                healthyNodes === mockNodes.length 
                  ? "bg-[oklch(0.70_0.18_155/0.15)]" 
                  : "bg-[oklch(0.75_0.15_85/0.15)]"
              )}>
                <Activity className={cn(
                  "w-6 h-6",
                  healthyNodes === mockNodes.length 
                    ? "text-[oklch(0.70_0.18_155)]" 
                    : "text-[oklch(0.75_0.15_85)]"
                )} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              {healthyNodes}/{mockNodes.length} nodes ready
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
              Across {mockNamespaces.length} namespaces
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
                    <AreaChart data={mockMetricsData}>
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
                    <AreaChart data={mockMetricsData}>
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
                    {mockNodes.map((node) => (
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
                    {mockServices.map((service) => (
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
                {mockNamespaces.map((ns) => (
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
                  {mockEvents.map((event, i) => (
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
