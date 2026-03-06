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
  PanelLeftClose,
  PanelLeft,
  Sparkles,
  Wrench,
  Brain,
  MessageSquare,
  RefreshCw,
  AlertCircle,
  Square,
  Trash2,
  FileCode,
  Database,
  Monitor,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
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
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/useMobile";
import { toast } from "sonner";
import { Streamdown } from "streamdown";
import { fetchAgents, streamChatMessageWithToolCalls, fetchTools, type Agent, type ChatMessage as ApiChatMessage } from "@/lib/api";
import { useArtifacts } from "./chat/hooks/useArtifacts";
import { useContextTracking } from "./chat/hooks/useContext";
import { ArtifactViewer } from "./chat/components/ArtifactViewer";
import { ContextPanel } from "./chat/components/ContextPanel";
import { extractResourceName } from "./chat/artifact-parser";
import { ScreenViewer } from "./chat/components/ScreenViewer";

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
  const [isOpen, setIsOpen] = useState(true); // Default open like Factory.ai

  const statusColors = {
    pending: "text-muted-foreground",
    running: "text-primary",
    completed: "text-success",
    failed: "text-destructive",
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="my-2 rounded border border-border bg-background overflow-hidden">
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center gap-2 px-3 py-2 hover:bg-secondary/50 transition-colors">
            {isOpen ? (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
            )}
            <Terminal className="w-3.5 h-3.5 text-primary" />
            <span className="font-mono text-xs text-primary">{toolCall.name}</span>
            <div className={cn("ml-auto flex items-center gap-1.5 text-xs font-mono uppercase", statusColors[toolCall.status])}>
              {toolCall.status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
              {toolCall.status === "completed" && <CheckCircle2 className="w-3 h-3" />}
              {toolCall.status}
            </div>
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t border-border">
            <div className="px-3 py-2 border-b border-border/50">
              <p className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wide">Input</p>
              <pre className="text-xs font-mono text-foreground/80 bg-black/30 p-2 rounded overflow-x-auto">
                {JSON.stringify(toolCall.arguments, null, 2)}
              </pre>
            </div>
            {toolCall.result && (
              <div className="px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Output</p>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    onClick={() => {
                      navigator.clipboard.writeText(toolCall.result || "");
                      toast("Copied to clipboard");
                    }}
                  >
                    <Copy className="w-3 h-3" />
                  </Button>
                </div>
                <pre className="text-xs font-mono text-foreground/80 bg-black/30 p-2 rounded overflow-x-auto max-h-[200px]">
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
    <div className="animate-slide-up">
      {/* Message header - Factory.ai style */}
      <div className="flex items-center gap-2 mb-2">
        <div className={cn(
          "w-6 h-6 rounded flex items-center justify-center shrink-0",
          isUser ? "bg-primary/15" : "bg-card-elevated"
        )}>
          {isUser ? (
            <MessageSquare className="w-3.5 h-3.5 text-primary" />
          ) : (
            <Bot className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </div>
        <span className="text-xs font-medium text-foreground">
          {isUser ? "You" : "Assistant"}
        </span>
        <span className="text-xs text-muted-foreground font-mono">
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </div>

      {/* Message content */}
      <div className="pl-8">
        {/* Tool calls rendered first, like Factory.ai */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-3 space-y-2">
            {message.toolCalls.map((tc) => (
              <ToolCallBlock key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Text content */}
        {message.content && (
          <div className="prose prose-invert prose-sm max-w-none break-words overflow-hidden [&_pre]:overflow-x-auto [&_pre]:max-w-full [&_pre]:bg-black/30 [&_pre]:border [&_pre]:border-border [&_pre]:rounded [&_code]:break-all [&_code]:text-primary [&_p]:break-words [&_p]:text-foreground/90">
            <Streamdown>{message.content}</Streamdown>
          </div>
        )}
      </div>
    </div>
  );
}

const THINKING_PHRASES = [
  "Thinking",
  "Reasoning",
  "Analyzing",
  "Considering",
];

function ThinkingIndicator({ agentName, hasContent, hasToolCalls }: {
  agentName?: string;
  hasContent: boolean;
  hasToolCalls: boolean;
}) {
  const [phraseIndex, setPhraseIndex] = useState(0);

  useEffect(() => {
    if (hasContent || hasToolCalls) return;
    const interval = setInterval(() => {
      setPhraseIndex(i => (i + 1) % THINKING_PHRASES.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [hasContent, hasToolCalls]);

  // Don't show if there's already content or tool calls visible
  if (hasContent || hasToolCalls) return null;

  const statusText = THINKING_PHRASES[phraseIndex];

  return (
    <div className="animate-slide-up">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-6 h-6 rounded flex items-center justify-center bg-card-elevated">
          <Bot className="w-3.5 h-3.5 text-muted-foreground" />
        </div>
        <span className="text-xs font-medium text-foreground">
          {agentName || "Assistant"}
        </span>
      </div>
      <div className="pl-8">
        <div className="flex items-center gap-2.5">
          <Spinner className="size-3.5 text-primary" />
          <span className="text-xs text-muted-foreground font-mono animate-pulse">
            {statusText}...
          </span>
        </div>
      </div>
    </div>
  );
}

function ActivityLogItem({ log }: { log: ActivityLog }) {
  const icons = {
    thought: <Brain className="w-3 h-3" />,
    action: <Wrench className="w-3 h-3" />,
    result: <CheckCircle2 className="w-3 h-3" />,
    error: <AlertCircle className="w-3 h-3" />,
  };

  const colors = {
    thought: "text-primary border-primary/30",
    action: "text-info border-info/30",
    result: "text-success border-success/30",
    error: "text-destructive border-destructive/30",
  };

  return (
    <div className={cn("pl-2 py-1.5 border-l-2", colors[log.type])}>
      <div className="flex items-center gap-1.5">
        {icons[log.type]}
        <span className="text-[10px] font-mono uppercase tracking-wide">{log.type}</span>
        <span className="text-[10px] text-muted-foreground font-mono ml-auto">
          {log.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </div>
      <p className="text-xs text-muted-foreground mt-0.5 pl-4">{log.content}</p>
    </div>
  );
}

// Dynamic routing agent - uses LLM with MCP tools and routes to specific agents when needed
const DYNAMIC_AGENT: Agent = {
  id: "dynamic",
  name: "Dynamic (Auto-route)",
  description: "Uses LLM with MCP tools for general questions, routes to specialized agents when appropriate",
  status: "ready",
  capabilities: [
    { name: "auto-routing", description: "Automatically routes to the best agent for the task" },
    { name: "general-chat", description: "Handles general questions using available MCP tools" },
  ],
};

export default function Chat() {
  const computerMcpNoVncUrl = import.meta.env.VITE_COMPUTER_NOVNC_URL || null;

  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>("nexus");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showLeftPanel, setShowLeftPanel] = useState(false);
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [historySheetOpen, setHistorySheetOpen] = useState(false);
  const [rightSheetOpen, setRightSheetOpen] = useState(false);
  const [availableTools, setAvailableTools] = useState<Array<{ name: string; description: string }>>([]);
  const isMobile = useIsMobile();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Factory.ai-style artifact and context tracking
  const {
    artifacts,
    activeArtifactId,
    setActiveArtifactId,
    addArtifact,
    closeArtifact,
    clearArtifacts,
  } = useArtifacts();

  const { contextItems, addContextItem, clearContext } = useContextTracking();

  // Load conversations from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("kubani-conversations");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Convert date strings back to Date objects
        const restored = parsed.map((conv: Conversation) => ({
          ...conv,
          messages: conv.messages.map((m: Message) => ({
            ...m,
            timestamp: new Date(m.timestamp)
          }))
        }));
        setConversations(restored);
      } catch {
        // Invalid data, ignore
      }
    }
  }, []);

  // Save conversations to localStorage when they change
  useEffect(() => {
    if (conversations.length > 0) {
      localStorage.setItem("kubani-conversations", JSON.stringify(conversations));
    }
  }, [conversations]);

  // Fetch agents on mount
  useEffect(() => {
    async function loadAgents() {
      try {
        setAgentsLoading(true);
        setAgentsError(null);
        const fetchedAgents = await fetchAgents();
        // Add dynamic agent at the beginning
        setAgents([DYNAMIC_AGENT, ...fetchedAgents]);
        // Default to Nexus agent
        setSelectedAgent("nexus");
      } catch (err) {
        setAgentsError(err instanceof Error ? err.message : "Failed to load agents");
        // Set default agents for fallback (with dynamic agent)
        const defaultAgents: Agent[] = [
          DYNAMIC_AGENT,
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
        setSelectedAgent("nexus");
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

    // Create AbortController for stop functionality
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Add activity log for processing
    addActivityLog("thought", `Processing user request: "${inputValue.slice(0, 50)}${inputValue.length > 50 ? '...' : ''}"`);

    // Prepare messages for API (without timestamps and extra fields)
    const apiMessages: ApiChatMessage[] = [...messages, userMessage].map(m => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const agentName = selectedAgent === "dynamic" ? "Dynamic (LLM + MCP)" : selectedAgent;
      addActivityLog("action", `Querying ${agentName} agent (streaming response)...`);

      // Create assistant message placeholder for streaming
      const assistantMessageId = (Date.now() + 1).toString();
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        toolCalls: [],
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Track tool calls by ID (from backend)
      const toolCallsById: Map<string, ToolCall> = new Map();

      // Stream the response and update the message as chunks arrive
      let fullContent = "";
      for await (const chunk of streamChatMessageWithToolCalls({
        messages: apiMessages,
        agentId: selectedAgent,
        stream: true,
      }, abortController.signal)) {
        if (chunk.type === "content" && chunk.content) {
          fullContent += chunk.content;
          setMessages(prev => prev.map(m =>
            m.id === assistantMessageId
              ? { ...m, content: fullContent }
              : m
          ));
        } else if (chunk.type === "tool_call" && chunk.toolCall) {
          // Backend sends complete tool call info
          const tc = chunk.toolCall;
          const toolId = tc.id || `tool-${tc.index}`;

          let parsedArgs: Record<string, unknown> = {};
          try {
            if (tc.function?.arguments) {
              parsedArgs = JSON.parse(tc.function.arguments);
            }
          } catch {
            parsedArgs = { raw: tc.function?.arguments || "" };
          }

          const newToolCall: ToolCall = {
            id: toolId,
            name: tc.function?.name || "unknown",
            arguments: parsedArgs,
            status: "pending",
          };
          toolCallsById.set(toolId, newToolCall);
          addActivityLog("action", `Tool requested: ${newToolCall.name}`);

          // Update message with current tool calls
          setMessages(prev => prev.map(m =>
            m.id === assistantMessageId
              ? { ...m, toolCalls: Array.from(toolCallsById.values()) }
              : m
          ));
        } else if (chunk.type === "tool_start" && chunk.toolExecution) {
          // Tool execution starting
          const { id, name } = chunk.toolExecution;
          const existing = toolCallsById.get(id);
          if (existing) {
            existing.status = "running";
            toolCallsById.set(id, existing);
          } else {
            // Create new tool call if we haven't seen it yet
            toolCallsById.set(id, {
              id,
              name: name || "unknown",
              arguments: {},
              status: "running",
            });
          }
          addActivityLog("action", `Executing tool: ${name || id}`);

          setMessages(prev => prev.map(m =>
            m.id === assistantMessageId
              ? { ...m, toolCalls: Array.from(toolCallsById.values()) }
              : m
          ));
        } else if (chunk.type === "tool_complete" && chunk.toolExecution) {
          // Tool execution completed
          const { id, result } = chunk.toolExecution;
          const existing = toolCallsById.get(id);
          if (existing) {
            existing.status = "completed";
            existing.result = result;
            toolCallsById.set(id, existing);
            addActivityLog("result", `Tool completed: ${existing.name}`);

            // Add artifact from tool result (Factory.ai-style)
            if (result) {
              addArtifact(id, existing.name, result);

              // Track context
              addContextItem({
                type: "resource",
                name: extractResourceName(existing.name, result),
                accessedAt: new Date(),
                toolCallId: id,
              });
            }
          }

          setMessages(prev => prev.map(m =>
            m.id === assistantMessageId
              ? { ...m, toolCalls: Array.from(toolCallsById.values()) }
              : m
          ));
        } else if (chunk.type === "tool_error" && chunk.toolExecution) {
          // Tool execution failed
          const { id, error } = chunk.toolExecution;
          const existing = toolCallsById.get(id);
          if (existing) {
            existing.status = "failed";
            existing.result = `Error: ${error}`;
            toolCallsById.set(id, existing);
            addActivityLog("error", `Tool failed: ${existing.name} - ${error}`);
          }

          setMessages(prev => prev.map(m =>
            m.id === assistantMessageId
              ? { ...m, toolCalls: Array.from(toolCallsById.values()) }
              : m
          ));
        } else if (chunk.type === "error" && chunk.error) {
          addActivityLog("error", `Error: ${chunk.error}`);
          toast.error("Error from agent", { description: chunk.error });
        } else if (chunk.type === "conversation_id" && chunk.conversationId) {
          addActivityLog("thought", `Nexus conversation: ${chunk.conversationId.slice(0, 8)}...`);
        } else if (chunk.type === "done") {
          addActivityLog("result", "Response completed successfully");
        }
      }

    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        addActivityLog("thought", "Generation stopped by user");
        toast("Generation stopped");
      } else {
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
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [inputValue, isLoading, messages, selectedAgent, addActivityLog, addArtifact, addContextItem]);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  const handleClearHistory = useCallback(() => {
    setConversations([]);
    localStorage.removeItem("kubani-conversations");
    toast("Chat history cleared");
  }, []);

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
    clearArtifacts();
    clearContext();
    setCurrentConversationId(Date.now().toString());
    toast("New chat started");
  }, [messages, selectedAgent, currentConversationId, clearArtifacts, clearContext]);

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
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Header - Factory.ai style */}
      <div className="h-12 border-b border-border px-4 flex items-center justify-between shrink-0 bg-card">
        <div className="flex items-center gap-3">
          <h1 className="text-xs font-semibold text-foreground uppercase tracking-wide">Chat</h1>
          <span className="text-border">|</span>
          {agentsLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span className="text-xs font-mono">Loading...</span>
            </div>
          ) : agentsError ? (
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="w-3.5 h-3.5" />
              <span className="text-xs">{agentsError}</span>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => window.location.reload()}>
                <RefreshCw className="w-3 h-3 mr-1" />
                Retry
              </Button>
            </div>
          ) : (
            <>
              <Select value={selectedAgent} onValueChange={setSelectedAgent}>
                <SelectTrigger className={cn("h-7 text-xs bg-secondary border-border", isMobile ? "w-[130px]" : "w-[180px]")}>
                  <SelectValue placeholder="Select agent" />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {agents.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id} disabled={agent.status === "offline"} className="text-xs">
                      <div className="flex items-center gap-2">
                        <div className={cn(
                          "w-1.5 h-1.5 rounded-full",
                          (agent.status === "ready" || agent.status === "healthy") ? "bg-success" : "bg-muted-foreground/50"
                        )} />
                        {agent.name}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {currentAgent && (
                <span className={cn(
                  "text-xs font-mono uppercase",
                  (currentAgent.status === "ready" || currentAgent.status === "healthy")
                    ? "text-success"
                    : "text-muted-foreground"
                )}>
                  {(currentAgent.status === "ready" || currentAgent.status === "healthy") ? "● Ready" : "○ Offline"}
                </span>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs font-mono"
            onClick={() => isMobile ? setHistorySheetOpen(true) : setShowLeftPanel(!showLeftPanel)}
            title={showLeftPanel ? "Hide conversations" : "Show conversations"}
          >
            {showLeftPanel && !isMobile ? (
              <><PanelLeftClose className="w-3.5 h-3.5 mr-1" />{!isMobile && " History"}</>
            ) : (
              <><PanelLeft className="w-3.5 h-3.5 mr-1" />{!isMobile && " History"}</>
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs font-mono"
            onClick={() => isMobile ? setRightSheetOpen(true) : setShowRightPanel(!showRightPanel)}
            title={showRightPanel ? "Hide panel" : "Show panel"}
          >
            {showRightPanel && !isMobile ? (
              <><PanelRightClose className="w-3.5 h-3.5 mr-1" />{!isMobile && " Panel"}</>
            ) : (
              <><PanelRight className="w-3.5 h-3.5 mr-1" />{!isMobile && " Panel"}</>
            )}
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        {(() => {
          // Shared sidebar content (used in both desktop ResizablePanel and mobile Sheet)
          const sidebarContent = (
            <div className="h-full flex flex-col bg-card">
              <div className="p-2 border-b border-border flex items-center gap-2">
                <Button className="flex-1 gap-1.5 h-7 text-xs" size="sm" onClick={handleNewChat}>
                  <Plus className="w-3.5 h-3.5" />
                  New
                </Button>
                {conversations.length > 0 && (
                  <Button
                    variant="ghost"
                    className="h-7 px-2 text-muted-foreground hover:text-destructive"
                    size="sm"
                    onClick={handleClearHistory}
                    title="Clear history"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
              <ScrollArea className="flex-1">
                <div className="p-1">
                  {conversations.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-6">
                      No conversations
                    </p>
                  ) : (
                    conversations.map((conv) => (
                      <button
                        key={conv.id}
                        className={cn(
                          "w-full text-left px-2 py-2 rounded hover:bg-secondary/50 transition-colors",
                          currentConversationId === conv.id && "bg-primary/10"
                        )}
                        onClick={() => {
                          handleLoadConversation(conv);
                          if (isMobile) setHistorySheetOpen(false);
                        }}
                      >
                        <p className="text-xs font-medium truncate text-foreground">{conv.title}</p>
                        <div className="flex items-center gap-1.5 mt-1">
                          <span className="text-[10px] font-mono text-primary">{conv.agent}</span>
                          <span className="text-[10px] text-muted-foreground">· {conv.time}</span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          );

          // Shared right panel content (used in both desktop ResizablePanel and mobile Sheet)
          const rightPanelContent = (
            <div className="h-full flex flex-col bg-card">
              <Tabs defaultValue="artifacts" className="flex-1 flex flex-col">
                <div className="px-2 pt-2 border-b border-border">
                  <TabsList className="h-7 p-0.5 bg-secondary">
                    <TabsTrigger value="artifacts" className="gap-1 h-6 text-xs px-2 data-[state=active]:bg-card">
                      <FileCode className="w-3 h-3" />
                      Artifacts
                      {artifacts.length > 0 && (
                        <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                          {artifacts.length}
                        </Badge>
                      )}
                    </TabsTrigger>
                    <TabsTrigger value="context" className="gap-1 h-6 text-xs px-2 data-[state=active]:bg-card">
                      <Database className="w-3 h-3" />
                      Context
                    </TabsTrigger>
                    <TabsTrigger value="log" className="gap-1 h-6 text-xs px-2 data-[state=active]:bg-card">
                      <Terminal className="w-3 h-3" />
                      Log
                    </TabsTrigger>
                    <TabsTrigger value="screen" className="gap-1 h-6 text-xs px-2 data-[state=active]:bg-card">
                      <Monitor className="w-3 h-3" />
                      Screen
                    </TabsTrigger>
                  </TabsList>
                </div>

                <TabsContent value="artifacts" className="flex-1 overflow-hidden m-0">
                  <ArtifactViewer
                    artifacts={artifacts}
                    activeArtifactId={activeArtifactId}
                    onArtifactSelect={setActiveArtifactId}
                    onClose={closeArtifact}
                  />
                </TabsContent>

                <TabsContent value="context" className="flex-1 overflow-hidden m-0">
                  <ContextPanel
                    contextItems={contextItems}
                    currentAgent={currentAgent ? {
                      id: currentAgent.id,
                      name: currentAgent.name,
                      description: currentAgent.description
                    } : null}
                    availableTools={availableTools}
                  />
                </TabsContent>

                <TabsContent value="log" className="flex-1 overflow-hidden m-0">
                  <ScrollArea className="h-full">
                    <div className="p-2 space-y-0.5">
                      {activityLogs.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-6 font-mono">
                          No activity
                        </p>
                      ) : (
                        activityLogs.map((log) => (
                          <ActivityLogItem key={log.id} log={log} />
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="screen" className="flex-1 overflow-hidden m-0">
                  <ScreenViewer novncUrl={computerMcpNoVncUrl} />
                </TabsContent>
              </Tabs>
            </div>
          );

          // Shared chat area content (messages + input)
          const chatAreaContent = (
            <div className="h-full flex flex-col bg-background">
              <ScrollArea className="flex-1 min-h-0">
                <div className="space-y-4 max-w-4xl mx-auto p-4">
                  {messages.length === 0 && !isLoading && (
                    <div className="text-center py-16">
                      <div className="w-10 h-10 rounded bg-card-elevated flex items-center justify-center mx-auto mb-4">
                        <Terminal className="w-5 h-5 text-muted-foreground" />
                      </div>
                      <h3 className="text-sm font-medium mb-1 text-foreground">Ready</h3>
                      <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                        {currentAgent ? (
                          <>Connected to <span className="text-primary font-mono">{currentAgent.name}</span></>
                        ) : (
                          "Select an agent to begin"
                        )}
                      </p>
                    </div>
                  )}
                  {messages.map((message) => (
                    <ChatMessage key={message.id} message={message} />
                  ))}
                  {isLoading && (
                    <ThinkingIndicator
                      agentName={currentAgent?.name}
                      hasContent={!!(messages[messages.length - 1]?.role === "assistant" && messages[messages.length - 1]?.content)}
                      hasToolCalls={!!(messages[messages.length - 1]?.role === "assistant" && messages[messages.length - 1]?.toolCalls?.length)}
                    />
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </ScrollArea>

              {/* Input Area - pinned to bottom */}
              <div className="shrink-0 p-3 border-t border-border bg-card">
                <div className="max-w-4xl mx-auto">
                  <div className="flex gap-2">
                    <Input
                      placeholder={currentAgent ? `Message ${currentAgent.name}...` : "Select an agent..."}
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSend();
                        }
                      }}
                      className="h-9 text-sm bg-background border-border"
                      disabled={isLoading || !currentAgent || (currentAgent?.status !== "ready" && currentAgent?.status !== "healthy")}
                    />
                    {isLoading ? (
                      <Button
                        onClick={handleStop}
                        variant="destructive"
                        size="sm"
                        className="h-9 gap-1.5 text-xs font-mono"
                      >
                        <Square className="w-3.5 h-3.5" />
                        Stop
                      </Button>
                    ) : (
                      <Button
                        onClick={handleSend}
                        disabled={!inputValue.trim() || !currentAgent || (currentAgent?.status !== "ready" && currentAgent?.status !== "healthy")}
                        size="sm"
                        className="h-9 gap-1.5 text-xs font-mono"
                      >
                        <Send className="w-3.5 h-3.5" />
                        Send
                      </Button>
                    )}
                  </div>
                  {!isMobile && (
                    <p className="text-[10px] text-muted-foreground mt-1.5 text-center font-mono">
                      ↵ send · ⇧↵ newline
                    </p>
                  )}
                </div>
              </div>
            </div>
          );

          if (isMobile) {
            return (
              <>
                {/* Mobile: History Sheet (left side) */}
                <Sheet open={historySheetOpen} onOpenChange={setHistorySheetOpen}>
                  <SheetContent side="left" className="w-[85%] p-0">
                    <SheetHeader className="px-4 py-3 border-b border-border">
                      <SheetTitle className="text-xs font-semibold uppercase tracking-wide">History</SheetTitle>
                    </SheetHeader>
                    {sidebarContent}
                  </SheetContent>
                </Sheet>

                {/* Mobile: Right Panel Sheet */}
                <Sheet open={rightSheetOpen} onOpenChange={setRightSheetOpen}>
                  <SheetContent side="right" className="w-[90%] sm:max-w-md p-0">
                    <SheetHeader className="px-4 py-3 border-b border-border">
                      <SheetTitle className="text-xs font-semibold uppercase tracking-wide">Panel</SheetTitle>
                    </SheetHeader>
                    {rightPanelContent}
                  </SheetContent>
                </Sheet>

                {/* Mobile: Full-width chat area */}
                {chatAreaContent}
              </>
            );
          }

          // Desktop: Original ResizablePanelGroup layout
          return (
            <ResizablePanelGroup direction="horizontal">
              {/* Chat History Sidebar */}
              {showLeftPanel && (
                <>
                  <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
                    <div className="h-full border-r border-border">
                      {sidebarContent}
                    </div>
                  </ResizablePanel>
                  <ResizableHandle withHandle />
                </>
              )}

              {/* Chat Area */}
              <ResizablePanel defaultSize={showLeftPanel && showRightPanel ? 50 : showLeftPanel || showRightPanel ? 65 : 100}>
                {chatAreaContent}
              </ResizablePanel>

              {showRightPanel && (
                <>
                  <ResizableHandle withHandle />
                  {/* Right Panel */}
                  <ResizablePanel defaultSize={35} minSize={25} maxSize={50}>
                    <div className="h-full border-l border-border">
                      {rightPanelContent}
                    </div>
                  </ResizablePanel>
                </>
              )}
            </ResizablePanelGroup>
          );
        })()}
      </div>
    </div>
  );
}
