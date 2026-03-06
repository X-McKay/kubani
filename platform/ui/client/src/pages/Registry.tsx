import { useState, useEffect, useCallback } from "react";
import {
  Bot,
  Server,
  Sparkles,
  Brain,
  Search,
  Plus,
  MoreVertical,
  Clock,
  Grid3X3,
  List,
  Filter,
  ExternalLink,
  Copy,
  Trash2,
  Edit,
  Loader2
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/useMobile";
import { toast } from "sonner";

// Types for registry data
interface Agent {
  id: string;
  name: string;
  description: string;
  version?: string;
  status: string;
  endpoint?: string;
  capabilities: string[] | Array<{ name: string; description: string }>;
  lastHeartbeat?: string;
}

interface MCPServer {
  id: string;
  name: string;
  description: string;
  transport: string;
  status: string;
  capabilities: string[];
  tools: number;
}

interface Skill {
  id: string;
  name: string;
  domain: string;
  category: string;
  confidence: number;
  success_count: number;
  failure_count: number;
  status: string;
}

interface Model {
  id: string;
  name: string;
  type: string;
  provider: string;
  quantization?: string;
  contextLength: number;
  status: string;
}

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

function AgentCard({ agent, isMobile }: { agent: Agent; isMobile: boolean }) {
  // Normalize capabilities to string array
  const capabilityNames = agent.capabilities.map(cap =>
    typeof cap === 'string' ? cap : cap.name
  );

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
              <Button variant="ghost" size="icon" className={cn("transition-opacity", isMobile ? "opacity-100" : "opacity-0 group-hover:opacity-100")}>
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="glass">
              <DropdownMenuItem onClick={() => toast("Edit agent coming soon")}>
                <Edit className="w-4 h-4 mr-2" />
                Edit
              </DropdownMenuItem>
              {agent.endpoint && (
                <DropdownMenuItem onClick={() => {
                  navigator.clipboard.writeText(agent.endpoint!);
                  toast("Endpoint copied to clipboard");
                }}>
                  <Copy className="w-4 h-4 mr-2" />
                  Copy Endpoint
                </DropdownMenuItem>
              )}
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
          {capabilityNames.slice(0, 3).map((cap) => (
            <Badge key={cap} variant="secondary" className="text-xs font-mono">
              {cap}
            </Badge>
          ))}
          {capabilityNames.length > 3 && (
            <Badge variant="secondary" className="text-xs">
              +{capabilityNames.length - 3}
            </Badge>
          )}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-white/10">
          <div className="flex items-center gap-2">
            <StatusBadge status={agent.status === "ready" ? "active" : agent.status} />
            {agent.version && <span className="text-xs text-muted-foreground">v{agent.version}</span>}
          </div>
          {agent.lastHeartbeat && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="w-3 h-3" />
              {agent.lastHeartbeat}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function MCPServerCard({ server, isMobile }: { server: MCPServer; isMobile: boolean }) {
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
              <Button variant="ghost" size="icon" className={cn("transition-opacity", isMobile ? "opacity-100" : "opacity-0 group-hover:opacity-100")}>
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

function SkillCard({ skill }: { skill: Skill }) {
  const totalExecutions = skill.success_count + skill.failure_count;
  const successRate = totalExecutions > 0
    ? Math.round((skill.success_count / totalExecutions) * 100)
    : 0;

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
            <p className="text-xs text-muted-foreground">Executions</p>
            <p className="text-lg font-semibold">
              {totalExecutions > 0 ? `${successRate}% (${totalExecutions})` : "No data"}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ModelCard({ model }: { model: Model }) {
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
  const isMobile = useIsMobile();
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);

  // Real registry data states
  const [agents, setAgents] = useState<Agent[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [models, setModels] = useState<Model[]>([]);

  // Fetch all registry data
  const fetchData = useCallback(async () => {
    try {
      const [agentsRes, mcpRes, skillsRes, modelsRes] = await Promise.all([
        fetch("/api/agents"),
        fetch("/api/registry/mcp-servers"),
        fetch("/api/registry/skills"),
        fetch("/api/registry/models"),
      ]);

      if (agentsRes.ok) {
        const data = await agentsRes.json();
        setAgents(data);
      }

      if (mcpRes.ok) {
        setMcpServers(await mcpRes.json());
      }

      if (skillsRes.ok) {
        setSkills(await skillsRes.json());
      }

      if (modelsRes.ok) {
        setModels(await modelsRes.json());
      }
    } catch (error) {
      console.error("Failed to fetch registry data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Filter data based on search query
  const filteredAgents = agents.filter(a =>
    a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredMcpServers = mcpServers.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredSkills = skills.filter(s =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.domain.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredModels = models.filter(m =>
    m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    m.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen p-4 md:p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Registry</h1>
          <p className="text-muted-foreground mt-1">Browse and manage registered entities</p>
        </div>
        <Button className="gap-2" onClick={() => toast("Register new entity coming soon")}>
          <Plus className="w-4 h-4" />
          {!isMobile && "Register New"}
        </Button>
      </div>

      {/* Search & Filters */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1 max-w-full md:max-w-md">
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
        {!isMobile && (
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
        )}
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="ml-3 text-muted-foreground">Loading registry data...</span>
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="agents" className="w-full">
        <TabsList className="glass mb-6 overflow-x-auto">
          <TabsTrigger value="agents" className="gap-1.5">
            <Bot className="w-4 h-4" />
            {!isMobile && <span>Agents</span>}
            {!isMobile && <Badge variant="secondary" className="ml-1">{agents.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="mcp" className="gap-1.5">
            <Server className="w-4 h-4" />
            {!isMobile && <span>MCP Servers</span>}
            {!isMobile && <Badge variant="secondary" className="ml-1">{mcpServers.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="skills" className="gap-1.5">
            <Sparkles className="w-4 h-4" />
            {!isMobile && <span>Skills</span>}
            {!isMobile && <Badge variant="secondary" className="ml-1">{skills.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="models" className="gap-1.5">
            <Brain className="w-4 h-4" />
            {!isMobile && <span>Models</span>}
            {!isMobile && <Badge variant="secondary" className="ml-1">{models.length}</Badge>}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="agents">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {filteredAgents.length > 0 ? (
              filteredAgents.map((agent) => (
                <AgentCard key={agent.id} agent={agent} isMobile={isMobile} />
              ))
            ) : !loading && (
              <p className="text-muted-foreground col-span-full text-center py-8">No agents found</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="mcp">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {filteredMcpServers.length > 0 ? (
              filteredMcpServers.map((server) => (
                <MCPServerCard key={server.id} server={server} isMobile={isMobile} />
              ))
            ) : !loading && (
              <p className="text-muted-foreground col-span-full text-center py-8">No MCP servers found</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="skills">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {filteredSkills.length > 0 ? (
              filteredSkills.map((skill) => (
                <SkillCard key={skill.id} skill={skill} />
              ))
            ) : !loading && (
              <p className="text-muted-foreground col-span-full text-center py-8">No skills found</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="models">
          <div className={cn(
            "grid gap-4",
            viewMode === "grid" ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1"
          )}>
            {filteredModels.length > 0 ? (
              filteredModels.map((model) => (
                <ModelCard key={model.id} model={model} />
              ))
            ) : !loading && (
              <p className="text-muted-foreground col-span-full text-center py-8">No models found</p>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
