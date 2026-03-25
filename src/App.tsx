import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import Index from "./pages/Index";
import Pipelines from "./pages/Pipelines";
import NotFound from "./pages/NotFound";
import OntologyManager from "@/components/OntologyManager";
import DataUpload from "@/components/DataUpload";
import ProtographLogin from "@/components/ProtographLogin";
import ProtographDashboard from "@/components/ProtographDashboard";
import IntelligenceConsole from "./components/IntelligenceConsole";
import AppOnboarding from "./components/AppOnboarding";
import PluginDashboard from "./components/PluginDashboard";
import 'reactflow/dist/style.css';

const queryClient = new QueryClient();

/** Gate: redirect to /login if not authenticated */
const RequireAuth = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = sessionStorage.getItem("protograph_authenticated") === "true";
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

/**
 * PluginDashboard wrapper that reads :id from the URL and passes it as
 * an initial selection prop. PluginDashboard already handles null → fleet view,
 * so when no id is present (the /plugins fleet route) it just renders the grid.
 */
function PluginDashboardRoute() {
  const { id } = useParams<{ id?: string }>();
  return <PluginDashboard initialPluginId={id ?? null} />;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* Auth */}
          <Route path="/login" element={<ProtographLogin />} />

          {/* ProtoGraph Dashboard Hub */}
          <Route path="/home" element={<RequireAuth><ProtographDashboard /></RequireAuth>} />

          {/* Core tools */}
          <Route path="/graph"    element={<RequireAuth><Index /></RequireAuth>} />
          <Route path="/ontology" element={<RequireAuth><OntologyManager /></RequireAuth>} />
          <Route path="/pipelines" element={<RequireAuth><Pipelines /></RequireAuth>} />
          <Route path="/upload"   element={<RequireAuth><DataUpload /></RequireAuth>} />
          <Route path="/console"  element={<RequireAuth><IntelligenceConsole /></RequireAuth>} />

          {/* App management
              /apps       → onboarding wizard + registered-apps sidebar
              /plugins    → fleet overview grid
              /plugins/:id → individual agent dashboard (auto-selects that plugin)
          */}
          <Route path="/apps"         element={<RequireAuth><AppOnboarding /></RequireAuth>} />
          <Route path="/plugins"      element={<RequireAuth><PluginDashboardRoute /></RequireAuth>} />
          <Route path="/plugins/:id"  element={<RequireAuth><PluginDashboardRoute /></RequireAuth>} />

          {/* Legacy /dashboard route → full ProtoGraph */}
          <Route path="/dashboard" element={<RequireAuth><Index /></RequireAuth>} />

          {/* Root redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />

          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;