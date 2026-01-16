import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import DashboardLayout from "./components/DashboardLayout";
import Monitoring from "./pages/Monitoring";
import Registry from "./pages/Registry";
import Workflows from "./pages/Workflows";
import Chat from "./pages/Chat";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Monitoring} />
      <Route path="/monitoring" component={Monitoring} />
      <Route path="/registry" component={Registry} />
      <Route path="/workflows" component={Workflows} />
      <Route path="/chat" component={Chat} />
      <Route path="/404" component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark">
        <TooltipProvider>
          <Toaster 
            position="bottom-right"
            toastOptions={{
              className: "glass border-white/10",
            }}
          />
          <DashboardLayout>
            <Router />
          </DashboardLayout>
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
