import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Loader2,
  Search,
  Filter,
  Eye,
  Play,
  Calendar,
  User,
  Zap
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface Task {
  id: string;
  name: string;
  agent: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startTime: string;
  duration?: string;
  user: string;
  description: string;
  logs?: string[];
}

// Sample task data
const sampleTasks: Task[] = [
  {
    id: 'task-001',
    name: 'Cluster Health Check',
    agent: 'K8s Monitor',
    status: 'completed',
    startTime: '2025-01-14 10:30:15',
    duration: '2.3s',
    user: 'admin',
    description: 'Performed comprehensive health check on all cluster nodes',
    logs: [
      '[10:30:15] Starting health check...',
      '[10:30:16] Checking node status...',
      '[10:30:17] All nodes healthy',
      '[10:30:17] Health check completed successfully'
    ]
  },
  {
    id: 'task-002',
    name: 'Deploy News Monitor',
    agent: 'Core Agent',
    status: 'running',
    startTime: '2025-01-14 10:35:42',
    user: 'admin',
    description: 'Deploying news monitoring agent to cluster',
    logs: [
      '[10:35:42] Preparing deployment manifest...',
      '[10:35:43] Creating namespace...',
      '[10:35:44] Deploying pods...',
      '[10:35:45] Waiting for pods to be ready...'
    ]
  },
  {
    id: 'task-003',
    name: 'Analyze Pod Logs',
    agent: 'K8s Monitor',
    status: 'pending',
    startTime: '2025-01-14 10:40:00',
    user: 'developer',
    description: 'Analyze logs from vllm pods for errors',
  },
  {
    id: 'task-004',
    name: 'Update Agent Config',
    agent: 'Core Agent',
    status: 'failed',
    startTime: '2025-01-14 09:15:30',
    duration: '0.8s',
    user: 'admin',
    description: 'Failed to update agent configuration',
    logs: [
      '[09:15:30] Reading configuration...',
      '[09:15:31] ERROR: Invalid configuration format',
      '[09:15:31] Task failed'
    ]
  },
  {
    id: 'task-005',
    name: 'Scale Deployment',
    agent: 'K8s Monitor',
    status: 'completed',
    startTime: '2025-01-14 09:00:12',
    duration: '5.1s',
    user: 'admin',
    description: 'Scaled llm-api deployment to 3 replicas',
    logs: [
      '[09:00:12] Scaling deployment...',
      '[09:00:13] Waiting for new pods...',
      '[09:00:17] All replicas ready',
      '[09:00:17] Scaling completed'
    ]
  },
];

const statusConfig = {
  pending: { 
    icon: Clock, 
    color: 'text-muted-foreground', 
    bg: 'bg-muted',
    label: 'Pending'
  },
  running: { 
    icon: Loader2, 
    color: 'text-blue-500', 
    bg: 'bg-blue-500/10',
    label: 'Running',
    animate: true
  },
  completed: { 
    icon: CheckCircle2, 
    color: 'text-green-500', 
    bg: 'bg-green-500/10',
    label: 'Completed'
  },
  failed: { 
    icon: XCircle, 
    color: 'text-red-500', 
    bg: 'bg-red-500/10',
    label: 'Failed'
  },
};

