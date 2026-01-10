import { useState, useRef, useEffect } from "react";
import { 
  Bot, 
  Send, 
  Plus,
  ChevronDown,
  ChevronRight,
  Terminal,
  FileText,
  Clock,
  CheckCircle2,
  Loader2,
  Copy,
  RotateCcw,
  Settings,
  Maximize2,
  Minimize2,
  PanelRightClose,
  PanelRight,
  Sparkles,
  Wrench,
  Brain,
  MessageSquare
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Streamdown } from "streamdown";

// Mock data
const mockAgents = [
  { id: "k8s-monitor", name: "K8s Monitor", status: "ready" },
  { id: "news-monitor", name: "News Monitor", status: "ready" },
  { id: "backup-agent", name: "Backup Agent", status: "offline" },
  { id: "code-reviewer", name: "Code Reviewer", status: "ready" },
];

const mockConversations = [
  { id: "1", title: "Cluster health check", agent: "k8s-monitor", time: "2 hours ago" },
  { id: "2", title: "News summary request", agent: "news-monitor", time: "Yesterday" },
  { id: "3", title: "Pod scaling issue", agent: "k8s-monitor", time: "2 days ago" },
];

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
}

interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
  status: "pending" | "running" | "completed" | "failed";
}

interface ActivityLog {
  id: string;
  timestamp: Date;
  type: "thought" | "action" | "result" | "error";
  content: string;
}

const mockMessages: Message[] = [
  {
    id: "1",
    role: "user",
    content: "Can you check the health of the cluster and give me a summary?",
    timestamp: new Date(Date.now() - 1000 * 60 * 5),
  },
  {
    id: "2",
    role: "assistant",
    content: "I'll analyze the cluster health for you. Let me check the node status, pod health, and resource utilization.",
    timestamp: new Date(Date.now() - 1000 * 60 * 4),
    toolCalls: [
      {
        id: "tc1",
        name: "get_cluster_nodes",
        arguments: { includeMetrics: true },
        result: JSON.stringify({
          nodes: [
            { name: "control-plane-01", status: "Ready", cpu: "45%", memory: "62%" },
            { name: "worker-01", status: "Ready", cpu: "72%", memory: "58%" },
            { name: "worker-02", status: "Ready", cpu: "38%", memory: "71%" },
          ]
        }, null, 2),
        status: "completed",
      },
      {
        id: "tc2",
        name: "get_pod_status",
        arguments: { namespace: "all" },
        result: JSON.stringify({
          total: 117,
          running: 115,
          pending: 1,
          failed: 1
        }, null, 2),
        status: "completed",
      },
    ],
  },
  {
    id: "3",
    role: "assistant",
    content: `## Cluster Health Summary

Based on my analysis, here's the current state of your cluster:

### Node Status
All **3 nodes** are in Ready state:
- **control-plane-01**: CPU 45%, Memory 62%
- **worker-01**: CPU 72%, Memory 58% 
- **worker-02**: CPU 38%, Memory 71%

### Pod Health
- Total Pods: **117**
- Running: **115** (98.3%)
- Pending: **1**
- Failed: **1**

### Recommendations
1. Worker-01 has elevated CPU usage (72%). Consider monitoring for potential scaling needs.
2. There's 1 failed pod that needs attention. Would you like me to investigate?

Overall cluster health: **Good** with minor issues to address.`,
    timestamp: new Date(Date.now() - 1000 * 60 * 3),
  },
];

