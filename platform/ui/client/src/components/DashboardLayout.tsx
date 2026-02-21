import { ReactNode, useState, useEffect } from "react";
import { Link, useLocation } from "wouter";
import {
  Activity,
  Database,
  MessageSquare,
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

  const MobileMenuContent = () => (
    <>
      {/* Logo */}
      <div className="h-14 flex items-center border-b border-border px-4 gap-3">
        <div className="w-8 h-8 rounded bg-primary flex items-center justify-center">
          <Boxes className="w-5 h-5 text-primary-foreground" />
        </div>
        <div className="flex flex-col">
          <span className="font-semibold text-foreground text-sm tracking-tight">
            Kubani
          </span>
          <span className="text-xs text-muted-foreground font-mono">
            v0.1.0
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const isActive =
            location === item.path ||
            (location === "/" && item.path === "/activity");
          const Icon = item.icon;

          return (
            <div key={item.path}>
              <Link href={item.path}>
                <div
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded",
                    "transition-colors duration-150",
                    "min-h-[40px]",
                    isActive && "bg-primary/15 text-primary",
                    !isActive &&
                      "text-muted-foreground hover:text-foreground hover:bg-secondary"
                  )}
                >
                  <Icon
                    className={cn(
                      "w-4 h-4 shrink-0",
                      isActive && "text-primary"
                    )}
                  />
                  <span className="text-sm font-medium">{item.label}</span>
                </div>
              </Link>
            </div>
          );
        })}
      </nav>

      {/* Bottom nav */}
      <div className="border-t border-border py-2 px-2 space-y-0.5">
        {bottomNavItems.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.path}>
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
                  "min-h-[40px]"
                )}
              >
                <Icon className="w-4 h-4" />
                <span className="text-sm">{item.label}</span>
              </button>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Top Navigation Bar */}
      <header className="fixed top-0 left-0 right-0 h-14 z-50 flex items-center bg-sidebar border-b border-border">
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 shrink-0">
          <div className="w-8 h-8 rounded bg-primary flex items-center justify-center">
            <Boxes className="w-5 h-5 text-primary-foreground" />
          </div>
          {!isMobile && (
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

        {/* Desktop Navigation */}
        {!isMobile && (
          <>
            <nav className="flex items-center gap-1 px-2">
              {navItems.map((item) => {
                const isActive =
                  location === item.path ||
                  (location === "/" && item.path === "/activity");
                const Icon = item.icon;

                return (
                  <Tooltip key={item.path} delayDuration={0}>
                    <TooltipTrigger asChild>
                      <Link href={item.path}>
                        <div
                          className={cn(
                            "flex items-center gap-2 px-3 py-1.5 rounded",
                            "transition-colors duration-150",
                            "text-sm font-medium",
                            isActive && "bg-primary/15 text-primary",
                            !isActive &&
                              "text-muted-foreground hover:text-foreground hover:bg-secondary"
                          )}
                        >
                          <Icon
                            className={cn(
                              "w-4 h-4 shrink-0",
                              isActive && "text-primary"
                            )}
                          />
                          <span>{item.label}</span>
                        </div>
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent className="bg-card-elevated border-border">
                      <p className="text-xs text-muted-foreground">
                        {item.description}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </nav>

            {/* Right side: command palette + settings/help */}
            <div className="ml-auto flex items-center gap-1 px-4">
              <button
                className="flex items-center gap-2 px-3 py-1.5 rounded bg-secondary border border-border text-muted-foreground text-sm hover:bg-muted transition-colors"
                onClick={() => {
                  import("sonner").then(({ toast }) => {
                    toast("Command palette coming soon", {
                      description: "Press ⌘K to quick navigate",
                    });
                  });
                }}
              >
                <Command className="w-3.5 h-3.5" />
                <kbd className="text-xs font-mono">⌘K</kbd>
              </button>

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
                        className="p-2 rounded text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors duration-150"
                      >
                        <Icon className="w-4 h-4" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className="bg-card-elevated border-border">
                      {item.label}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </>
        )}

        {/* Mobile hamburger */}
        {isMobile && (
          <div className="ml-auto px-4">
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
                side="top"
                className="w-full p-0 bg-sidebar border-b border-border"
              >
                <div className="flex flex-col">
                  <MobileMenuContent />
                </div>
              </SheetContent>
            </Sheet>
          </div>
        )}
      </header>

      {/* Main content */}
      <main className="flex-1 pt-14">{children}</main>
    </div>
  );
}
