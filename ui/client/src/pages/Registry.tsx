import { useState } from "react";
import { 
  Bot, 
  Server, 
  Sparkles, 
  Brain,
  Search,
  Plus,
  MoreVertical,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Grid3X3,
  List,
  Filter,
  ChevronRight,
  ExternalLink,
  Copy,
  Trash2,
  Edit
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// Mock data
const mockAgents = [
  { 
    id: "k8s-monitor", 
    name: "K8s Monitor", 
    description: "Monitors Kubernetes cluster health and generates reports",
    version: "1.2.0",
    status: "active",
    endpoint: "http://k8s-monitor.ai-agents.svc:8080",
    capabilities: ["cluster-analysis", "report-generation", "alerting"],
    lastHeartbeat: "2 min ago"
  },
  { 
    id: "news-monitor", 
    name: "News Monitor", 
    description: "Tracks and summarizes tech news from multiple sources",
    version: "1.0.3",
    status: "active",
    endpoint: "http://news-monitor.ai-agents.svc:8080",
    capabilities: ["web-scraping", "summarization", "categorization"],
    lastHeartbeat: "1 min ago"
  },
  { 
    id: "backup-agent", 
    name: "Backup Agent", 
    description: "Automated backup and disaster recovery management",
    version: "0.9.1",
    status: "inactive",
    endpoint: "http://backup-agent.ai-agents.svc:8080",
    capabilities: ["backup", "restore", "scheduling"],
    lastHeartbeat: "15 min ago"
  },
  { 
    id: "code-reviewer", 
    name: "Code Reviewer", 
    description: "AI-powered code review and suggestions",
    version: "2.1.0",
    status: "active",
    endpoint: "http://code-reviewer.ai-agents.svc:8080",
    capabilities: ["code-analysis", "suggestions", "security-scan"],
    lastHeartbeat: "30 sec ago"
  },
];

const mockMCPServers = [
  {
    id: "kubernetes-mcp",
    name: "Kubernetes MCP Server",
    description: "Provides Kubernetes cluster management tools",
    transport: "streamable-http",
    status: "active",
    capabilities: ["tools", "resources"],
    tools: 24,
  },
  {
    id: "github-mcp",
    name: "GitHub MCP Server",
    description: "GitHub repository and issue management",
    transport: "stdio",
    status: "active",
    capabilities: ["tools"],
    tools: 18,
  },
  {
    id: "filesystem-mcp",
    name: "Filesystem MCP Server",
    description: "Local filesystem operations",
    transport: "stdio",
    status: "active",
    capabilities: ["tools", "resources"],
    tools: 12,
  },
];

const mockSkills = [
  {
    id: "analyze-pod-logs",
    name: "Analyze Pod Logs",
    domain: "kubernetes",
    category: "diagnostics",
    confidence: 0.92,
    successRate: 94,
    status: "validated",
  },
  {
    id: "generate-report",
    name: "Generate Cluster Report",
    domain: "kubernetes",
    category: "reporting",
    confidence: 0.88,
    successRate: 91,
    status: "validated",
  },
  {
    id: "scale-deployment",
    name: "Scale Deployment",
    domain: "kubernetes",
    category: "operations",
    confidence: 0.95,
    successRate: 98,
    status: "validated",
  },
  {
    id: "summarize-news",
    name: "Summarize News Article",
    domain: "nlp",
    category: "summarization",
    confidence: 0.85,
    successRate: 89,
    status: "proposed",
  },
];

const mockModels = [
  {
    id: "qwen2.5-coder-32b",
    name: "Qwen 2.5 Coder 32B",
    type: "coding",
    provider: "local",
    quantization: "Q4_K_M",
    contextLength: 32768,
    status: "loaded",
  },
  {
    id: "llama-3.3-70b",
    name: "Llama 3.3 70B",
    type: "general",
    provider: "local",
    quantization: "Q4_K_M",
    contextLength: 128000,
    status: "available",
  },
  {
    id: "nomic-embed-text",
    name: "Nomic Embed Text",
    type: "embeddings",
    provider: "local",
    quantization: "fp16",
    contextLength: 8192,
    status: "loaded",
  },
];

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    active: "bg-[oklch(0.70_0.18_155/0.15)] text-[oklch(0.70_0.18_155)] border-[oklch(0.70_0.18_155/0.3)]",
    loaded: "bg-[oklch(0.70_0.18_155/0.15)] text-[oklch(0.70_0.18_155)] border-[oklch(0.70_0.18_155/0.3)]",
    validated: "bg-[oklch(0.70_0.18_155/0.15)] text-[oklch(0.70_0.18_155)] border-[oklch(0.70_0.18_155/0.3)]",
    inactive: "bg-[oklch(0.75_0.15_85/0.15)] text-[oklch(0.75_0.15_85)] border-[oklch(0.75_0.15_85/0.3)]",
    available: "bg-primary/15 text-primary border-primary/30",
    proposed: "bg-accent/15 text-accent border-accent/30",
  };
  
  return (
    <Badge variant="outline" className={cn("font-medium capitalize", variants[status] || "")}>
      {status}
    </Badge>
  );
}

