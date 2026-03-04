import { 
  Search, 
  Settings, 
  Sparkles, 
  Loader2, 
  Compass, 
  GitBranch, 
  Database, 
  Workflow,
  Brain,
  Zap,
  ChevronDown,
  ChevronUp,
  Target,
  Clock,
  X,
  ExternalLink,
  Info
} from "lucide-react";
import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import ConnectionReviewModal from "./ConnectionReviewModal";
import DataIngestionModal from "./DataIngestionModal";
import PluginManager from "./PluginManager";

interface HeaderProps {
  onDiscoveryPromptClick: (prompt: string) => void;
  onNodeSelect?: (nodeIds: string[]) => void;
  onNodeFocus?: (nodeId: string) => void;
  onHighlightNodes?: (nodeIds: string[]) => void;
}

interface UnifiedSearchResult {
  id: string;
  label: string;
  type: string;
  cluster: string;
  description: string;
  relevance_score: number;
  source: "keyword" | "neural" | "both";
  neural_context?: string;
  scenario_id: string;
  metadata?: Record<string, any>;
}

interface IntentAnalysis {
  strategy: "keyword" | "neural" | "hybrid";
  confidence: number;
  signals: string[];
  extracted_filters: Record<string, any>;
  search_terms: string[];
}

interface UnifiedSearchResponse {
  query: string;
  strategy_used: string;
  intent_analysis: IntentAnalysis;
  total_results: number;
  keyword_results: number;
  neural_results: number;
  merged_results: number;
  time_ms: number;
  results: UnifiedSearchResult[];
}

const discoveryPrompts = [
  "How do we handle credential dumping?",
  "Show me OPFOR scripts for lateral movement",
  "Find automation related to persistence",
  "What TTPs involve PowerShell?",
  "lib_cs_mimikatz",
  "Range infrastructure for AD environments"
];

const API_BASE = "http://localhost:8000";

