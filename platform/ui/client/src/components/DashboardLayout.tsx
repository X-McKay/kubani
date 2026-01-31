import { ReactNode, useState, useEffect } from "react";
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
  Boxes,
  Menu,
  X,
  Workflow,
  Rss,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";

interface DashboardLayoutProps {
  children: ReactNode;
}

const navItems = [
  {
    path: "/activity",
    icon: Rss,
    label: "Activity",
    description: "Real-time syndicate feed",
  },
  {
    path: "/monitoring",
    icon: Activity,
    label: "Monitoring",
    description: "Cluster health & metrics",
  },
  {
    path: "/registry",
    icon: Database,
    label: "Registry",
    description: "Agents, MCP servers, skills",
  },
  {
    path: "/workflows",
    icon: Workflow,
    label: "Workflows",
    description: "Task & workflow tracking",
  },
  {
    path: "/chat",
    icon: MessageSquare,
    label: "Chat",
    description: "Interact with agents",
  },
];

const bottomNavItems = [
  { path: "/settings", icon: Settings, label: "Settings" },
  { path: "/help", icon: HelpCircle, label: "Help" },
];

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [location] = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Detect mobile viewport
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [location]);

  const SidebarContent = () => (
    <>
      {/* Logo */}
      <div
        className={cn(
          "h-14 flex items-center border-b border-border px-4",
          collapsed && !isMobile ? "justify-center" : "gap-3"
        )}
      >
        <div className="w-8 h-8 rounded bg-primary flex items-center justify-center">
          <Boxes className="w-5 h-5 text-primary-foreground" />
        </div>
        {(!collapsed || isMobile) && (
          <div className="flex flex-col">
            <span className="font-semibold text-foreground text-sm tracking-tight">
              Kubani
            </span>
            <span className="text-xs text-muted-foreground font-mono">
              v0.1.0
            </span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const isActive =
            location === item.path ||
            (location === "/" && item.path === "/activity");
          const Icon = item.icon;

          const NavLink = (
            <Link href={item.path}>
              <div
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded",
                  "transition-colors duration-150",
                  "min-h-[40px]",
                  isActive && "bg-primary/15 text-primary",
                  !isActive &&
                    "text-muted-foreground hover:text-foreground hover:bg-secondary",
                  collapsed && !isMobile && "justify-center px-2"
                )}
              >
                <Icon
                  className={cn("w-4 h-4 shrink-0", isActive && "text-primary")}
                />
                {(!collapsed || isMobile) && (
                  <span className="text-sm font-medium">{item.label}</span>
                )}
              </div>
            </Link>
          );

          if (collapsed && !isMobile) {
            return (
              <Tooltip key={item.path} delayDuration={0}>
                <TooltipTrigger asChild>{NavLink}</TooltipTrigger>
                <TooltipContent
                  side="right"
                  className="bg-card-elevated border-border"
                >
                  <p className="font-medium">{item.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.description}
                  </p>
                </TooltipContent>
              </Tooltip>
            );
          }

          return <div key={item.path}>{NavLink}</div>;
        })}
      </nav>

      {/* Command palette hint - hide on mobile */}
      {(!collapsed || isMobile) && !isMobile && (
        <div className="px-2 py-2">
          <button
            className="w-full flex items-center gap-2 px-3 py-2 rounded bg-secondary border border-border text-muted-foreground text-sm hover:bg-muted transition-colors"
            onClick={() => {
              import("sonner").then(({ toast }) => {
                toast("Command palette coming soon", {
                  description: "Press ⌘K to quick navigate",
                });
              });
            }}
          >
            <Command className="w-4 h-4" />
            <span className="font-mono text-xs">Quick actions</span>
            <kbd className="ml-auto text-xs font-mono bg-muted px-1.5 py-0.5 rounded text-muted-foreground">
              ⌘K
            </kbd>
          </button>
        </div>
      )}

      {/* Bottom nav */}
      <div className="border-t border-border py-2 px-2 space-y-0.5">
        {bottomNavItems.map((item) => {
          const Icon = item.icon;
          const NavButton = (
            <button
              onClick={() => {
                import("sonner").then(({ toast }) => {
                  toast(`${item.label} coming soon`);
                });
              }}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 rounded",
                "text-muted-foreground hover:text-foreground hover:bg-secondary",
                "transition-colors duration-150",
                "min-h-[40px]",
                collapsed && !isMobile && "justify-center px-2"
              )}
            >
              <Icon className="w-4 h-4" />
              {(!collapsed || isMobile) && (
                <span className="text-sm">{item.label}</span>
              )}
            </button>
          );

          if (collapsed && !isMobile) {
            return (
              <Tooltip key={item.path} delayDuration={0}>
                <TooltipTrigger asChild>{NavButton}</TooltipTrigger>
                <TooltipContent
                  side="right"
                  className="bg-card-elevated border-border"
                >
                  {item.label}
                </TooltipContent>
              </Tooltip>
            );
          }

          return <div key={item.path}>{NavButton}</div>;
        })}
      </div>

      {/* Collapse toggle - desktop only */}
      {!isMobile && (
        <div className="border-t border-border p-2">
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
      )}
    </>
  );

  return (
    <div className="min-h-screen flex bg-background">
      {/* Mobile Header */}
      {isMobile && (
        <header className="fixed top-0 left-0 right-0 h-14 z-50 flex items-center justify-between px-4 bg-card border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-primary flex items-center justify-center">
              <Boxes className="w-5 h-5 text-primary-foreground" />
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-foreground text-sm">
                Kubani
              </span>
              <span className="text-xs text-muted-foreground font-mono">
                v0.1.0
              </span>
            </div>
          </div>

          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="h-10 w-10">
                {mobileOpen ? (
                  <X className="w-5 h-5" />
                ) : (
                  <Menu className="w-5 h-5" />
                )}
              </Button>
            </SheetTrigger>
            <SheetContent
              side="left"
              className="w-64 p-0 bg-sidebar border-r border-border"
            >
              <div className="h-full flex flex-col">
                <SidebarContent />
              </div>
            </SheetContent>
          </Sheet>
        </header>
      )}

      {/* Desktop Sidebar */}
      {!isMobile && (
        <aside
          className={cn(
            "fixed left-0 top-0 h-full z-50 flex flex-col",
            "bg-sidebar border-r border-border",
            "transition-all duration-200 ease-out",
            collapsed ? "w-14" : "w-56"
          )}
        >
          <SidebarContent />
        </aside>
      )}

      {/* Main content */}
      <main
        className={cn(
          "flex-1 transition-all duration-200",
          isMobile ? "pt-14" : collapsed ? "ml-14" : "ml-56"
        )}
      >
        {children}
      </main>
    </div>
  );
}