function AgentCard({ agent }: { agent: typeof mockAgents[0] }) {
  return (
    <Card className="glass gradient-border hover:bg-white/5 transition-all cursor-pointer group">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center">
              <Bot className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">{agent.name}</h3>
              <p className="text-xs text-muted-foreground font-mono">{agent.id}</p>
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="glass">
              <DropdownMenuItem onClick={() => toast("Edit agent coming soon")}>
                <Edit className="w-4 h-4 mr-2" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => {
                navigator.clipboard.writeText(agent.endpoint);
                toast("Endpoint copied to clipboard");
              }}>
                <Copy className="w-4 h-4 mr-2" />
                Copy Endpoint
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive" onClick={() => toast("Delete agent coming soon")}>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        
        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">{agent.description}</p>
        
        <div className="flex flex-wrap gap-1.5 mb-3">
          {agent.capabilities.slice(0, 3).map((cap) => (
            <Badge key={cap} variant="secondary" className="text-xs font-mono">
              {cap}
            </Badge>
          ))}
          {agent.capabilities.length > 3 && (
            <Badge variant="secondary" className="text-xs">
              +{agent.capabilities.length - 3}
            </Badge>
          )}
        </div>
        
        <div className="flex items-center justify-between pt-3 border-t border-white/10">
          <div className="flex items-center gap-2">
            <StatusBadge status={agent.status} />
            <span className="text-xs text-muted-foreground">v{agent.version}</span>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="w-3 h-3" />
            {agent.lastHeartbeat}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function MCPServerCard({ server }: { server: typeof mockMCPServers[0] }) {
  return (
    <Card className="glass gradient-border hover:bg-white/5 transition-all cursor-pointer group">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-accent/15 flex items-center justify-center">
              <Server className="w-5 h-5 text-accent" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">{server.name}</h3>
              <p className="text-xs text-muted-foreground font-mono">{server.id}</p>
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="glass">
              <DropdownMenuItem onClick={() => toast("View tools coming soon")}>
                <ExternalLink className="w-4 h-4 mr-2" />
                View Tools
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => toast("Edit server coming soon")}>
                <Edit className="w-4 h-4 mr-2" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive" onClick={() => toast("Delete server coming soon")}>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        
        <p className="text-sm text-muted-foreground mb-3">{server.description}</p>
        
        <div className="flex items-center gap-2 mb-3">
          <Badge variant="secondary" className="text-xs font-mono">
            {server.transport}
          </Badge>
          {server.capabilities.map((cap) => (
            <Badge key={cap} variant="outline" className="text-xs">
              {cap}
            </Badge>
          ))}
        </div>
        
        <div className="flex items-center justify-between pt-3 border-t border-white/10">
          <StatusBadge status={server.status} />
          <span className="text-sm text-muted-foreground">{server.tools} tools</span>
        </div>
      </CardContent>
    </Card>
  );
}

