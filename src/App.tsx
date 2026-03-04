import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Index from "./pages/Index";
import Pipelines from "./pages/Pipelines";
import NotFound from "./pages/NotFound";
import OntologyManager from "@/components/OntologyManager";
import DataUpload from "@/components/DataUpload";
import ProtographLogin from "@/components/ProtographLogin";
import ProtographDashboard from "@/components/ProtographDashboard";
import IntelligenceConsole from "./components/IntelligenceConsole";
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

          {/* Tools */}
          <Route path="/graph" element={<RequireAuth><Index /></RequireAuth>} />
          <Route path="/ontology" element={<RequireAuth><OntologyManager /></RequireAuth>} />
          <Route path="/pipelines" element={<RequireAuth><Pipelines /></RequireAuth>} />
          <Route path="/upload" element={<RequireAuth><DataUpload /></RequireAuth>} />
          <Route path="/console" element={<RequireAuth><IntelligenceConsole /></RequireAuth>} />

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