/**
 * Pipelines Page
 * 
 * Page wrapper for the Pipeline Builder component.
 * Accessible via /pipelines route.
 */

import { useNavigate } from "react-router-dom";
import { ArrowLeft, Workflow } from "lucide-react";
import PipelineBuilder from "@/components/PipelineBuilder";

const Pipelines = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background">
      {/* ProtoGraph Tool Header */}
      <header className="border-b border-border bg-[#0c0c0c]/90 backdrop-blur-sm px-5 py-3 sticky top-0 z-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/home")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-[#2d2d2d] text-[#888] hover:border-[#6EBE46] hover:text-[#6EBE46] transition-colors"
              style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1 }}
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              DASHBOARD
            </button>

            <div className="w-px h-5 bg-[#2d2d2d]" />

            <Workflow className="w-4 h-4 text-[#A09678]" />
            <span
              className="text-sm font-bold text-white tracking-wider"
              style={{ fontFamily: "'Rajdhani', sans-serif" }}
            >
              Pipeline Builder
            </span>
          </div>

          <span
            className="text-[10px] text-[#555] tracking-widest"
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          >
            PROTOGRAPH • PIPELINES
          </span>
        </div>
      </header>

      {/* Pipeline Builder */}
      <main className="p-6">
        <PipelineBuilder />
      </main>
    </div>
  );
};

export default Pipelines;