export default function Workflows() {
  const [tasks] = useState<Task[]>(sampleTasks);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const filteredTasks = tasks.filter(task => {
    const matchesSearch = task.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         task.agent.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || task.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const stats = {
    total: tasks.length,
    running: tasks.filter(t => t.status === 'running').length,
    completed: tasks.filter(t => t.status === 'completed').length,
    failed: tasks.filter(t => t.status === 'failed').length,
  };

  return (
    <div className="min-h-screen p-4 md:p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6 md:mb-8">
        <h1 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent mb-2">
          Workflows & Tasks
        </h1>
        <p className="text-sm text-muted-foreground">
          Track and monitor agent tasks and workflow executions
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mb-6">
        <Card className="glass p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Total Tasks</p>
              <p className="text-2xl font-bold">{stats.total}</p>
            </div>
            <Zap className="w-8 h-8 text-primary opacity-50" />
          </div>
        </Card>

        <Card className="glass p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Running</p>
              <p className="text-2xl font-bold text-blue-500">{stats.running}</p>
            </div>
            <Loader2 className="w-8 h-8 text-blue-500 opacity-50 animate-spin" />
          </div>
        </Card>

        <Card className="glass p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Completed</p>
              <p className="text-2xl font-bold text-green-500">{stats.completed}</p>
            </div>
            <CheckCircle2 className="w-8 h-8 text-green-500 opacity-50" />
          </div>
        </Card>

        <Card className="glass p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Failed</p>
              <p className="text-2xl font-bold text-red-500">{stats.failed}</p>
            </div>
            <XCircle className="w-8 h-8 text-red-500 opacity-50" />
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card className="glass p-4 mb-6">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search tasks..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 glass"
            />
          </div>
          
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-full md:w-[180px] glass">
              <Filter className="w-4 h-4 mr-2" />
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent className="glass">
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Card>

      {/* Tasks Table - Desktop */}
      <Card className="glass hidden md:block overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead>Task</TableHead>
              <TableHead>Agent</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Start Time</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>User</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredTasks.map((task) => {
              const config = statusConfig[task.status];
              const Icon = config.icon;
              
              return (
                <TableRow key={task.id} className="border-white/10">
                  <TableCell className="font-medium">{task.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="glass">
                      {task.agent}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className={cn("p-1 rounded", config.bg)}>
                        <Icon className={cn("w-3 h-3", config.color, config.animate && "animate-spin")} />
                      </div>
                      <span className={cn("text-sm", config.color)}>{config.label}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {task.startTime}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {task.duration || '-'}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {task.user}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedTask(task)}
                      className="glass"
                    >
                      <Eye className="w-4 h-4 mr-2" />
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      {/* Tasks List - Mobile */}
      <div className="md:hidden space-y-3">
        {filteredTasks.map((task) => {
          const config = statusConfig[task.status];
          const Icon = config.icon;
          
          return (
            <Card key={task.id} className="glass p-4">
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <h3 className="font-semibold mb-1">{task.name}</h3>
                  <Badge variant="outline" className="glass text-xs">
                    {task.agent}
                  </Badge>
                </div>
                <div className={cn("p-1.5 rounded", config.bg)}>
                  <Icon className={cn("w-4 h-4", config.color, config.animate && "animate-spin")} />
                </div>
              </div>
              
              <div className="space-y-2 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Calendar className="w-3 h-3" />
                  <span>{task.startTime}</span>
                </div>
                <div className="flex items-center gap-2">
                  <User className="w-3 h-3" />
                  <span>{task.user}</span>
                </div>
                {task.duration && (
                  <div className="flex items-center gap-2">
                    <Clock className="w-3 h-3" />
                    <span>{task.duration}</span>
                  </div>
                )}
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedTask(task)}
                className="w-full mt-3 glass"
              >
                <Eye className="w-4 h-4 mr-2" />
                View Details
              </Button>
            </Card>
          );
        })}
      </div>

      {/* Task Detail Dialog */}
      <Dialog open={!!selectedTask} onOpenChange={() => setSelectedTask(null)}>
        <DialogContent className="glass max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedTask && (
                <>
                  <Play className="w-5 h-5 text-primary" />
                  {selectedTask.name}
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {selectedTask?.description}
            </DialogDescription>
          </DialogHeader>

          {selectedTask && (
            <div className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Agent</p>
                  <Badge variant="outline" className="glass">
                    {selectedTask.agent}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Status</p>
                  <Badge className={cn(statusConfig[selectedTask.status].bg, statusConfig[selectedTask.status].color)}>
                    {statusConfig[selectedTask.status].label}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Start Time</p>
                  <p className="text-sm">{selectedTask.startTime}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Duration</p>
                  <p className="text-sm">{selectedTask.duration || 'In progress...'}</p>
                </div>
              </div>

              {selectedTask.logs && selectedTask.logs.length > 0 && (
                <div>
                  <p className="text-sm font-semibold mb-2">Execution Logs</p>
                  <Card className="glass p-3 bg-black/20">
                    <pre className="text-xs font-mono space-y-1">
                      {selectedTask.logs.map((log, i) => (
                        <div key={i} className="text-muted-foreground">
                          {log}
                        </div>
                      ))}
                    </pre>
                  </Card>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