const mockActivityLogs: ActivityLog[] = [
  { id: "1", timestamp: new Date(Date.now() - 1000 * 60 * 5), type: "thought", content: "User is requesting a cluster health check. I'll need to gather information about nodes, pods, and resource utilization." },
  { id: "2", timestamp: new Date(Date.now() - 1000 * 60 * 4.5), type: "action", content: "Calling get_cluster_nodes with includeMetrics=true" },
  { id: "3", timestamp: new Date(Date.now() - 1000 * 60 * 4.3), type: "result", content: "Retrieved 3 nodes, all in Ready state" },
  { id: "4", timestamp: new Date(Date.now() - 1000 * 60 * 4), type: "action", content: "Calling get_pod_status for all namespaces" },
  { id: "5", timestamp: new Date(Date.now() - 1000 * 60 * 3.8), type: "result", content: "Retrieved pod status: 115/117 running" },
  { id: "6", timestamp: new Date(Date.now() - 1000 * 60 * 3.5), type: "thought", content: "Analyzing results to provide a comprehensive summary with recommendations" },
];

function ToolCallBlock({ toolCall }: { toolCall: ToolCall }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="my-2 rounded-lg border border-white/10 bg-white/5 overflow-hidden">
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center gap-2 px-3 py-2 hover:bg-white/5 transition-colors">
            {isOpen ? (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            )}
            <Wrench className="w-4 h-4 text-accent" />
            <span className="font-mono text-sm text-accent">{toolCall.name}</span>
            <Badge 
              variant="outline" 
              className={cn(
                "ml-auto text-xs",
                toolCall.status === "completed" && "border-[oklch(0.70_0.18_155/0.3)] text-[oklch(0.70_0.18_155)]",
                toolCall.status === "running" && "border-primary/30 text-primary",
                toolCall.status === "failed" && "border-destructive/30 text-destructive",
              )}
            >
              {toolCall.status === "running" && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
              {toolCall.status === "completed" && <CheckCircle2 className="w-3 h-3 mr-1" />}
              {toolCall.status}
            </Badge>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t border-white/10">
            <div className="px-3 py-2 border-b border-white/5">
              <p className="text-xs text-muted-foreground mb-1">Arguments</p>
              <pre className="text-xs font-mono bg-black/20 p-2 rounded overflow-x-auto">
                {JSON.stringify(toolCall.arguments, null, 2)}
              </pre>
            </div>
            {toolCall.result && (
              <div className="px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs text-muted-foreground">Result</p>
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-6 w-6"
                    onClick={() => {
                      navigator.clipboard.writeText(toolCall.result || "");
                      toast("Result copied to clipboard");
                    }}
                  >
                    <Copy className="w-3 h-3" />
                  </Button>
                </div>
                <pre className="text-xs font-mono bg-black/20 p-2 rounded overflow-x-auto max-h-[200px]">
                  {toolCall.result}
                </pre>
              </div>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-3 animate-slide-up", isUser && "flex-row-reverse")}>
      <div className={cn(
        "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
        isUser ? "bg-primary/15" : "bg-accent/15"
      )}>
        {isUser ? (
          <MessageSquare className="w-4 h-4 text-primary" />
        ) : (
          <Bot className="w-4 h-4 text-accent" />
        )}
      </div>
      <div className={cn("flex-1 max-w-[80%]", isUser && "flex flex-col items-end")}>
        <div className={cn(
          "rounded-lg px-4 py-3",
          isUser ? "bg-primary/15 border border-primary/20" : "bg-white/5 border border-white/10"
        )}>
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="mb-3">
              {message.toolCalls.map((tc) => (
                <ToolCallBlock key={tc.id} toolCall={tc} />
              ))}
            </div>
          )}
          <div className="prose prose-invert prose-sm max-w-none">
            <Streamdown>{message.content}</Streamdown>
          </div>
        </div>
        <span className="text-xs text-muted-foreground mt-1">
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  );
}

function ActivityLogItem({ log }: { log: ActivityLog }) {
  const icons = {
    thought: <Brain className="w-3 h-3 text-primary" />,
    action: <Wrench className="w-3 h-3 text-accent" />,
    result: <CheckCircle2 className="w-3 h-3 text-[oklch(0.70_0.18_155)]" />,
    error: <Terminal className="w-3 h-3 text-destructive" />,
  };

  const colors = {
    thought: "border-l-primary/50",
    action: "border-l-accent/50",
    result: "border-l-[oklch(0.70_0.18_155/0.5)]",
    error: "border-l-destructive/50",
  };

  return (
    <div className={cn("pl-3 py-2 border-l-2 text-sm", colors[log.type])}>
      <div className="flex items-center gap-2 mb-1">
        {icons[log.type]}
        <span className="text-xs text-muted-foreground capitalize">{log.type}</span>
        <span className="text-xs text-muted-foreground ml-auto">
          {log.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </div>
      <p className="text-muted-foreground text-xs">{log.content}</p>
    </div>
  );
}

export default function Chat() {
  // Note: This page has its own layout, so we need to handle the sidebar differently
  const [selectedAgent, setSelectedAgent] = useState("k8s-monitor");
  const [messages, setMessages] = useState<Message[]>(mockMessages);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>(mockActivityLogs);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showActivityPanel, setShowActivityPanel] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = () => {
    if (!inputValue.trim() || isLoading) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages([...messages, newMessage]);
    setInputValue("");
    setIsLoading(true);

    // Simulate agent response
    setTimeout(() => {
      const newLog: ActivityLog = {
        id: Date.now().toString(),
        timestamp: new Date(),
        type: "thought",
        content: "Processing user request...",
      };
      setActivityLogs([...activityLogs, newLog]);
    }, 500);

    setTimeout(() => {
      const responseMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "I've received your message. This is a demo response - in a real implementation, this would be connected to the actual agent backend.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, responseMessage]);
      setIsLoading(false);
    }, 2000);
  };

  const currentAgent = mockAgents.find((a) => a.id === selectedAgent);

  return (
    <div className="h-[calc(100vh-0px)] flex flex-col">
      {/* Header */}
      <div className="h-14 border-b border-white/10 px-4 flex items-center justify-between shrink-0 glass">
        <div className="flex items-center gap-4">
          <Select value={selectedAgent} onValueChange={setSelectedAgent}>
            <SelectTrigger className="w-[200px] glass">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="glass">
              {mockAgents.map((agent) => (
                <SelectItem key={agent.id} value={agent.id} disabled={agent.status === "offline"}>
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      "w-2 h-2 rounded-full",
                      agent.status === "ready" ? "bg-[oklch(0.70_0.18_155)]" : "bg-muted-foreground/50"
                    )} />
                    {agent.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          {currentAgent && (
            <Badge 
              variant="outline" 
              className={cn(
                currentAgent.status === "ready" 
                  ? "border-[oklch(0.70_0.18_155/0.3)] text-[oklch(0.70_0.18_155)]"
                  : "border-muted-foreground/30 text-muted-foreground"
              )}
            >
              {currentAgent.status === "ready" ? "Ready" : "Offline"}
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button 
            variant="ghost" 
            size="icon"
            onClick={() => setShowActivityPanel(!showActivityPanel)}
          >
            {showActivityPanel ? (
              <PanelRightClose className="w-4 h-4" />
            ) : (
              <PanelRight className="w-4 h-4" />
            )}
          </Button>
          <Button variant="ghost" size="icon" onClick={() => toast("Settings coming soon")}>
            <Settings className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal">
          {/* Chat History Sidebar */}
          <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
            <div className="h-full border-r border-white/10 flex flex-col">
              <div className="p-3 border-b border-white/10">
                <Button className="w-full gap-2" size="sm" onClick={() => toast("New chat coming soon")}>
                  <Plus className="w-4 h-4" />
                  New Chat
                </Button>
              </div>
              <ScrollArea className="flex-1">
                <div className="p-2 space-y-1">
                  {mockConversations.map((conv) => (
                    <button
                      key={conv.id}
                      className="w-full text-left p-3 rounded-lg hover:bg-white/5 transition-colors"
                    >
                      <p className="text-sm font-medium truncate">{conv.title}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="secondary" className="text-xs">
                          {conv.agent}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{conv.time}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Chat Area */}
          <ResizablePanel defaultSize={showActivityPanel ? 50 : 80}>
            <div className="h-full flex flex-col">
              <ScrollArea className="flex-1 p-4">
                <div className="space-y-6 max-w-3xl mx-auto">
                  {messages.map((message) => (
                    <ChatMessage key={message.id} message={message} />
                  ))}
                  {isLoading && (
                    <div className="flex gap-3">
                      <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center">
                        <Bot className="w-4 h-4 text-accent" />
                      </div>
                      <div className="bg-white/5 border border-white/10 rounded-lg px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin text-accent" />
                          <span className="text-sm text-muted-foreground">Thinking...</span>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </ScrollArea>

              {/* Input Area */}
              <div className="p-4 border-t border-white/10">
                <div className="max-w-3xl mx-auto">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Send a message..."
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSend();
                        }
                      }}
                      className="glass"
                      disabled={isLoading || currentAgent?.status !== "ready"}
                    />
                    <Button 
                      onClick={handleSend} 
                      disabled={!inputValue.trim() || isLoading || currentAgent?.status !== "ready"}
                      className="gap-2"
                    >
                      <Send className="w-4 h-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2 text-center">
                    Press Enter to send, Shift+Enter for new line
                  </p>
                </div>
              </div>
            </div>
          </ResizablePanel>

          {showActivityPanel && (
            <>
              <ResizableHandle withHandle />

              {/* Activity Panel */}
              <ResizablePanel defaultSize={30} minSize={20} maxSize={40}>
                <div className="h-full border-l border-white/10 flex flex-col">
                  <Tabs defaultValue="activity" className="flex-1 flex flex-col">
                    <TabsList className="mx-3 mt-3 glass">
                      <TabsTrigger value="activity" className="gap-1.5">
                        <Terminal className="w-3.5 h-3.5" />
                        Activity
                      </TabsTrigger>
                      <TabsTrigger value="context" className="gap-1.5">
                        <Brain className="w-3.5 h-3.5" />
                        Context
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="activity" className="flex-1 overflow-hidden m-0">
                      <ScrollArea className="h-full">
                        <div className="p-3 space-y-1">
                          {activityLogs.map((log) => (
                            <ActivityLogItem key={log.id} log={log} />
                          ))}
                        </div>
                      </ScrollArea>
                    </TabsContent>

                    <TabsContent value="context" className="flex-1 overflow-hidden m-0">
                      <ScrollArea className="h-full">
                        <div className="p-3 space-y-4">
                          <div>
                            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                              <Sparkles className="w-4 h-4 text-primary" />
                              Active Skills
                            </h4>
                            <div className="space-y-1">
                              <Badge variant="secondary" className="mr-1">cluster-analysis</Badge>
                              <Badge variant="secondary" className="mr-1">report-generation</Badge>
                              <Badge variant="secondary" className="mr-1">alerting</Badge>
                            </div>
                          </div>

                          <div>
                            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                              <Wrench className="w-4 h-4 text-accent" />
                              Available Tools
                            </h4>
                            <div className="space-y-1 text-sm text-muted-foreground">
                              <p className="font-mono text-xs">get_cluster_nodes</p>
                              <p className="font-mono text-xs">get_pod_status</p>
                              <p className="font-mono text-xs">get_service_health</p>
                              <p className="font-mono text-xs">scale_deployment</p>
                              <p className="font-mono text-xs">get_logs</p>
                            </div>
                          </div>

                          <div>
                            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                              <FileText className="w-4 h-4 text-[oklch(0.75_0.15_85)]" />
                              Memory
                            </h4>
                            <p className="text-xs text-muted-foreground">
                              3 conversation turns in context
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Token usage: 1,847 / 32,768
                            </p>
                          </div>
                        </div>
                      </ScrollArea>
                    </TabsContent>
                  </Tabs>
                </div>
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>
    </div>
  );
}