function SkillCard({ skill }: { skill: typeof mockSkills[0] }) {
  return (
    <Card className="glass gradient-border hover:bg-white/5 transition-all cursor-pointer">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[oklch(0.75_0.15_85/0.15)] flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-[oklch(0.75_0.15_85)]" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">{skill.name}</h3>
              <p className="text-xs text-muted-foreground font-mono">{skill.id}</p>
            </div>
          </div>
          <StatusBadge status={skill.status} />
        </div>
        
        <div className="flex items-center gap-2 mb-3">
          <Badge variant="secondary" className="text-xs">
            {skill.domain}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {skill.category}
          </Badge>
        </div>
        
        <div className="grid grid-cols-2 gap-4 pt-3 border-t border-white/10">
          <div>
            <p className="text-xs text-muted-foreground">Confidence</p>
            <p className="text-lg font-semibold">{Math.round(skill.confidence * 100)}%</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Success Rate</p>
            <p className="text-lg font-semibold">{skill.successRate}%</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ModelCard({ model }: { model: typeof mockModels[0] }) {
  return (
    <Card className="glass gradient-border hover:bg-white/5 transition-all cursor-pointer">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[oklch(0.70_0.18_155/0.15)] flex items-center justify-center">
              <Brain className="w-5 h-5 text-[oklch(0.70_0.18_155)]" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground">{model.name}</h3>
              <p className="text-xs text-muted-foreground font-mono">{model.id}</p>
            </div>
          </div>
          <StatusBadge status={model.status} />
        </div>
        
        <div className="flex items-center gap-2 mb-3">
          <Badge variant="secondary" className="text-xs capitalize">
            {model.type}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {model.quantization}
          </Badge>
        </div>
        
        <div className="grid grid-cols-2 gap-4 pt-3 border-t border-white/10">
          <div>
            <p className="text-xs text-muted-foreground">Provider</p>
            <p className="text-sm font-medium capitalize">{model.provider}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Context</p>
            <p className="text-sm font-medium">{(model.contextLength / 1000).toFixed(0)}K</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Registry() {
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Registry</h1>
          <p className="text-muted-foreground mt-1">Browse and manage registered entities</p>
        </div>
        <Button className="gap-2" onClick={() => toast("Register new entity coming soon")}>
          <Plus className="w-4 h-4" />
          Register New
        </Button>
      </div>

      {/* Search & Filters */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, ID, or capability..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 glass"
          />
        </div>
        <Button variant="outline" size="icon" className="glass" onClick={() => toast("Filters coming soon")}>
          <Filter className="w-4 h-4" />
        </Button>
        <div className="flex items-center border border-white/10 rounded-lg p-1 glass">
          <Button
            variant={viewMode === "grid" ? "secondary" : "ghost"}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode("grid")}
          >
            <Grid3X3 className="w-4 h-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "secondary" : "ghost"}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode("list")}
          >
            <List className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="agents" className="w-full">
        <TabsList className="glass mb-6">
          <TabsTrigger value="agents" className="gap-2">
            <Bot className="w-4 h-4" />
            Agents
            <Badge variant="secondary" className="ml-1">{mockAgents.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="mcp" className="gap-2">
            <Server className="w-4 h-4" />
            MCP Servers
            <Badge variant="secondary" className="ml-1">{mockMCPServers.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="skills" className="gap-2">
            <Sparkles className="w-4 h-4" />
            Skills
            <Badge variant="secondary" className="ml-1">{mockSkills.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="models" className="gap-2">
            <Brain className="w-4 h-4" />
            Models
            <Badge variant="secondary" className="ml-1">{mockModels.length}</Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="agents">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {mockAgents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="mcp">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {mockMCPServers.map((server) => (
              <MCPServerCard key={server.id} server={server} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="skills">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {mockSkills.map((skill) => (
              <SkillCard key={skill.id} skill={skill} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="models">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {mockModels.map((model) => (
              <ModelCard key={model.id} model={model} />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