const Header = ({ onDiscoveryPromptClick, onNodeSelect, onNodeFocus, onHighlightNodes }: HeaderProps) => {
  const [currentPrompts, setCurrentPrompts] = useState(discoveryPrompts.slice(0, 4));
  const [searchFocused, setSearchFocused] = useState(false);
 
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UnifiedSearchResult[]>([]);
  const [searchResponse, setSearchResponse] = useState<UnifiedSearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  
  // Strategy info tooltip
  const [showStrategyInfo, setShowStrategyInfo] = useState(false);
 
  const [showConnectionReview, setShowConnectionReview] = useState(false);
  const [pendingReviewCount, setPendingReviewCount] = useState(0);
  const [showDataIngestion, setShowDataIngestion] = useState(false);
  const [pluginManagerOpen, setPluginManagerOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
 
  // Load recent searches from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("protograph-recent-searches");
    if (saved) {
      try {
        setRecentSearches(JSON.parse(saved).slice(0, 5));
      } catch (e) {}
    }
  }, []);

  const saveRecentSearch = useCallback((query: string) => {
    setRecentSearches(prev => {
      const updated = [query, ...prev.filter(s => s !== query)].slice(0, 5);
      localStorage.setItem("protograph-recent-searches", JSON.stringify(updated));
      return updated;
    });
  }, []);

  useEffect(() => {
    const fetchPendingCount = async () => {
      try {
        const res = await fetch(`${API_BASE}/connections/stats`);
        const data = await res.json();
        setPendingReviewCount(data.total_pending || 0);
      } catch (error) {
        console.error("Failed to fetch review count:", error);
      }
    };
   
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (resultsRef.current && !resultsRef.current.contains(event.target as Node)) {
        if (inputRef.current?.contains(event.target as Node)) return;
        setShowResults(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const shufflePrompts = () => {
    const shuffled = [...discoveryPrompts].sort(() => Math.random() - 0.5);
    setCurrentPrompts(shuffled.slice(0, 4));
  };

  const handleSearch = async (query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      setSearchResponse(null);
      setShowResults(false);
      return;
    }

    setSearchLoading(true);
    setShowResults(true);
    setSearchFocused(false);

    try {
      // Use the new unified search endpoint
      const res = await fetch(
        `${API_BASE}/api/search/unified?q=${encodeURIComponent(query)}&limit=30`
      );
     
      if (!res.ok) throw new Error(`Search failed: ${res.status}`);
      const data: UnifiedSearchResponse = await res.json();
     
      setSearchResults(data.results || []);
      setSearchResponse(data);
      saveRecentSearch(query);

      // Select and highlight nodes in graph
      if (data.results.length > 0) {
        const nodeIds = data.results.slice(0, 15).map(r => r.id);
        
        if (onNodeSelect) {
          onNodeSelect(nodeIds);
        }
        
        if (onHighlightNodes) {
          onHighlightNodes(nodeIds);
        }

        if (onNodeFocus && data.results.length > 0) {
          setTimeout(() => {
            onNodeFocus(data.results[0].id);
          }, 150);
        }
      }
    } catch (error) {
      console.error("❌ Search failed:", error);
      setSearchResults([]);
      setSearchResponse(null);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleResultClick = (result: UnifiedSearchResult) => {
    if (onNodeSelect) onNodeSelect([result.id]);
    if (onHighlightNodes) onHighlightNodes([result.id]);
    if (onNodeFocus) {
      setTimeout(() => onNodeFocus(result.id), 100);
    }
    setShowResults(false);
    setSearchQuery("");
  };

  const handleClear = () => {
    setSearchQuery("");
    setSearchResults([]);
    setSearchResponse(null);
    setShowResults(false);
    if (onHighlightNodes) onHighlightNodes([]);
    inputRef.current?.focus();
  };

  const getClusterColor = (cluster: string) => {
    switch (cluster?.toLowerCase()) {
      case "automation": return "bg-amber-500/20 text-amber-400 border-amber-500/30";
      case "range": return "bg-stone-500/20 text-stone-300 border-stone-500/30";
      case "content":
      case "contentdev":
      case "content_dev": return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
      case "opfor": return "bg-red-500/20 text-red-400 border-red-500/30";
      case "planning": return "bg-blue-500/20 text-blue-400 border-blue-500/30";
      default: return "bg-gray-500/20 text-gray-400 border-gray-500/30";
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source) {
      case "keyword":
        return <span className="px-1.5 py-0.5 text-[9px] bg-blue-500/20 text-blue-400 rounded">KEYWORD</span>;
      case "neural":
        return <span className="px-1.5 py-0.5 text-[9px] bg-purple-500/20 text-purple-400 rounded flex items-center gap-1">
          <Brain className="w-2.5 h-2.5" />NEURAL
        </span>;
      case "both":
        return <span className="px-1.5 py-0.5 text-[9px] bg-cactus-green/20 text-cactus-green rounded flex items-center gap-1">
          <Zap className="w-2.5 h-2.5" />BOTH
        </span>;
      default:
        return null;
    }
  };

  const getStrategyIcon = (strategy: string) => {
    switch (strategy) {
      case "keyword": return <Search className="w-3.5 h-3.5 text-blue-400" />;
      case "neural": return <Brain className="w-3.5 h-3.5 text-purple-400" />;
      case "hybrid": return <Zap className="w-3.5 h-3.5 text-cactus-green" />;
      default: return <Search className="w-3.5 h-3.5" />;
    }
  };

  const getStrategyLabel = (strategy: string) => {
    switch (strategy) {
      case "keyword": return "Keyword Match";
      case "neural": return "Semantic Search";
      case "hybrid": return "Hybrid Search";
      default: return strategy;
    }
  };

  return (
    <header className="border-b-3 border-border bg-card py-3 px-5">
      <div className="flex items-center justify-between gap-4">
        {/* Logo */}
        <div className="flex items-center gap-3 relative flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <img src="/cactus.png" alt="318th RANS" className="w-20 h-20 object-contain western-badge crisp-logo" />
            <div>
              <h1 className="text-xl leading-none text-white" style={{ fontFamily: "'Outfit', sans-serif" }}>
                <span className="font-normal">Proto</span><span className="font-semibold text-cyan-400">Graph</span>
              </h1>
              <p className="text-[10px] text-white font-semibold tracking-wide uppercase">Range Intelligence</p>
            </div>
          </div>
        </div>

        {/* Unified Search Bar */}
        <div className="flex-1 max-w-2xl mx-4">
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              {searchLoading ? (
                <Loader2 className="w-4 h-4 animate-spin text-cactus-green" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
            </div>
            
            <input
              ref={inputRef}
              type="text"
              placeholder="Ask me anything about your data"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch(searchQuery);
                else if (e.key === "Escape") {
                  handleClear();
                  setSearchFocused(false);
                }
              }}
              className="w-full pl-10 pr-20 py-2.5 bg-background border-2 border-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cactus-green/50 focus:border-cactus-green transition-all"
              onFocus={() => {
                if (!searchQuery) setSearchFocused(true);
                setShowResults(true);
              }}
              onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
            />
           
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
              {searchQuery && !searchLoading && (
                <button
                  onClick={handleClear}
                  className="p-1 text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
              {searchQuery && !searchLoading && (
                <button
                  onClick={() => handleSearch(searchQuery)}
                  className="p-1.5 hover:bg-cactus-green/20 rounded transition-colors text-cactus-green"
                  title="Search"
                >
                  <Sparkles className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={shufflePrompts}
                className="p-1.5 hover:bg-secondary rounded transition-colors"
                title="Shuffle prompts"
              >
                <Compass className="w-4 h-4 text-muted-foreground hover:text-cactus-green transition-colors" />
              </button>
            </div>
          </div>

          {/* Discovery Prompts (when focused with no query) */}
          {searchFocused && !searchQuery && showResults && (
            <div ref={resultsRef} className="absolute mt-2 neo-card bg-card z-50 w-[600px] shadow-2xl">
              <div className="p-2.5 border-b-2 border-border bg-secondary/20">
                <div className="flex items-center gap-2">
                  <Compass className="w-3.5 h-3.5 text-cactus-green" />
                  <span className="text-xs font-bold text-white uppercase tracking-wide">Try These</span>
                </div>
              </div>
              
              {/* Recent searches */}
              {recentSearches.length > 0 && (
                <div className="p-2 border-b border-border">
                  <div className="text-[10px] font-semibold text-gray-500 uppercase px-2 py-1">Recent</div>
                  {recentSearches.slice(0, 3).map((search, idx) => (
                    <button
                      key={idx}
                      onClick={() => { setSearchQuery(search); handleSearch(search); }}
                      className="w-full text-left text-xs px-3 py-2 rounded hover:bg-secondary text-gray-300 flex items-center gap-2"
                    >
                      <Clock className="w-3 h-3 text-gray-500" />
                      {search}
                    </button>
                  ))}
                </div>
              )}
              
              <div className="p-2">
                <div className="text-[10px] font-semibold text-gray-500 uppercase px-2 py-1">Suggested</div>
                {currentPrompts.map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setSearchQuery(prompt);
                      handleSearch(prompt);
                    }}
                    className="w-full text-left text-xs px-3 py-2 rounded hover:bg-secondary border border-transparent hover:border-cactus-olive/30 transition-all text-white flex items-center gap-2"
                  >
                    <Sparkles className="w-3 h-3 text-cactus-green/50" />
                    {prompt}
                  </button>
                ))}
              </div>
              
              <div className="p-2 border-t border-border bg-secondary/10">
                <div className="text-[10px] text-gray-500 text-center">
                  Type naturally • Questions use AI • Exact terms use keyword match
                </div>
              </div>
            </div>
          )}

          {/* Search Results */}
          {showResults && (searchResults.length > 0 || searchLoading || searchResponse) && searchQuery && (
            <div ref={resultsRef} className="absolute mt-2 neo-card bg-card z-50 w-[650px] max-h-[600px] overflow-hidden shadow-2xl">
              {/* Results Header with Strategy Info */}
              <div className="p-3 border-b-2 border-border bg-secondary/20">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {searchResponse && getStrategyIcon(searchResponse.strategy_used)}
                    <span className="text-xs font-bold text-white">
                      {searchLoading ? "Searching..." : `${searchResults.length} results`}
                    </span>
                    {searchResponse && (
                      <span className="text-[10px] text-gray-400">
                        via {getStrategyLabel(searchResponse.strategy_used)}
                      </span>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-3">
                    {searchResponse && (
                      <div className="flex items-center gap-2 text-[10px] text-gray-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {searchResponse.time_ms.toFixed(0)}ms
                        </span>
                        
                        {/* Strategy info button */}
                        <button
                          onClick={() => setShowStrategyInfo(!showStrategyInfo)}
                          className="p-1 hover:bg-secondary rounded"
                          title="Why this strategy?"
                        >
                          <Info className="w-3 h-3" />
                        </button>
                      </div>
                    )}
                    
                    <button
                      onClick={handleClear}
                      className="text-xs text-muted-foreground hover:text-white transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
                
                {/* Strategy explanation panel */}
                {showStrategyInfo && searchResponse && (
                  <div className="mt-2 p-2 bg-black/30 rounded text-[10px] text-gray-400">
                    <div className="font-semibold text-white mb-1">Why {searchResponse.strategy_used}?</div>
                    <div className="space-y-1">
                      <div>Signals: {searchResponse.intent_analysis.signals.join(", ") || "none"}</div>
                      <div>Confidence: {(searchResponse.intent_analysis.confidence * 100).toFixed(0)}%</div>
                      {searchResponse.intent_analysis.extracted_filters && 
                        Object.keys(searchResponse.intent_analysis.extracted_filters).length > 0 && (
                        <div>Filters: {JSON.stringify(searchResponse.intent_analysis.extracted_filters)}</div>
                      )}
                      {searchResponse.strategy_used === "hybrid" && (
                        <div className="text-cactus-green">
                          Merged {searchResponse.keyword_results} keyword + {searchResponse.neural_results} neural results
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Results List */}
              <div className="overflow-y-auto max-h-[480px]">
                {searchLoading ? (
                  <div className="p-8 text-center">
                    <Loader2 className="w-8 h-8 animate-spin mx-auto text-cactus-green mb-2" />
                    <p className="text-xs text-muted-foreground">Analyzing your query...</p>
                  </div>
                ) : searchResults.length > 0 ? (
                  searchResults.map((result, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleResultClick(result)}
                      className="w-full text-left px-4 py-3 hover:bg-secondary border-b border-border last:border-b-0 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-bold text-sm text-white">{result.label}</span>
                            {getSourceBadge(result.source)}
                          </div>
                         
                          {result.description && (
                            <div className="text-[11px] text-muted-foreground mb-2 line-clamp-2">
                              {result.description}
                            </div>
                          )}
                          
                          {/* Neural context if available */}
                          {result.neural_context && (
                            <div className="text-[10px] text-purple-300/70 mb-2 italic line-clamp-1">
                              💡 {result.neural_context}
                            </div>
                          )}
                         
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="px-1.5 py-0.5 bg-secondary border border-border rounded text-[9px] font-semibold text-white">
                              {result.type}
                            </span>
                           
                            <span className={`px-1.5 py-0.5 border rounded text-[9px] font-semibold ${getClusterColor(result.cluster)}`}>
                              {result.cluster}
                            </span>
                          </div>
                        </div>

                        <div className="flex-shrink-0 text-right">
                          <div className="text-sm font-mono font-bold text-cactus-green">
                            {(result.relevance_score * 100).toFixed(0)}%
                          </div>
                          <div className="text-[9px] text-muted-foreground">
                            relevance
                          </div>
                        </div>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="p-8 text-center">
                    <div className="text-4xl mb-2">🔍</div>
                    <p className="text-xs font-semibold mb-1 text-white">No results found</p>
                    <p className="text-[11px] text-muted-foreground">
                      Try different terms or phrasing
                    </p>
                  </div>
                )}
              </div>

              {/* Results Footer */}
              {!searchLoading && searchResults.length > 0 && (
                <div className="p-2 border-t-2 border-border bg-secondary/5">
                  <div className="text-[9px] text-muted-foreground text-center flex items-center justify-center gap-4">
                    <span>Enter to search</span>
                    <span>Click to focus</span>
                    <span>Esc to close</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link to="/pipelines">
            <button
              className="neo-button-secondary flex items-center gap-2 text-xs"
              title="Configure data pipelines"
            >
              <Workflow className="w-3.5 h-3.5" />
              <span className="hidden lg:inline">Pipelines</span>
            </button>
          </Link>

          <button
            onClick={() => setShowDataIngestion(true)}
            className="neo-button-secondary flex items-center gap-2 text-xs"
            title="Ingest new data"
          >
            <Database className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">Ingest</span>
          </button>
         
          <button
            onClick={() => setShowConnectionReview(true)}
            className="neo-button-secondary relative flex items-center gap-2 text-xs"
            title="Review AI-suggested connections"
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">Review</span>
           
            {pendingReviewCount > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-cactus-green text-black text-[9px] font-bold rounded-full flex items-center justify-center border border-border">
                {pendingReviewCount > 99 ? "99" : pendingReviewCount}
              </span>
            )}
          </button>

          <button
            onClick={() => setPluginManagerOpen(true)}
            className="neo-button-secondary flex items-center gap-2 text-xs"
            title="Manage plugins"
          >
            <Settings className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">Tools</span>
          </button>
        </div>
      </div>
     
      <ConnectionReviewModal
        open={showConnectionReview}
        onClose={() => setShowConnectionReview(false)}
        onReviewComplete={() => {
          fetch(`${API_BASE}/connections/stats`)
            .then(res => res.json())
            .then(data => setPendingReviewCount(data.total_pending || 0))
            .catch(console.error);
        }}
      />
     
      <DataIngestionModal
        isOpen={showDataIngestion}
        onClose={() => setShowDataIngestion(false)}
        onSuccess={(results) => {
          console.log("Ingestion complete:", results);
          setShowDataIngestion(false);
        }}
      />

      <PluginManager 
        open={pluginManagerOpen}
        onClose={() => setPluginManagerOpen(false)}
      />
    </header>
  );
};

export default Header;