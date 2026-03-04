import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  GitBranch,
  Loader2,
  Network,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Unplug,
  Zap,
} from "lucide-react";

interface GraphHealthMonitorProps {
  onDiscoveryComplete?: () => void;
  className?: string;
}

interface HealthData {
  timestamp: string;
  num_nodes: number;
  num_edges: number;
  edge_density: number;
  avg_connections_per_node: number;
  max_degree: number;
  min_degree: number;
  median_degree: number;
  clustering_coefficient: number;
  num_weakly_connected_components: number;
  largest_wcc_size: number;
  num_orphan_nodes: number;
  nodes_by_collection: Record<string, number>;
  edges_by_type: Record<string, number>;
  status: "healthy" | "needs_discovery" | "critical";
  issues: string[];
}

interface ReviewStats {
  total_pending: number;
  total_reviewed: number;
  approved_count: number;
  rejected_count: number;
  modified_count: number;
  precision: number;
}

const GraphHealthMonitor: React.FC<GraphHealthMonitorProps> = ({
  onDiscoveryComplete,
  className = "",
}) => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunningDiscovery, setIsRunningDiscovery] = useState(false);
  const [lastScanTime, setLastScanTime] = useState<Date | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [discoveryResult, setDiscoveryResult] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:8000/api/graph/health");
      if (res.ok) {
        const data = await res.json();
        setHealth(data.health);
        setLastScanTime(new Date());
      }
    } catch (error) {
      console.error("Failed to fetch graph health:", error);
    }
  }, []);

  const fetchReviewStats = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:8000/connections/stats");
      if (res.ok) {
        const data = await res.json();
        setReviewStats(data);
      }
    } catch (error) {
      console.error("Failed to fetch review stats:", error);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setIsLoading(true);
    await Promise.all([fetchHealth(), fetchReviewStats()]);
    setIsLoading(false);
  }, [fetchHealth, fetchReviewStats]);

  useEffect(() => {
    refreshAll();
    // Refresh every 2 minutes
    const interval = setInterval(refreshAll, 2 * 60 * 1000);
    return () => clearInterval(interval);
  }, [refreshAll]);

  const runDiscoveryOnOrphans = async () => {
    if (!health || health.num_orphan_nodes === 0) return;

    setIsRunningDiscovery(true);
    setDiscoveryResult(null);

    try {
      // Get the first orphan node to run discovery on
      // In a full implementation, you might want to batch process all orphans
      const graphRes = await fetch("http://localhost:8000/graph");
      const graphData = await graphRes.json();
      
      // Find nodes with no edges (orphans)
      const nodeIds = new Set(graphData.nodes.map((n: any) => n.id));
      const connectedNodes = new Set<string>();
      
      graphData.edges.forEach((e: any) => {
        connectedNodes.add(e.source);
        connectedNodes.add(e.target);
      });

      const orphanNodes = graphData.nodes.filter((n: any) => !connectedNodes.has(n.id));
      
      if (orphanNodes.length === 0) {
        setDiscoveryResult("No orphan nodes found");
        return;
      }

      // Run discovery on first orphan (could be extended to batch)
      const targetNode = orphanNodes[0];
      const res = await fetch(
        `http://localhost:8000/api/discovery/run?artifact_id=${encodeURIComponent(targetNode.id)}`,
        { method: "POST" }
      );

      if (res.ok) {
        const data = await res.json();
        const suggestionCount = data.suggestions?.length || 0;
        setDiscoveryResult(
          suggestionCount > 0
            ? `Found ${suggestionCount} potential connections for "${targetNode.label}"`
            : `No connections found for "${targetNode.label}"`
        );
        
        // Refresh stats
        await refreshAll();
        onDiscoveryComplete?.();
      } else {
        setDiscoveryResult("Discovery failed - check server logs");
      }
    } catch (error) {
      console.error("Discovery failed:", error);
      setDiscoveryResult("Discovery failed - server error");
    } finally {
      setIsRunningDiscovery(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "healthy":
        return "text-green-400";
      case "needs_discovery":
        return "text-yellow-400";
      case "critical":
        return "text-red-400";
      default:
        return "text-gray-400";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "healthy":
        return <CheckCircle2 className="w-4 h-4 text-green-400" />;
      case "needs_discovery":
        return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
      case "critical":
        return <AlertTriangle className="w-4 h-4 text-red-400" />;
      default:
        return <Activity className="w-4 h-4 text-gray-400" />;
    }
  };

  const getConnectivityPercent = () => {
    if (!health || health.num_nodes === 0) return 0;
    return Math.round(((health.num_nodes - health.num_orphan_nodes) / health.num_nodes) * 100);
  };

  const formatTimeSince = (date: Date) => {
    const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  };

  if (isLoading && !health) {
    return (
      <div className={`p-4 ${className}`}>
        <div className="flex items-center gap-2 text-gray-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-xs">Loading health data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`${className}`}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-teal-400" />
          <span className="text-xs font-bold uppercase tracking-wide">Graph Health</span>
          {health && getStatusIcon(health.status)}
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500" />
        )}
      </button>

      {expanded && health && (
        <div className="px-3 pb-3 space-y-3">
          {/* Quick Stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-gray-800/50 rounded p-2 text-center">
              <div className="text-lg font-bold">{health.num_nodes}</div>
              <div className="text-[10px] text-gray-500 uppercase">Nodes</div>
            </div>
            <div className="bg-gray-800/50 rounded p-2 text-center">
              <div className="text-lg font-bold">{health.num_edges}</div>
              <div className="text-[10px] text-gray-500 uppercase">Edges</div>
            </div>
            <div className="bg-gray-800/50 rounded p-2 text-center">
              <div className="text-lg font-bold">{Math.round(health.edge_density * 100)}%</div>
              <div className="text-[10px] text-gray-500 uppercase">Density</div>
            </div>
          </div>

          {/* Connectivity Bar */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-gray-400">Connectivity</span>
              <span className={getStatusColor(health.status)}>
                {getConnectivityPercent()}% connected
              </span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  health.status === "healthy"
                    ? "bg-green-500"
                    : health.status === "needs_discovery"
                    ? "bg-yellow-500"
                    : "bg-red-500"
                }`}
                style={{ width: `${getConnectivityPercent()}%` }}
              />
            </div>
          </div>

          {/* Issues */}
          {health.issues.length > 0 && (
            <div className="space-y-1">
              {health.issues.slice(0, 3).map((issue, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 text-xs text-yellow-400 bg-yellow-900/20 rounded px-2 py-1.5"
                >
                  <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>{issue}</span>
                </div>
              ))}
            </div>
          )}

          {/* Detailed Stats (collapsible) */}
          <details className="group">
            <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              Detailed metrics
            </summary>
            <div className="mt-2 space-y-1 text-xs">
              <div className="flex justify-between text-gray-400">
                <span>Avg connections/node:</span>
                <span className="font-mono">{health.avg_connections_per_node}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>Clustering coefficient:</span>
                <span className="font-mono">{health.clustering_coefficient}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>Components:</span>
                <span className="font-mono">{health.num_weakly_connected_components}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>Largest component:</span>
                <span className="font-mono">{health.largest_wcc_size} nodes</span>
              </div>
            </div>
          </details>

          {/* Discovery Section */}
          <div className="pt-2 border-t border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-pink-400" />
                <span className="text-xs font-semibold">AI Discovery</span>
              </div>
              {reviewStats && reviewStats.total_pending > 0 && (
                <span className="px-2 py-0.5 bg-pink-900/50 text-pink-300 rounded-full text-[10px] font-bold">
                  {reviewStats.total_pending} pending
                </span>
              )}
            </div>

            {/* Orphan indicator */}
            {health.num_orphan_nodes > 0 && (
              <div className="flex items-center gap-2 text-xs text-gray-400 mb-2">
                <Unplug className="w-3 h-3" />
                <span>{health.num_orphan_nodes} orphan nodes need connections</span>
              </div>
            )}

            {/* Discovery Button */}
            <button
              onClick={runDiscoveryOnOrphans}
              disabled={isRunningDiscovery || health.num_orphan_nodes === 0}
              className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                health.num_orphan_nodes === 0
                  ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                  : isRunningDiscovery
                  ? "bg-pink-900/50 text-pink-300"
                  : "bg-pink-600 hover:bg-pink-500 text-white"
              }`}
            >
              {isRunningDiscovery ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running Discovery...
                </>
              ) : health.num_orphan_nodes === 0 ? (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  All Nodes Connected
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Run Discovery
                </>
              )}
            </button>

            {/* Discovery Result */}
            {discoveryResult && (
              <div className="mt-2 text-xs text-center text-gray-400 bg-gray-800/50 rounded px-2 py-1.5">
                {discoveryResult}
              </div>
            )}

            {/* Review Stats */}
            {reviewStats && reviewStats.total_reviewed > 0 && (
              <div className="mt-2 flex items-center justify-between text-[10px] text-gray-500">
                <span>
                  {reviewStats.approved_count} approved / {reviewStats.rejected_count} rejected
                </span>
                <span>
                  {Math.round(reviewStats.precision * 100)}% precision
                </span>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between pt-2 border-t border-gray-700">
            <span className="text-[10px] text-gray-500">
              {lastScanTime ? `Updated ${formatTimeSince(lastScanTime)}` : ""}
            </span>
            <button
              onClick={refreshAll}
              disabled={isLoading}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
              title="Refresh stats"
            >
              <RefreshCw className={`w-3 h-3 text-gray-500 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphHealthMonitor;