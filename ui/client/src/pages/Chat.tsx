import { useState, useRef, useEffect, useCallback } from "react";
import {
  Bot,
  Send,
  Plus,
  ChevronDown,
  ChevronRight,
  Terminal,
  FileText,
  CheckCircle2,
  Loader2,
  Copy,
  PanelRightClose,
  PanelRight,
  Sparkles,
  Wrench,
  Brain,
  MessageSquare,
  RefreshCw,
  AlertCircle
} from "lucide-react";
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
import { fetchAgents, sendChatMessage, fetchTools, type Agent, type ChatMessage as ApiChatMessage } from "@/lib/api";

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

interface Conversation {
  id: string;
  title: string;
  agent: string;
  time: string;
  messages: Message[];
}

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
          <div className="prose prose-invert prose-sm max-w-none break-words overflow-hidden [&_pre]:overflow-x-auto [&_pre]:max-w-full [&_code]:break-all [&_p]:break-words">
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
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showActivityPanel, setShowActivityPanel] = useState(true);
  const [availableTools, setAvailableTools] = useState<Array<{ name: string; description: string }>>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch agents on mount
  useEffect(() => {
    async function loadAgents() {
      try {
        setAgentsLoading(true);
        setAgentsError(null);
        const fetchedAgents = await fetchAgents();
        setAgents(fetchedAgents);
        if (fetchedAgents.length > 0) {
          // Select first ready agent, or first agent if none ready
          const readyAgent = fetchedAgents.find(a => a.status === "ready");
          setSelectedAgent(readyAgent?.id || fetchedAgents[0].id);
        }
      } catch (err) {
        setAgentsError(err instanceof Error ? err.message : "Failed to load agents");
        // Set default agents for fallback
        const defaultAgents: Agent[] = [
          {
            id: "k8s-monitor",
            name: "Kubernetes Monitor",
            description: "Monitors cluster health",
            status: "ready",
            capabilities: [],
          },
          {
            id: "general",
            name: "Kubani Assistant",
            description: "General assistant",
            status: "ready",
            capabilities: [],
          },
        ];
        setAgents(defaultAgents);
        setSelectedAgent(defaultAgents[0].id);
      } finally {
        setAgentsLoading(false);
      }
    }
    loadAgents();
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Fetch available tools on mount
  useEffect(() => {
    fetchTools().then(setAvailableTools).catch(() => setAvailableTools([]));
  }, []);

  const addActivityLog = useCallback((type: ActivityLog["type"], content: string) => {
    const log: ActivityLog = {
      id: Date.now().toString(),
      timestamp: new Date(),
      type,
      content,
    };
    setActivityLogs(prev => [...prev, log]);
  }, []);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    // Add activity log for processing
    addActivityLog("thought", `Processing user request: "${inputValue.slice(0, 50)}${inputValue.length > 50 ? '...' : ''}"`);

    // Prepare messages for API (without timestamps and extra fields)
    const apiMessages: ApiChatMessage[] = [...messages, userMessage].map(m => ({
      role: m.role,
      content: m.content,
    }));

    try {
      addActivityLog("action", `Querying ${selectedAgent} agent (may use tools)...`);

      // Send message and wait for response (includes tool calls)
      const response = await sendChatMessage({
        messages: apiMessages,
        agentId: selectedAgent,
        stream: false,
      });

      // Create assistant message from response
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.content,
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);
      addActivityLog("result", "Response completed successfully");

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "An error occurred";
      addActivityLog("error", `Error: ${errorMessage}`);
      toast.error("Failed to get response", {
        description: errorMessage,
      });

      // Add error message to chat
      const errorResponse: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `Sorry, I encountered an error: ${errorMessage}. Please try again.`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorResponse]);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, messages, selectedAgent, addActivityLog]);

  const handleNewChat = useCallback(() => {
    // Save current conversation if it has messages
    if (messages.length > 0) {
      const newConversation: Conversation = {
        id: currentConversationId || Date.now().toString(),
        title: messages[0]?.content.slice(0, 30) + (messages[0]?.content.length > 30 ? "..." : "") || "New chat",
        agent: selectedAgent,
        time: "Just now",
        messages: [...messages],
      };
      setConversations(prev => {
        const existing = prev.find(c => c.id === newConversation.id);
        if (existing) {
          return prev.map(c => c.id === newConversation.id ? newConversation : c);
        }
        return [newConversation, ...prev];
      });
    }

    // Start new chat
    setMessages([]);
    setActivityLogs([]);
    setCurrentConversationId(Date.now().toString());
    toast("New chat started");
  }, [messages, selectedAgent, currentConversationId]);

  const handleLoadConversation = useCallback((conversation: Conversation) => {
    // Save current conversation first
    if (messages.length > 0 && currentConversationId) {
      const currentConversation: Conversation = {
        id: currentConversationId,
        title: messages[0]?.content.slice(0, 30) + "..." || "Chat",
        agent: selectedAgent,
        time: "Just now",
        messages: [...messages],
      };
      setConversations(prev => {
        const existing = prev.find(c => c.id === currentConversation.id);
        if (existing) {
          return prev.map(c => c.id === currentConversation.id ? currentConversation : c);
        }
        return prev;
      });
    }

    // Load selected conversation
    setMessages(conversation.messages);
    setCurrentConversationId(conversation.id);
    setSelectedAgent(conversation.agent);
    setActivityLogs([]);
  }, [messages, selectedAgent, currentConversationId]);

  const currentAgent = agents.find((a) => a.id === selectedAgent);

  return (
    <div className="h-[calc(100vh-0px)] flex flex-col">
      {/* Header */}
      <div className="h-14 border-b border-white/10 px-4 flex items-center justify-between shrink-0 glass">
        <div className="flex items-center gap-4">
          {agentsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading agents...</span>
            </div>
          ) : agentsError ? (
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="w-4 h-4" />
              <span className="text-sm">{agentsError}</span>
              <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
                <RefreshCw className="w-3 h-3 mr-1" />
                Retry
              </Button>
            </div>
          ) : (
            <>
              <Select value={selectedAgent} onValueChange={setSelectedAgent}>
                <SelectTrigger className="w-[200px] glass">
                  <SelectValue placeholder="Select an agent" />
                </SelectTrigger>
                <SelectContent className="glass">
                  {agents.map((agent) => (
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
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowActivityPanel(!showActivityPanel)}
            title={showActivityPanel ? "Hide activity panel" : "Show activity panel"}
          >
            {showActivityPanel ? (
              <PanelRightClose className="w-4 h-4" />
            ) : (
              <PanelRight className="w-4 h-4" />
            )}
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
                <Button className="w-full gap-2" size="sm" onClick={handleNewChat}>
                  <Plus className="w-4 h-4" />
                  New Chat
                </Button>
              </div>
              <ScrollArea className="flex-1">
                <div className="p-2 space-y-1">
                  {conversations.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No conversations yet
                    </p>
                  ) : (
                    conversations.map((conv) => (
                      <button
                        key={conv.id}
                        className={cn(
                          "w-full text-left p-3 rounded-lg hover:bg-white/5 transition-colors",
                          currentConversationId === conv.id && "bg-white/5"
                        )}
                        onClick={() => handleLoadConversation(conv)}
                      >
                        <p className="text-sm font-medium truncate">{conv.title}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge variant="secondary" className="text-xs">
                            {conv.agent}
                          </Badge>
                          <span className="text-xs text-muted-foreground">{conv.time}</span>
                        </div>
                      </button>
                    ))
                  )}
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
                  {messages.length === 0 && !streamingContent && (
                    <div className="text-center py-12">
                      <Bot className="w-12 h-12 text-accent/50 mx-auto mb-4" />
                      <h3 className="text-lg font-medium mb-2">Start a conversation</h3>
                      <p className="text-muted-foreground text-sm max-w-md mx-auto">
                        {currentAgent ? (
                          <>Ask <span className="text-accent">{currentAgent.name}</span> anything about {currentAgent.description?.toLowerCase() || "your cluster"}.</>
                        ) : (
                          "Select an agent to get started."
                        )}
                      </p>
                    </div>
                  )}
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
                      placeholder={currentAgent ? `Message ${currentAgent.name}...` : "Select an agent first..."}
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSend();
                        }
                      }}
                      className="glass"
                      disabled={isLoading || !currentAgent || currentAgent?.status !== "ready"}
                    />
                    <Button
                      onClick={handleSend}
                      disabled={!inputValue.trim() || isLoading || !currentAgent || currentAgent?.status !== "ready"}
                      className="gap-2"
                    >
                      {isLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
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
                          {activityLogs.length === 0 ? (
                            <p className="text-sm text-muted-foreground text-center py-4">
                              No activity yet
                            </p>
                          ) : (
                            activityLogs.map((log) => (
                              <ActivityLogItem key={log.id} log={log} />
                            ))
                          )}
                        </div>
                      </ScrollArea>
                    </TabsContent>

                    <TabsContent value="context" className="flex-1 overflow-hidden m-0">
                      <ScrollArea className="h-full">
                        <div className="p-3 space-y-4">
                          <div>
                            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                              <Bot className="w-4 h-4 text-accent" />
                              Current Agent
                            </h4>
                            {currentAgent ? (
                              <div className="space-y-1">
                                <p className="text-sm font-medium">{currentAgent.name}</p>
                                <p className="text-xs text-muted-foreground">{currentAgent.description}</p>
                              </div>
                            ) : (
                              <p className="text-xs text-muted-foreground">No agent selected</p>
                            )}
                          </div>

                          {currentAgent?.capabilities && currentAgent.capabilities.length > 0 && (
                            <div>
                              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                                <Sparkles className="w-4 h-4 text-primary" />
                                Capabilities
                              </h4>
                              <div className="space-y-1">
                                {currentAgent.capabilities.map((cap, i) => (
                                  <div key={i} className="text-xs">
                                    <span className="font-mono text-accent">{cap.name}</span>
                                    {cap.description && (
                                      <p className="text-muted-foreground mt-0.5">{cap.description}</p>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {availableTools.length > 0 && (
                            <div>
                              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                                <Wrench className="w-4 h-4 text-accent" />
                                Available Tools ({availableTools.length})
                              </h4>
                              <div className="space-y-1 max-h-[150px] overflow-y-auto">
                                {availableTools.slice(0, 10).map((tool, i) => (
                                  <div key={i} className="text-xs">
                                    <span className="font-mono text-accent">{tool.name}</span>
                                  </div>
                                ))}
                                {availableTools.length > 10 && (
                                  <p className="text-xs text-muted-foreground">
                                    +{availableTools.length - 10} more tools
                                  </p>
                                )}
                              </div>
                            </div>
                          )}

                          <div>
                            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                              <FileText className="w-4 h-4 text-[oklch(0.75_0.15_85)]" />
                              Conversation
                            </h4>
                            <p className="text-xs text-muted-foreground">
                              {messages.length} messages in current chat
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {conversations.length} saved conversations
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
