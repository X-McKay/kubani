import { useCallback, useState, useEffect } from 'react';
import { 
  ReactFlow, 
  Node, 
  Edge, 
  Controls, 
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  MarkerType,
  Panel
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  Play, 
  Pause, 
  RotateCcw, 
  Zap,
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle
} from 'lucide-react';
import { cn } from '@/lib/utils';

// Custom node types
const nodeTypes = {
  agent: AgentNode,
  task: TaskNode,
  tool: ToolNode,
};

interface AgentNodeData {
  label: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
  agent: string;
  duration?: number;
}

function AgentNode({ data }: { data: AgentNodeData }) {
  const statusConfig = {
    idle: { icon: Clock, color: 'text-muted-foreground', bg: 'bg-muted' },
    running: { icon: Zap, color: 'text-blue-500', bg: 'bg-blue-500/10' },
    completed: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-500/10' },
    failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10' },
  };

  const config = statusConfig[data.status];
  const Icon = config.icon;

  return (
    <div className={cn(
      "px-4 py-3 rounded-lg border-2 glass min-w-[200px]",
      data.status === 'running' && "border-blue-500 shadow-lg shadow-blue-500/20",
      data.status === 'completed' && "border-green-500",
      data.status === 'failed' && "border-red-500",
      data.status === 'idle' && "border-white/10"
    )}>
      <div className="flex items-center gap-2 mb-2">
        <div className={cn("p-1.5 rounded", config.bg)}>
          <Icon className={cn("w-4 h-4", config.color)} />
        </div>
        <div className="flex-1">
          <div className="font-semibold text-sm">{data.label}</div>
          <div className="text-xs text-muted-foreground">{data.agent}</div>
        </div>
      </div>
      {data.duration && (
        <div className="text-xs text-muted-foreground">
          {data.duration}ms
        </div>
      )}
    </div>
  );
}

function TaskNode({ data }: { data: { label: string; status: string } }) {
  return (
    <div className="px-3 py-2 rounded-md border border-white/10 glass bg-background/50 min-w-[150px]">
      <div className="text-sm font-medium">{data.label}</div>
      <Badge variant="outline" className="mt-1 text-xs">
        {data.status}
      </Badge>
    </div>
  );
}

function ToolNode({ data }: { data: { label: string; tool: string } }) {
  return (
    <div className="px-3 py-2 rounded border border-primary/30 glass bg-primary/5 min-w-[140px]">
      <div className="text-xs text-muted-foreground">{data.tool}</div>
      <div className="text-sm font-medium">{data.label}</div>
    </div>
  );
}

// Sample execution data
const initialNodes: Node[] = [
  {
    id: '1',
    type: 'agent',
    position: { x: 250, y: 50 },
    data: { 
      label: 'Initialize Request', 
      status: 'completed',
      agent: 'Core Agent',
      duration: 145
    },
  },
  {
    id: '2',
    type: 'task',
    position: { x: 250, y: 150 },
    data: { label: 'Parse User Intent', status: 'completed' },
  },
  {
    id: '3',
    type: 'agent',
    position: { x: 100, y: 250 },
    data: { 
      label: 'Query Cluster Status', 
      status: 'running',
      agent: 'K8s Monitor',
      duration: 892
    },
  },
  {
    id: '4',
    type: 'tool',
    position: { x: 100, y: 350 },
    data: { label: 'kubectl get nodes', tool: 'kubernetes-mcp' },
  },
  {
    id: '5',
    type: 'agent',
    position: { x: 400, y: 250 },
    data: { 
      label: 'Generate Response', 
      status: 'idle',
      agent: 'Core Agent'
    },
  },
  {
    id: '6',
    type: 'tool',
    position: { x: 400, y: 350 },
    data: { label: 'LLM Generation', tool: 'vllm' },
  },
];

const initialEdges: Edge[] = [
  { 
    id: 'e1-2', 
    source: '1', 
    target: '2',
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed }
  },
  { 
    id: 'e2-3', 
    source: '2', 
    target: '3',
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: '#3b82f6' }
  },
  { 
    id: 'e3-4', 
    source: '3', 
    target: '4',
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed }
  },
  { 
    id: 'e2-5', 
    source: '2', 
    target: '5',
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { strokeDasharray: '5,5' }
  },
  { 
    id: 'e5-6', 
    source: '5', 
    target: '6',
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { strokeDasharray: '5,5' }
  },
];

export default function Execution() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [isPlaying, setIsPlaying] = useState(true);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  // Simulate execution progress
  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      setNodes((nds) =>
        nds.map((node) => {
          if (node.type === 'agent' && node.data.status === 'running') {
            // Simulate duration increase
            return {
              ...node,
              data: {
                ...node.data,
                duration: (node.data.duration || 0) + Math.floor(Math.random() * 100),
              },
            };
          }
          return node;
        })
      );
    }, 500);

    return () => clearInterval(interval);
  }, [isPlaying, setNodes]);

  const handleReset = () => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  };

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="border-b border-white/10 glass">
        <div className="px-4 md:px-6 py-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
                Agent Execution
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                Real-time visualization of agent plans and execution
              </p>
            </div>
            
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsPlaying(!isPlaying)}
                className="glass"
              >
                {isPlaying ? (
                  <>
                    <Pause className="w-4 h-4 mr-2" />
                    Pause
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2" />
                    Resume
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
                className="glass"
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Reset
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Flow Canvas */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
          className="bg-background"
        >
          <Background className="opacity-20" />
          <Controls className="glass border border-white/10" />
          
          <Panel position="top-right" className="glass border border-white/10 rounded-lg p-3 space-y-2">
            <div className="text-xs font-semibold text-muted-foreground mb-2">Legend</div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded-full bg-blue-500" />
              <span>Running</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded-full bg-green-500" />
              <span>Completed</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded-full bg-red-500" />
              <span>Failed</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded-full bg-muted-foreground" />
              <span>Pending</span>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      {/* Stats Footer */}
      <div className="border-t border-white/10 glass">
        <div className="px-4 md:px-6 py-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">Total Steps</div>
              <div className="text-lg font-semibold">6</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Completed</div>
              <div className="text-lg font-semibold text-green-500">2</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Running</div>
              <div className="text-lg font-semibold text-blue-500">1</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Duration</div>
              <div className="text-lg font-semibold">1.2s</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
