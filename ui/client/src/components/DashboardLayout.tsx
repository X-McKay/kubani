import { ReactNode, useState } from "react";
import { Link, useLocation } from "wouter";
import { 
  Activity, 
  Database, 
  MessageSquare, 
  ChevronLeft,
  ChevronRight,
  Command,
  Settings,
  HelpCircle,
  Boxes
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface DashboardLayoutProps {
  children: ReactNode;
}

const navItems = [
  { path: "/monitoring", icon: Activity, label: "Monitoring", description: "Cluster health & metrics" },
  { path: "/registry", icon: Database, label: "Registry", description: "Agents, MCP servers, skills" },
  { path: "/chat", icon: MessageSquare, label: "Chat", description: "Interact with agents" },
];

const bottomNavItems = [
  { path: "/settings", icon: Settings, label: "Settings" },
  { path: "/help", icon: HelpCircle, label: "Help" },
];

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [location] = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen flex bg-background">
      {/* Background orbs */}
      <div className="bg-orbs" />
      
      {/* Sidebar */}
      <aside 
        className={cn(
          "fixed left-0 top-0 h-full z-50 flex flex-col",
          "glass border-r border-white/10",
          "transition-all duration-300 ease-in-out",
          collapsed ? "w-16" : "w-64"
        )}
      >
        {/* Logo */}
        <div className={cn(
          "h-16 flex items-center border-b border-white/10 px-4",
          collapsed ? "justify-center" : "gap-3"
        )}>
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
            <Boxes className="w-5 h-5 text-white" />
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="font-semibold text-foreground">Kubani</span>
              <span className="text-xs text-muted-foreground">Cluster Manager</span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-2 space-y-1">
          {navItems.map((item) => {
            const isActive = location === item.path || (location === "/" && item.path === "/monitoring");
            const Icon = item.icon;
            
            return (
              <Tooltip key={item.path} delayDuration={0}>
                <TooltipTrigger asChild>
                  <Link href={item.path}>
                    <div
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg",
                        "transition-all duration-200",
                        "hover:bg-white/5",
                        isActive && "bg-primary/10 text-primary border border-primary/20",
                        !isActive && "text-muted-foreground hover:text-foreground",
                        collapsed && "justify-center px-2"
                      )}
                    >
                      <Icon className={cn("w-5 h-5 shrink-0", isActive && "text-primary")} />
                      {!collapsed && (
                        <div className="flex flex-col">
                          <span className="text-sm font-medium">{item.label}</span>
                          <span className="text-xs text-muted-foreground">{item.description}</span>
                        </div>
                      )}
                    </div>
                  </Link>
                </TooltipTrigger>
                {collapsed && (
                  <TooltipContent side="right" className="glass">
                    <p className="font-medium">{item.label}</p>
                    <p className="text-xs text-muted-foreground">{item.description}</p>
                  </TooltipContent>
                )}
              </Tooltip>
            );
          })}
        </nav>

        {/* Command palette hint */}
        {!collapsed && (
          <div className="px-3 py-2">
            <button 
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-muted-foreground text-sm hover:bg-white/10 transition-colors"
              onClick={() => {
                // Command palette would open here
                import("sonner").then(({ toast }) => {
                  toast("Command palette coming soon", {
                    description: "Press ⌘K to quick navigate"
                  });
                });
              }}
            >
              <Command className="w-4 h-4" />
              <span>Quick actions</span>
              <kbd className="ml-auto text-xs bg-white/10 px-1.5 py-0.5 rounded">⌘K</kbd>
            </button>
          </div>
        )}

        {/* Bottom nav */}
        <div className="border-t border-white/10 py-2 px-2 space-y-1">
          {bottomNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <Tooltip key={item.path} delayDuration={0}>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => {
                      import("sonner").then(({ toast }) => {
                        toast(`${item.label} coming soon`);
                      });
                    }}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2 rounded-lg",
                      "text-muted-foreground hover:text-foreground hover:bg-white/5",
                      "transition-all duration-200",
                      collapsed && "justify-center px-2"
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    {!collapsed && <span className="text-sm">{item.label}</span>}
                  </button>
                </TooltipTrigger>
                {collapsed && (
                  <TooltipContent side="right" className="glass">
                    {item.label}
                  </TooltipContent>
                )}
              </Tooltip>
            );
          })}
        </div>

        {/* Collapse toggle */}
        <div className="border-t border-white/10 p-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCollapsed(!collapsed)}
            className={cn(
              "w-full justify-center text-muted-foreground hover:text-foreground",
              !collapsed && "justify-start px-3"
            )}
          >
            {collapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <>
                <ChevronLeft className="w-4 h-4 mr-2" />
                <span className="text-sm">Collapse</span>
              </>
            )}
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main 
        className={cn(
          "flex-1 transition-all duration-300",
          collapsed ? "ml-16" : "ml-64"
        )}
      >
        {children}
      </main>
    </div>
  );
}
