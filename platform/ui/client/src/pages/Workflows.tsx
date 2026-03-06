import { useState, useEffect, useCallback } from 'react';
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
  Zap,
  RefreshCw,
  Workflow,
  ArrowLeft,
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

interface WorkflowDetail {
  id: string;
  run_id?: string;
  workflow_type: string;
  status: string;
  startTime?: string;
  closeTime?: string;
  taskQueue: string;
  duration?: string;
  events: WorkflowEvent[];
}

interface WorkflowEvent {
  eventId: number;
  eventType: string;
  timestamp?: string;
}

const statusConfig = {
  pending: {
    icon: Clock,
    color: 'text-muted-foreground',
    bg: 'bg-muted',
    label: 'Pending',
    animate: false
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
    label: 'Completed',
    animate: false
  },
  failed: {
    icon: XCircle,
    color: 'text-red-500',
    bg: 'bg-red-500/10',
    label: 'Failed',
    animate: false
  },
};

function getEventDotColor(eventType: string): string {
  const upper = eventType.toUpperCase();
  if (upper.includes('STARTED') || upper.includes('COMPLETED')) return 'bg-green-500';
  if (upper.includes('FAILED') || upper.includes('TIMED_OUT') || upper.includes('TERMINATED') || upper.includes('CANCELED')) return 'bg-red-500';
  if (upper.includes('ACTIVITY') || upper.includes('SCHEDULED')) return 'bg-blue-500';
  return 'bg-gray-500';
}

function formatEventType(eventType: string): string {
  return eventType
    .replace(/^EVENT_TYPE_/, '')
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}

function WorkflowEventTimeline({ events }: { events: WorkflowEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No events recorded.</p>
    );
  }

  return (
    <div className="relative">
      {events.map((event, index) => {
        const dotColor = getEventDotColor(event.eventType);
        const isLast = index === events.length - 1;

        return (
          <div key={event.eventId} className="relative flex gap-4 pb-4">
            {/* Vertical line */}
            {!isLast && (
              <div className="absolute left-[7px] top-4 bottom-0 w-px bg-white/10" />
            )}
            {/* Dot */}
            <div className={cn('w-[15px] h-[15px] rounded-full mt-0.5 shrink-0', dotColor)} />
            {/* Content */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{formatEventType(event.eventType)}</p>
              {event.timestamp && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {new Date(event.timestamp).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Workflows() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [workflowDetail, setWorkflowDetail] = useState<WorkflowDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Fetch workflows data
  const fetchData = useCallback(async () => {
    try {
      const response = await fetch('/api/workflows');
      if (response.ok) {
        const data = await response.json();
        setTasks(data);
      }
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh list every 30 seconds when no task is selected
  useEffect(() => {
    if (!selectedTask) {
      const interval = setInterval(fetchData, 30000);
      return () => clearInterval(interval);
    }
  }, [selectedTask, fetchData]);

  // Fetch workflow detail when a task is selected
  useEffect(() => {
    if (selectedTask) {
      setDetailLoading(true);
      setWorkflowDetail(null);
      fetch(`/api/workflows/${encodeURIComponent(selectedTask.id)}`)
        .then(res => res.json())
        .then(data => {
          if (!data.error) setWorkflowDetail(data);
        })
        .catch(console.error)
        .finally(() => setDetailLoading(false));
    } else {
      setWorkflowDetail(null);
    }
  }, [selectedTask]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

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
      <div className="flex items-center justify-between mb-6 md:mb-8">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent mb-2">
            Workflows & Tasks
          </h1>
          <p className="text-sm text-muted-foreground">
            Track and monitor agent tasks and workflow executions
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing}
          className="glass"
        >
          <RefreshCw className={cn("w-4 h-4 mr-2", refreshing && "animate-spin")} />
          Refresh
        </Button>
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
            <Loader2 className={cn("w-8 h-8 text-blue-500 opacity-50", stats.running > 0 && "animate-spin")} />
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

      {/* Workflow Detail View */}
      {selectedTask ? (
        <Card className="glass p-6">
          {/* Detail Header */}
          <div className="flex items-center gap-3 mb-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedTask(null)}
              className="glass"
            >
              <ArrowLeft className="w-4 h-4 mr-1" />
              Back
            </Button>
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold truncate">{selectedTask.name}</h2>
            </div>
            <Badge className={cn(statusConfig[selectedTask.status].bg, statusConfig[selectedTask.status].color)}>
              {statusConfig[selectedTask.status].label}
            </Badge>
          </div>

          {detailLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <span className="ml-3 text-muted-foreground">Loading workflow details...</span>
            </div>
          )}

          {!detailLoading && workflowDetail && (
            <div className="space-y-6">
              {/* Info Grid */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Workflow Type</p>
                  <p className="text-sm font-medium">{workflowDetail.workflow_type}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Task Queue</p>
                  <p className="text-sm font-medium">{workflowDetail.taskQueue}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Status</p>
                  <p className="text-sm font-medium">{workflowDetail.status}</p>
                </div>
                {workflowDetail.startTime && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Start Time</p>
                    <p className="text-sm">{new Date(workflowDetail.startTime).toLocaleString()}</p>
                  </div>
                )}
                {workflowDetail.closeTime && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Close Time</p>
                    <p className="text-sm">{new Date(workflowDetail.closeTime).toLocaleString()}</p>
                  </div>
                )}
                {workflowDetail.duration && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Duration</p>
                    <p className="text-sm">{workflowDetail.duration}</p>
                  </div>
                )}
              </div>

              {/* Event Timeline */}
              <div>
                <h3 className="text-sm font-semibold mb-3">Event Timeline</h3>
                <Card className="glass p-4 bg-black/20">
                  <WorkflowEventTimeline events={workflowDetail.events} />
                </Card>
              </div>
            </div>
          )}

          {!detailLoading && !workflowDetail && (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground">
                Could not load workflow details.
              </p>
            </div>
          )}
        </Card>
      ) : (
        <>
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

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <span className="ml-3 text-muted-foreground">Loading workflows...</span>
            </div>
          )}

          {/* Empty State */}
          {!loading && tasks.length === 0 && (
            <Card className="glass p-8 text-center">
              <Workflow className="w-16 h-16 mx-auto text-muted-foreground/50 mb-4" />
              <h3 className="text-lg font-semibold mb-2">No workflows yet</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Workflow executions will appear here once agents start running tasks.
              </p>
              <Button variant="outline" onClick={handleRefresh} className="glass">
                <RefreshCw className="w-4 h-4 mr-2" />
                Check for workflows
              </Button>
            </Card>
          )}

          {/* Tasks Table - Desktop */}
          {!loading && tasks.length > 0 && (
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
          )}

          {/* Tasks List - Mobile */}
          {!loading && tasks.length > 0 && (
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
          )}
        </>
      )}
    </div>
  );
}
