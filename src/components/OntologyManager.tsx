// components/OntologyManager.tsx
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Database,
  Edit3,
  FileCode,
  GitBranch,
  Layers,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// =====================================================
// TYPES
// =====================================================

interface Taxonomy {
  scheme_id: string;
  uri: string;
  label: string;
  description: string;
  term_count?: number;
}

interface Term {
  uri: string;
  label: string;
  aliases: string[];
  definition?: string;
}

interface Property {
  name: string;
  type: string;
  required: boolean;
  multiple: boolean;
  taxonomy: string | null;
  target_class: string | null;
  range: string | null;
  description: string | null;
  inherited_from?: string;
}

interface Concept {
  uri: string;
  label: string;
  definition: string;
  parent: string | null;
  abstract: boolean;
  collection: string | null;
  properties?: Property[];
}

interface RelationshipType {
  uri: string;
  label: string;
  definition: string;
  domain?: string[];
  range?: string[];
  inverse?: string | null;
  symmetric?: boolean;
  transitive?: boolean;
}

interface HealthData {
  status: string;
  tbox?: { classes: number; properties: number };
  cbox?: { taxonomy_schemes: number; taxonomy_terms: number };
  rbox?: { relationship_types: number };
  abox?: { instances: number; edges: number };
  // Compat fields computed from above
  counts: {
    concepts: number;
    taxonomies: number;
    terms: number;
    relationship_types: number;
  };
  collections_initialized: boolean;
}

// =====================================================
// MAIN COMPONENT
// =====================================================

const OntologyManager: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"taxonomies" | "concepts" | "relationships" | "advanced">("taxonomies");
  const [health, setHealth] = useState<HealthData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchHealth();
  }, []);

  const fetchHealth = async () => {
    try {
      // Try new GraphDB summary endpoint first
      let res = await fetch(`${API_BASE}/api/ontology/summary`);
      if (res.ok) {
        const data = await res.json();
        setHealth({
          status: "ok",
          tbox: data.tbox,
          cbox: data.cbox,
          rbox: data.rbox,
          abox: data.abox,
          counts: {
            concepts: data.tbox?.classes ?? 0,
            taxonomies: data.cbox?.taxonomy_schemes ?? 0,
            terms: data.cbox?.taxonomy_terms ?? 0,
            relationship_types: data.rbox?.relationship_types ?? 0,
          },
          collections_initialized: true,
        });
        return;
      }
      // Fallback to old health endpoint
      res = await fetch(`${API_BASE}/api/ontology/health`);
      if (res.ok) {
        const data = await res.json();
        setHealth({
          ...data,
          counts: data.counts || { concepts: 0, taxonomies: 0, terms: 0, relationship_types: 0 },
          collections_initialized: data.collections_initialized ?? (data.status === "ok"),
        });
      }
    } catch (error) {
      console.error("Failed to fetch health:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const tabs = [
    { id: "taxonomies", label: "Taxonomies", icon: Tag, count: health?.counts?.taxonomies },
    { id: "concepts", label: "Concepts", icon: Layers, count: health?.counts?.concepts },
    { id: "relationships", label: "Relationships", icon: GitBranch, count: health?.counts?.relationship_types },
    { id: "advanced", label: "Advanced", icon: FileCode },
  ];

  return (
    <div className="h-full flex flex-col bg-background">
      {/* ProtoGraph Tool Header */}
      <div className="border-b border-border bg-[#0c0c0c]/90 backdrop-blur-sm px-5 py-3 sticky top-0 z-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/home")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-[#2d2d2d] text-[#888] hover:border-[#6EBE46] hover:text-[#6EBE46] transition-colors"
              style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1 }}
            >
              <span>←</span>
              DASHBOARD
            </button>

            <div className="w-px h-5 bg-[#2d2d2d]" />

            <Layers className="w-4 h-4 text-[#E6AA32]" />
            <span
              className="text-sm font-bold text-white tracking-wider"
              style={{ fontFamily: "'Rajdhani', sans-serif" }}
            >
              Ontology Manager
            </span>
          </div>

          <div className="flex items-center gap-4">
            {health && (
              <div className="flex items-center gap-2 text-xs" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                <span className="text-[#888]">
                  {health.counts?.concepts ?? 0} concepts • {health.counts?.taxonomies ?? 0} taxonomies • {health.counts?.terms ?? 0} terms
                </span>
                <span className={`px-2 py-0.5 rounded-full ${
                  health.collections_initialized 
                    ? "bg-green-900/50 text-green-400" 
                    : "bg-red-900/50 text-red-400"
                }`}>
                  {health.collections_initialized ? "Connected" : "Not Initialized"}
                </span>
              </div>
            )}
            <button
              onClick={fetchHealth}
              className="p-2 hover:bg-gray-700 rounded transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 text-gray-400 ${isLoading ? "animate-spin" : ""}`} />
            </button>
            <span
              className="text-[10px] text-[#555] tracking-widest"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              PROTOGRAPH • ONTOLOGY
            </span>
          </div>
        </div>

        <div className="flex gap-1 mt-4">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? "bg-card border-t-2 border-x border-[#6EBE46] text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
              {tab.count !== undefined && (
                <span className="px-1.5 py-0.5 text-xs bg-gray-700 rounded">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {activeTab === "taxonomies" && <TaxonomiesTab onUpdate={fetchHealth} />}
        {activeTab === "concepts" && <ConceptsTab onUpdate={fetchHealth} />}
        {activeTab === "relationships" && <RelationshipsTab onUpdate={fetchHealth} />}
        {activeTab === "advanced" && <AdvancedTab onUpdate={fetchHealth} />}
      </div>
    </div>
  );
};

// =====================================================
// TAXONOMIES TAB
// =====================================================

const TaxonomiesTab: React.FC<{ onUpdate: () => void }> = ({ onUpdate }) => {
  const [taxonomies, setTaxonomies] = useState<Taxonomy[]>([]);
  const [selectedTaxonomy, setSelectedTaxonomy] = useState<string | null>(null);
  const [terms, setTerms] = useState<Term[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  
  const [showCreateTaxonomy, setShowCreateTaxonomy] = useState(false);
  const [showCreateTerm, setShowCreateTerm] = useState(false);
  const [showBulkAdd, setShowBulkAdd] = useState(false);
  const [editingTerm, setEditingTerm] = useState<Term | null>(null);

  const [newTaxonomy, setNewTaxonomy] = useState({ scheme_id: "", label: "", description: "" });
  const [newTerm, setNewTerm] = useState({ uri: "", label: "", definition: "", aliases: "", broader: "" });
  const [bulkTermsJson, setBulkTermsJson] = useState("");

  useEffect(() => {
    fetchTaxonomies();
  }, []);

  useEffect(() => {
    if (selectedTaxonomy) {
      fetchTerms(selectedTaxonomy);
    }
  }, [selectedTaxonomy]);

  const fetchTaxonomies = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies`);
      if (res.ok) {
        const data = await res.json();
        setTaxonomies(data.taxonomies);
        if (data.taxonomies.length > 0 && !selectedTaxonomy) {
          setSelectedTaxonomy(data.taxonomies[0].scheme_id);
        }
      }
    } catch (error) {
      console.error("Failed to fetch taxonomies:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchTerms = async (taxonomyId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies/${taxonomyId}`);
      if (res.ok) {
        const data = await res.json();
        setTerms(data.terms || []);
      }
    } catch (error) {
      console.error("Failed to fetch terms:", error);
    }
  };

  const handleCreateTaxonomy = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newTaxonomy),
      });
      if (res.ok) {
        setShowCreateTaxonomy(false);
        setNewTaxonomy({ scheme_id: "", label: "", description: "" });
        await fetchTaxonomies();
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to create taxonomy:", error);
    }
  };

  const handleCreateTerm = async () => {
    if (!selectedTaxonomy) return;
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies/${selectedTaxonomy}/terms`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          term_id: newTerm.uri,  // URI field used as term_id
          label: newTerm.label,
          definition: newTerm.definition,
          aliases: newTerm.aliases.split(",").map(a => a.trim()).filter(a => a),
        }),
      });
      if (res.ok) {
        setShowCreateTerm(false);
        setNewTerm({ uri: "", label: "", definition: "", aliases: "", broader: "" });
        await fetchTerms(selectedTaxonomy);
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to create term:", error);
    }
  };

  const handleBulkAdd = async () => {
    if (!selectedTaxonomy) return;
    try {
      const termsArray = JSON.parse(bulkTermsJson);
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies/${selectedTaxonomy}/terms/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ terms: termsArray }),
      });
      if (res.ok) {
        const result = await res.json();
        alert(`Created ${result.created_count} terms. ${result.error_count} errors.`);
        setShowBulkAdd(false);
        setBulkTermsJson("");
        await fetchTerms(selectedTaxonomy);
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      alert(`Invalid JSON: ${error}`);
    }
  };

  const handleUpdateTerm = async () => {
    if (!selectedTaxonomy || !editingTerm) return;
    
    try {
      const termId = editingTerm.uri.includes("/") ? editingTerm.uri.split("/").pop() : editingTerm.uri;
      const res = await fetch(
        `${API_BASE}/api/ontology/taxonomies/${selectedTaxonomy}/terms/${encodeURIComponent(termId || editingTerm.uri)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            label: editingTerm.label,
            definition: editingTerm.definition,
            aliases: editingTerm.aliases,
          }),
        }
      );
      if (res.ok) {
        setEditingTerm(null);
        await fetchTerms(selectedTaxonomy);
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to update term:", error);
    }
  };

  const handleDeleteTerm = async (termUri: string) => {
    if (!selectedTaxonomy) return;
    if (!confirm("Delete this term?")) return;
    
    // Extract term_id from full URI (e.g. https://proto.atlas/taxonomy/risk-critical → risk-critical)
    const termId = termUri.includes("/") ? termUri.split("/").pop() : termUri;
    
    try {
      const res = await fetch(
        `${API_BASE}/api/ontology/taxonomies/${selectedTaxonomy}/terms/${encodeURIComponent(termId || termUri)}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        await fetchTerms(selectedTaxonomy);
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to delete term:", error);
    }
  };

  const handleDeleteTaxonomy = async (taxonomyId: string) => {
    if (!confirm(`Delete taxonomy "${taxonomyId}" and all its terms?`)) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies/${taxonomyId}?force=true`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSelectedTaxonomy(null);
        setTerms([]);
        await fetchTaxonomies();
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to delete taxonomy:", error);
    }
  };

  const filteredTerms = terms.filter(term =>
    term.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
    term.aliases.some(a => a.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="h-full flex">
      {/* Taxonomy List Sidebar */}
      <div className="w-64 border-r border-border bg-secondary/20 flex flex-col">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-bold uppercase text-gray-500">Taxonomies</span>
          <button
            onClick={() => setShowCreateTaxonomy(true)}
            className="p-1.5 hover:bg-gray-700 rounded transition-colors"
            title="Create Taxonomy"
          >
            <Plus className="w-4 h-4 text-[#6EBE46]" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 text-center">
              <Loader2 className="w-5 h-5 animate-spin mx-auto text-gray-500" />
            </div>
          ) : taxonomies.length === 0 ? (
            <div className="p-4 text-center text-xs text-gray-500">
              No taxonomies yet.
              <br />
              Click + to create one.
            </div>
          ) : (
            taxonomies.map((tax) => (
              <div
                key={tax.scheme_id}
                onClick={() => setSelectedTaxonomy(tax.scheme_id)}
                className={`p-3 cursor-pointer border-b border-border/50 transition-colors group relative ${
                  selectedTaxonomy === tax.scheme_id
                    ? "bg-[#4B5A2D]/30 border-l-2 border-l-[#6EBE46]"
                    : "hover:bg-gray-800/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm text-white">{tax.label}</span>
                  <span className="text-xs text-gray-500">{tax.term_count || 0}</span>
                </div>
                <div className="text-xs text-gray-500 truncate">{tax.scheme_id}</div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteTaxonomy(tax.scheme_id);
                  }}
                  className="hidden group-hover:block absolute right-2 top-2 p-1 hover:bg-red-900/50 rounded"
                >
                  <Trash2 className="w-3 h-3 text-red-400" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Terms Panel */}
      <div className="flex-1 flex flex-col">
        {selectedTaxonomy ? (
          <>
            <div className="p-4 border-b border-border flex items-center justify-between">
              <div>
                <h2 className="font-bold text-white">
                  {taxonomies.find(t => t.scheme_id === selectedTaxonomy)?.label}
                </h2>
                <p className="text-xs text-gray-500">
                  {terms.length} terms in this taxonomy
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search terms..."
                    className="pl-9 pr-3 py-1.5 bg-gray-800 border border-border rounded text-sm w-48"
                  />
                </div>
                <button
                  onClick={() => setShowBulkAdd(true)}
                  className="neo-button-secondary px-3 py-1.5 text-xs flex items-center gap-1"
                >
                  <Upload className="w-3 h-3" />
                  Bulk Add
                </button>
                <button
                  onClick={() => setShowCreateTerm(true)}
                  className="neo-button px-3 py-1.5 text-xs flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" />
                  Add Term
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {filteredTerms.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <Tag className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p className="text-sm">No terms yet</p>
                  <p className="text-xs mt-1">Add terms to this taxonomy</p>
                </div>
              ) : (
                <div className="grid gap-2">
                  {filteredTerms.map((term) => (
                    <div
                      key={term.uri}
                      className="neo-card p-3 bg-card hover:border-[#6EBE46]/50 transition-colors group"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white">{term.label}</span>
                            {term.broader && (
                              <span className="text-xs text-gray-500">
                                ↑ {terms.find(t => t.uri === term.broader)?.label || term.broader}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-gray-500 font-mono mt-0.5">{term.uri}</div>
                          {term.definition && (
                            <p className="text-xs text-gray-400 mt-1">{term.definition}</p>
                          )}
                          {term.aliases.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {term.aliases.map((alias, idx) => (
                                <span
                                  key={idx}
                                  className="px-1.5 py-0.5 bg-gray-700 rounded text-xs text-gray-300"
                                >
                                  {alias}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => setEditingTerm(term)}
                            className="p-1.5 hover:bg-gray-700 rounded"
                          >
                            <Edit3 className="w-3 h-3 text-gray-400" />
                          </button>
                          <button
                            onClick={() => handleDeleteTerm(term.uri)}
                            className="p-1.5 hover:bg-red-900/50 rounded"
                          >
                            <Trash2 className="w-3 h-3 text-red-400" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <Tag className="w-16 h-16 mx-auto mb-4 opacity-30" />
              <p>Select a taxonomy to view terms</p>
            </div>
          </div>
        )}
      </div>

      {/* Create Taxonomy Modal */}
      {showCreateTaxonomy && (
        <Modal onClose={() => setShowCreateTaxonomy(false)} title="Create Taxonomy">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">ID *</label>
              <input
                type="text"
                value={newTaxonomy.scheme_id}
                onChange={(e) => setNewTaxonomy({ ...newTaxonomy, scheme_id: e.target.value })}
                placeholder="e.g., teams, mitre_tactics"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Label *</label>
              <input
                type="text"
                value={newTaxonomy.label}
                onChange={(e) => setNewTaxonomy({ ...newTaxonomy, label: e.target.value })}
                placeholder="e.g., Teams, MITRE Tactics"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Description</label>
              <textarea
                value={newTaxonomy.description}
                onChange={(e) => setNewTaxonomy({ ...newTaxonomy, description: e.target.value })}
                placeholder="What does this taxonomy represent?"
                className="neo-input w-full h-20 resize-none"
              />
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setShowCreateTaxonomy(false)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateTaxonomy}
                disabled={!newTaxonomy.scheme_id || !newTaxonomy.label}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Create Term Modal */}
      {showCreateTerm && (
        <Modal onClose={() => setShowCreateTerm(false)} title="Add Term">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">URI *</label>
              <input
                type="text"
                value={newTerm.uri}
                onChange={(e) => setNewTerm({ ...newTerm, uri: e.target.value })}
                placeholder="e.g., proto:team/automation"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Label *</label>
              <input
                type="text"
                value={newTerm.label}
                onChange={(e) => setNewTerm({ ...newTerm, label: e.target.value })}
                placeholder="Canonical label (stored in data)"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Definition</label>
              <textarea
                value={newTerm.definition}
                onChange={(e) => setNewTerm({ ...newTerm, definition: e.target.value })}
                placeholder="What does this term mean?"
                className="neo-input w-full h-16 resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Aliases (comma-separated)</label>
              <input
                type="text"
                value={newTerm.aliases}
                onChange={(e) => setNewTerm({ ...newTerm, aliases: e.target.value })}
                placeholder="e.g., Auto, Automation Team"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Broader Term (parent URI)</label>
              <select
                value={newTerm.broader}
                onChange={(e) => setNewTerm({ ...newTerm, broader: e.target.value })}
                className="neo-input w-full"
              >
                <option value="">None (top-level)</option>
                {terms.map((t) => (
                  <option key={t.uri} value={t.uri}>{t.label}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setShowCreateTerm(false)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateTerm}
                disabled={!newTerm.uri || !newTerm.label}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Add Term
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Bulk Add Modal */}
      {showBulkAdd && (
        <Modal onClose={() => setShowBulkAdd(false)} title="Bulk Add Terms" width="lg">
          <div className="space-y-4">
            <p className="text-xs text-gray-400">
              Paste a JSON array of terms. Each term needs: uri, label. Optional: definition, aliases, broader.
            </p>
            <textarea
              value={bulkTermsJson}
              onChange={(e) => setBulkTermsJson(e.target.value)}
              placeholder={`[
  {"uri": "proto:tactic/TA0001", "label": "TA0001", "aliases": ["Initial Access"], "definition": "..."},
  {"uri": "proto:tactic/TA0002", "label": "TA0002", "aliases": ["Execution"], "definition": "..."}
]`}
              className="neo-input w-full h-64 font-mono text-xs resize-none"
            />
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setShowBulkAdd(false)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleBulkAdd}
                disabled={!bulkTermsJson.trim()}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Import Terms
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Edit Term Modal */}
      {editingTerm && (
        <Modal onClose={() => setEditingTerm(null)} title="Edit Term">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">URI (read-only)</label>
              <input
                type="text"
                value={editingTerm.uri}
                disabled
                className="neo-input w-full opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Label *</label>
              <input
                type="text"
                value={editingTerm.label}
                onChange={(e) => setEditingTerm({ ...editingTerm, label: e.target.value })}
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Definition</label>
              <textarea
                value={editingTerm.definition}
                onChange={(e) => setEditingTerm({ ...editingTerm, definition: e.target.value })}
                className="neo-input w-full h-16 resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Aliases (comma-separated)</label>
              <input
                type="text"
                value={editingTerm.aliases.join(", ")}
                onChange={(e) => setEditingTerm({ 
                  ...editingTerm, 
                  aliases: e.target.value.split(",").map(a => a.trim()).filter(a => a) 
                })}
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Broader Term</label>
              <select
                value={editingTerm.broader || ""}
                onChange={(e) => setEditingTerm({ ...editingTerm, broader: e.target.value || null })}
                className="neo-input w-full"
              >
                <option value="">None (top-level)</option>
                {terms.filter(t => t.uri !== editingTerm.uri).map((t) => (
                  <option key={t.uri} value={t.uri}>{t.label}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setEditingTerm(null)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleUpdateTerm}
                disabled={!editingTerm.label}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Save Changes
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

// =====================================================
// CONCEPTS TAB
// =====================================================

const ConceptsTab: React.FC<{ onUpdate: () => void }> = ({ onUpdate }) => {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [taxonomies, setTaxonomies] = useState<Taxonomy[]>([]);
  const [selectedConcept, setSelectedConcept] = useState<Concept | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  
  const [showCreateConcept, setShowCreateConcept] = useState(false);
  const [showAddProperty, setShowAddProperty] = useState(false);
  
  const [newConcept, setNewConcept] = useState({
    uri: "",
    label: "",
    definition: "",
    parent: "",
    abstract: false,
    collection: "",
  });
  const [newProperty, setNewProperty] = useState({
    name: "",
    type: "string",
    required: false,
    multiple: false,
    taxonomy: "",
    target_class: "",
    description: "",
  });

  useEffect(() => {
    fetchConcepts();
    fetchTaxonomies();
  }, []);

  const fetchConcepts = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ontology/concepts`);
      if (res.ok) {
        const data = await res.json();
        setConcepts(data.concepts);
      }
    } catch (error) {
      console.error("Failed to fetch concepts:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchTaxonomies = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/taxonomies`);
      if (res.ok) {
        const data = await res.json();
        setTaxonomies(data.taxonomies);
      }
    } catch (error) {
      console.error("Failed to fetch taxonomies:", error);
    }
  };

  const fetchConceptDetails = async (uriOrLabel: string) => {
    try {
      // New API takes label as path param, extract from URI or use directly
      let label = uriOrLabel;
      if (uriOrLabel.startsWith("http")) {
        // Extract local name from URI
        label = uriOrLabel.split("/").pop() || uriOrLabel;
      }
      const res = await fetch(`${API_BASE}/api/ontology/concepts/${encodeURIComponent(label)}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedConcept(data);
      }
    } catch (error) {
      console.error("Failed to fetch concept details:", error);
    }
  };

  const handleCreateConcept = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/concepts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: newConcept.label,
          definition: newConcept.definition,
          parent: newConcept.parent || null,
          abstract: newConcept.abstract,
          collection: newConcept.collection || null,
        }),
      });
      if (res.ok) {
        setShowCreateConcept(false);
        setNewConcept({ uri: "", label: "", definition: "", parent: "", abstract: false, collection: "" });
        await fetchConcepts();
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to create concept:", error);
    }
  };

  const handleAddProperty = async () => {
    if (!selectedConcept) return;
    try {
      const res = await fetch(`${API_BASE}/api/ontology/concepts/${encodeURIComponent(selectedConcept.label)}/properties`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...newProperty,
          taxonomy: newProperty.taxonomy || null,
          target_class: newProperty.type === "reference" ? (newProperty.target_class || null) : null,
        }),
      });
      if (res.ok) {
        setShowAddProperty(false);
        setNewProperty({ name: "", type: "string", required: false, multiple: false, taxonomy: "", target_class: "", description: "" });
        await fetchConceptDetails(selectedConcept.uri);
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to add property:", error);
    }
  };

  const handleDeleteConcept = async (label: string) => {
    if (!confirm("Delete this concept?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/ontology/concepts/${encodeURIComponent(label)}?force=true`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSelectedConcept(null);
        await fetchConcepts();
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to delete concept:", error);
    }
  };

  const handleRemoveProperty = async (propertyName: string) => {
    if (!selectedConcept) return;
    if (!confirm(`Remove property "${propertyName}"?`)) return;
    
    try {
      const res = await fetch(
        `${API_BASE}/api/ontology/concepts/${encodeURIComponent(selectedConcept.label)}/properties/${encodeURIComponent(propertyName)}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        await fetchConceptDetails(selectedConcept.uri);
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to remove property:", error);
    }
  };

  const buildTree = (parentUri: string | null): Concept[] => {
    return concepts
      .filter(c => {
        const p = c.parent || null;
        // Root level: parent is null/undefined or not in our concept list
        if (parentUri === null) {
          return p === null || !concepts.some(other => other.uri === p);
        }
        return p === parentUri;
      })
      .sort((a, b) => a.label.localeCompare(b.label));
  };

  const toggleExpand = (uri: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(uri)) {
        next.delete(uri);
      } else {
        next.add(uri);
      }
      return next;
    });
  };

  const renderConceptNode = (concept: Concept, depth: number = 0) => {
    const children = buildTree(concept.uri);
    const hasChildren = children.length > 0;
    const isExpanded = expandedNodes.has(concept.uri);
    const isSelected = selectedConcept?.uri === concept.uri;

    return (
      <div key={concept.uri}>
        <div
          className={`flex items-center gap-1 py-1.5 px-2 cursor-pointer rounded transition-colors ${
            isSelected ? "bg-[#4B5A2D]/40" : "hover:bg-gray-800/50"
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => fetchConceptDetails(concept.uri)}
        >
          {hasChildren ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleExpand(concept.uri);
              }}
              className="p-0.5"
            >
              {isExpanded ? (
                <ChevronDown className="w-3 h-3 text-gray-500" />
              ) : (
                <ChevronRight className="w-3 h-3 text-gray-500" />
              )}
            </button>
          ) : (
            <span className="w-4" />
          )}
          
          <span className={`text-sm ${concept.abstract ? "italic text-gray-400" : "text-white"}`}>
            {concept.label}
          </span>
          
          {concept.abstract && (
            <span className="text-[10px] text-gray-500 ml-1">(abstract)</span>
          )}
          
          {concept.collection && (
            <span className="text-[10px] text-[#829646] ml-1">[{concept.collection}]</span>
          )}
        </div>
        
        {hasChildren && isExpanded && (
          <div>
            {children.map(child => renderConceptNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex">
      <div className="w-72 border-r border-border bg-secondary/20 flex flex-col">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-bold uppercase text-gray-500">Concept Hierarchy</span>
          <button
            onClick={() => setShowCreateConcept(true)}
            className="p-1.5 hover:bg-gray-700 rounded transition-colors"
            title="Create Concept"
          >
            <Plus className="w-4 h-4 text-[#6EBE46]" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto py-2">
          {isLoading ? (
            <div className="p-4 text-center">
              <Loader2 className="w-5 h-5 animate-spin mx-auto text-gray-500" />
            </div>
          ) : concepts.length === 0 ? (
            <div className="p-4 text-center text-xs text-gray-500">
              No concepts yet.
              <br />
              Click + to create one.
            </div>
          ) : (
            buildTree(null).map(concept => renderConceptNode(concept))
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedConcept ? (
          <>
            <div className="p-4 border-b border-border">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold text-white">{selectedConcept.label}</h2>
                  <p className="text-xs text-gray-500 font-mono">{selectedConcept.uri}</p>
                  {selectedConcept.definition && (
                    <p className="text-sm text-gray-400 mt-2">{selectedConcept.definition}</p>
                  )}
                </div>
                <button
                  onClick={() => handleDeleteConcept(selectedConcept.label)}
                  className="p-2 hover:bg-red-900/50 rounded transition-colors"
                  title="Delete Concept"
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
              
              <div className="flex flex-wrap gap-2 mt-3">
                {selectedConcept.abstract && (
                  <span className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300">
                    Abstract
                  </span>
                )}
                {selectedConcept.collection && (
                  <span className="px-2 py-0.5 bg-[#4B5A2D]/50 rounded text-xs text-[#A0C060]">
                    Collection: {selectedConcept.collection}
                  </span>
                )}
                {selectedConcept.parent && (
                  <span className="px-2 py-0.5 bg-blue-900/50 rounded text-xs text-blue-300">
                    Parent: {concepts.find(c => c.uri === selectedConcept.parent)?.label || selectedConcept.parent}
                  </span>
                )}
                {selectedConcept.abox_count !== undefined && (
                  <span className="px-2 py-0.5 bg-purple-900/50 rounded text-xs text-purple-300">
                    {selectedConcept.abox_count} instances
                  </span>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-white">Properties</h3>
                <button
                  onClick={() => setShowAddProperty(true)}
                  className="neo-button-secondary px-3 py-1.5 text-xs flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" />
                  Add Property
                </button>
              </div>
              
              {selectedConcept.properties && selectedConcept.properties.length > 0 ? (
                <div className="space-y-2">
                  {selectedConcept.properties.map((prop) => (
                    <div
                      key={prop.name}
                      className={`neo-card p-3 bg-card group ${prop.inherited_from ? "opacity-70" : ""}`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-white">{prop.name}</span>
                            <span className="text-xs text-gray-500">{prop.type}</span>
                            {prop.required && (
                              <span className="text-xs text-red-400">required</span>
                            )}
                            {prop.multiple && (
                              <span className="text-xs text-blue-400">multi</span>
                            )}
                            {prop.type === "reference" && prop.target_class && (
                              <span className="text-xs text-purple-400">→ {prop.target_class}</span>
                            )}
                          </div>
                          {prop.taxonomy && (
                            <div className="text-xs text-[#6EBE46] mt-1">
                              → taxonomy: {prop.taxonomy}
                            </div>
                          )}
                          {prop.description && (
                            <p className="text-xs text-gray-500 mt-1">{prop.description}</p>
                          )}
                          {prop.inherited_from && (
                            <p className="text-xs text-yellow-500 mt-1">
                              inherited from: {concepts.find(c => c.uri === prop.inherited_from)?.label || prop.inherited_from}
                            </p>
                          )}
                        </div>
                        {!prop.inherited_from && (
                          <button
                            onClick={() => handleRemoveProperty(prop.name)}
                            className="p-1 hover:bg-red-900/50 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <X className="w-3 h-3 text-red-400" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <Settings className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No properties defined</p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <Layers className="w-16 h-16 mx-auto mb-4 opacity-30" />
              <p>Select a concept to view details</p>
            </div>
          </div>
        )}
      </div>

      {showCreateConcept && (
        <Modal onClose={() => setShowCreateConcept(false)} title="Create Concept">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">URI *</label>
              <input
                type="text"
                value={newConcept.uri}
                onChange={(e) => setNewConcept({ ...newConcept, uri: e.target.value })}
                placeholder="e.g., proto:concept/LibraryModule"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Label *</label>
              <input
                type="text"
                value={newConcept.label}
                onChange={(e) => setNewConcept({ ...newConcept, label: e.target.value })}
                placeholder="e.g., Library Module"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Definition</label>
              <textarea
                value={newConcept.definition}
                onChange={(e) => setNewConcept({ ...newConcept, definition: e.target.value })}
                placeholder="What does this concept represent?"
                className="neo-input w-full h-16 resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Parent Concept</label>
              <select
                value={newConcept.parent}
                onChange={(e) => setNewConcept({ ...newConcept, parent: e.target.value })}
                className="neo-input w-full"
              >
                <option value="">None (root level)</option>
                {concepts.map((c) => (
                  <option key={c.uri} value={c.label}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Collection Name</label>
              <input
                type="text"
                value={newConcept.collection}
                onChange={(e) => setNewConcept({ ...newConcept, collection: e.target.value })}
                placeholder="e.g., LibraryModule (leave empty for abstract)"
                className="neo-input w-full"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={newConcept.abstract}
                onChange={(e) => setNewConcept({ ...newConcept, abstract: e.target.checked })}
                className="w-4 h-4"
              />
              <span className="text-gray-300">Abstract (cannot be instantiated directly)</span>
            </label>
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setShowCreateConcept(false)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateConcept}
                disabled={!newConcept.uri || !newConcept.label}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showAddProperty && (
        <Modal onClose={() => setShowAddProperty(false)} title="Add Property">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Name *</label>
              <input
                type="text"
                value={newProperty.name}
                onChange={(e) => setNewProperty({ ...newProperty, name: e.target.value })}
                placeholder="e.g., category, tactic, status"
                className="neo-input w-full"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Type</label>
              <select
                value={newProperty.type}
                onChange={(e) => setNewProperty({ ...newProperty, type: e.target.value })}
                className="neo-input w-full"
              >
                <option value="string">string</option>
                <option value="integer">integer</option>
                <option value="boolean">boolean</option>
                <option value="datetime">datetime</option>
                <option value="double">double</option>
                <option value="uri">uri (SKOS concept)</option>
                <option value="reference">reference (link to another class)</option>
              </select>
            </div>
            {newProperty.type === "reference" && (
              <div>
                <label className="block text-xs font-semibold text-gray-400 mb-1">Target Class *</label>
                <select
                  value={newProperty.target_class}
                  onChange={(e) => setNewProperty({ ...newProperty, target_class: e.target.value })}
                  className="neo-input w-full"
                >
                  <option value="">Select target class...</option>
                  {concepts.map((c) => (
                    <option key={c.uri} value={c.label}>{c.label}</option>
                  ))}
                </select>
                <p className="text-[10px] text-gray-500 mt-1">
                  Creates an owl:ObjectProperty linking to instances of this class
                </p>
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Taxonomy (for controlled values)</label>
              <select
                value={newProperty.taxonomy}
                onChange={(e) => setNewProperty({ ...newProperty, taxonomy: e.target.value })}
                className="neo-input w-full"
              >
                <option value="">None (free text)</option>
                {taxonomies.map((t) => (
                  <option key={t.scheme_id} value={t.scheme_id}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Description</label>
              <input
                type="text"
                value={newProperty.description}
                onChange={(e) => setNewProperty({ ...newProperty, description: e.target.value })}
                placeholder="What does this property store?"
                className="neo-input w-full"
              />
            </div>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={newProperty.required}
                  onChange={(e) => setNewProperty({ ...newProperty, required: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Required</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={newProperty.multiple}
                  onChange={(e) => setNewProperty({ ...newProperty, multiple: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Multiple values (array)</span>
              </label>
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setShowAddProperty(false)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleAddProperty}
                disabled={!newProperty.name}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Add Property
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

// =====================================================
// RELATIONSHIPS TAB
// =====================================================

const RelationshipsTab: React.FC<{ onUpdate: () => void }> = ({ onUpdate }) => {
  const [relationships, setRelationships] = useState<RelationshipType[]>([]);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  
  const [newRelationship, setNewRelationship] = useState({
    uri: "",
    label: "",
    definition: "",
    domain: [] as string[],
    range: [] as string[],
    inverse: "",
    symmetric: false,
    transitive: false,
    functional: false,
  });

  useEffect(() => {
    fetchRelationships();
    fetchConcepts();
  }, []);

  const fetchRelationships = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ontology/relationships`);
      if (res.ok) {
        const data = await res.json();
        setRelationships(data.relationships);
      }
    } catch (error) {
      console.error("Failed to fetch relationships:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchConcepts = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/concepts`);
      if (res.ok) {
        const data = await res.json();
        setConcepts(data.concepts);
      }
    } catch (error) {
      console.error("Failed to fetch concepts:", error);
    }
  };

  const handleCreate = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/relationships`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: newRelationship.label,
          definition: newRelationship.definition,
          domain: newRelationship.domain,
          range: newRelationship.range,
          inverse: newRelationship.inverse || null,
          symmetric: newRelationship.symmetric,
          transitive: newRelationship.transitive,
          functional: newRelationship.functional,
        }),
      });
      if (res.ok) {
        setShowCreate(false);
        setNewRelationship({
          uri: "", label: "", definition: "",
          domain: [], range: [],
          inverse: "", symmetric: false, transitive: false, functional: false,
        });
        await fetchRelationships();
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to create relationship:", error);
    }
  };

  const handleDelete = async (label: string) => {
    if (!confirm("Delete this relationship type?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/ontology/relationships/${encodeURIComponent(label)}`, {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchRelationships();
        onUpdate();
      } else {
        const error = await res.json();
        alert(`Failed: ${error.detail}`);
      }
    } catch (error) {
      console.error("Failed to delete relationship:", error);
    }
  };

  const toggleDomain = (uri: string) => {
    setNewRelationship(prev => ({
      ...prev,
      domain: prev.domain.includes(uri)
        ? prev.domain.filter(d => d !== uri)
        : [...prev.domain, uri],
    }));
  };

  const toggleRange = (uri: string) => {
    setNewRelationship(prev => ({
      ...prev,
      range: prev.range.includes(uri)
        ? prev.range.filter(r => r !== uri)
        : [...prev.range, uri],
    }));
  };

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-bold text-white">Relationship Types</h2>
          <p className="text-xs text-gray-500">
            Define edge types with domain/range constraints
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="neo-button px-4 py-2 text-sm flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Add Relationship Type
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 animate-spin mx-auto text-gray-500" />
          </div>
        ) : relationships.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <GitBranch className="w-16 h-16 mx-auto mb-4 opacity-30" />
            <p>No relationship types defined</p>
            <p className="text-xs mt-1">Create relationship types to constrain edge creation</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {relationships.map((rel) => (
              <div key={rel.uri} className="neo-card p-4 bg-card group">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Link2 className="w-4 h-4 text-[#6EBE46]" />
                      <span className="font-bold text-white">{rel.label}</span>
                      <span className="text-xs text-gray-500 font-mono">{rel.uri}</span>
                    </div>
                    {rel.definition && (
                      <p className="text-sm text-gray-400 mt-1 ml-6">{rel.definition}</p>
                    )}
                    
                    <div className="mt-3 ml-6 grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <span className="text-gray-500 block mb-1">Domain (from):</span>
                        <div className="flex flex-wrap gap-1">
                          {(rel.domain || []).map((d) => (
                            <span key={d} className="px-1.5 py-0.5 bg-blue-900/50 text-blue-300 rounded">
                              {concepts.find(c => c.uri === d)?.label || d}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500 block mb-1">Range (to):</span>
                        <div className="flex flex-wrap gap-1">
                          {(rel.range || []).map((r) => (
                            <span key={r} className="px-1.5 py-0.5 bg-green-900/50 text-green-300 rounded">
                              {concepts.find(c => c.uri === r)?.label || r}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    
                    <div className="mt-2 ml-6 flex gap-2">
                      {rel.symmetric && (
                        <span className="text-xs text-yellow-400">↔ symmetric</span>
                      )}
                      {rel.transitive && (
                        <span className="text-xs text-purple-400">⟿ transitive</span>
                      )}
                      {rel.functional && (
                        <span className="text-xs text-cyan-400">𝑓 functional</span>
                      )}
                      {rel.inverse && (
                        <span className="text-xs text-gray-400">inverse: {rel.inverse}</span>
                      )}
                    </div>
                  </div>
                  
                  <button
                    onClick={() => handleDelete(rel.label)}
                    className="p-2 hover:bg-red-900/50 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Trash2 className="w-4 h-4 text-red-400" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal onClose={() => setShowCreate(false)} title="Create Relationship Type" width="lg">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-400 mb-1">URI *</label>
                <input
                  type="text"
                  value={newRelationship.uri}
                  onChange={(e) => setNewRelationship({ ...newRelationship, uri: e.target.value })}
                  placeholder="e.g., proto:rel/PRODUCES"
                  className="neo-input w-full"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-400 mb-1">Label *</label>
                <input
                  type="text"
                  value={newRelationship.label}
                  onChange={(e) => setNewRelationship({ ...newRelationship, label: e.target.value })}
                  placeholder="e.g., PRODUCES"
                  className="neo-input w-full"
                />
              </div>
            </div>
            
            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Definition</label>
              <textarea
                value={newRelationship.definition}
                onChange={(e) => setNewRelationship({ ...newRelationship, definition: e.target.value })}
                placeholder="What does this relationship mean?"
                className="neo-input w-full h-16 resize-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-400 mb-2">Domain (source concepts) *</label>
                <div className="max-h-32 overflow-y-auto border border-border rounded p-2 space-y-1">
                  {concepts.map((c) => (
                    <label key={c.uri} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-800 p-1 rounded">
                      <input
                        type="checkbox"
                        checked={newRelationship.domain.includes(c.uri)}
                        onChange={() => toggleDomain(c.uri)}
                        className="w-4 h-4"
                      />
                      <span className="text-gray-300">{c.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-400 mb-2">Range (target concepts) *</label>
                <div className="max-h-32 overflow-y-auto border border-border rounded p-2 space-y-1">
                  {concepts.map((c) => (
                    <label key={c.uri} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-800 p-1 rounded">
                      <input
                        type="checkbox"
                        checked={newRelationship.range.includes(c.uri)}
                        onChange={() => toggleRange(c.uri)}
                        className="w-4 h-4"
                      />
                      <span className="text-gray-300">{c.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-400 mb-1">Inverse Relationship (optional)</label>
              <input
                type="text"
                value={newRelationship.inverse}
                onChange={(e) => setNewRelationship({ ...newRelationship, inverse: e.target.value })}
                placeholder="e.g., proto:rel/PRODUCED_BY"
                className="neo-input w-full"
              />
            </div>

            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={newRelationship.symmetric}
                  onChange={(e) => setNewRelationship({ ...newRelationship, symmetric: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Symmetric (A→B implies B→A)</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={newRelationship.transitive}
                  onChange={(e) => setNewRelationship({ ...newRelationship, transitive: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Transitive (A→B→C implies A→C)</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={newRelationship.functional}
                  onChange={(e) => setNewRelationship({ ...newRelationship, functional: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-gray-300">Functional (at most one value)</span>
              </label>
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={() => setShowCreate(false)}
                className="flex-1 neo-button-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!newRelationship.uri || !newRelationship.label || newRelationship.domain.length === 0 || newRelationship.range.length === 0}
                className="flex-1 neo-button disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

// =====================================================
// ADVANCED TAB (TTL Editor)
// =====================================================

interface TTLSnippet {
  label: string;
  description: string;
  ttl: string;
}

interface TTLValidation {
  valid: boolean;
  triple_count: number;
  classes?: string[];
  properties?: string[];
  individuals?: string[];
  preview?: string;
  error?: string;
}

const AdvancedTab: React.FC<{ onUpdate: () => void }> = ({ onUpdate }) => {
  const [ttlContent, setTtlContent] = useState("");
  const [snippets, setSnippets] = useState<TTLSnippet[]>([]);
  const [validation, setValidation] = useState<TTLValidation | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [commitResult, setCommitResult] = useState<string | null>(null);
  const [namedGraph, setNamedGraph] = useState("");
  const [schemaContext, setSchemaContext] = useState<string>("");
  const [showSchema, setShowSchema] = useState(false);

  useEffect(() => {
    fetchSnippets();
    fetchSchema();
  }, []);

  const fetchSnippets = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ontology/ttl/snippets`);
      if (res.ok) {
        const data = await res.json();
        setSnippets(data.snippets || []);
      }
    } catch (err) {
      console.error("Failed to fetch snippets:", err);
    }
  };

  const fetchSchema = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/query/schema`);
      if (res.ok) {
        const data = await res.json();
        setSchemaContext(data.schema || "");
      }
    } catch (err) {
      // Schema endpoint may not exist
    }
  };

  const handleValidate = async () => {
    if (!ttlContent.trim()) return;
    setIsValidating(true);
    setValidation(null);
    setCommitResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/ontology/ttl/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ttl: ttlContent }),
      });
      const data = await res.json();
      setValidation(data);
    } catch (err: any) {
      setValidation({ valid: false, triple_count: 0, error: err.message });
    } finally {
      setIsValidating(false);
    }
  };

  const handleCommit = async () => {
    if (!ttlContent.trim() || !validation?.valid) return;
    setIsCommitting(true);
    setCommitResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/ontology/ttl/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ttl: ttlContent,
          named_graph: namedGraph || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setCommitResult(`✓ Committed ${data.triple_count} triples to GraphDB`);
        onUpdate();
      } else {
        const err = await res.json();
        setCommitResult(`✗ ${err.detail}`);
      }
    } catch (err: any) {
      setCommitResult(`✗ ${err.message}`);
    } finally {
      setIsCommitting(false);
    }
  };

  const loadSnippet = (snippet: TTLSnippet) => {
    if (ttlContent.trim()) {
      setTtlContent(ttlContent + "\n\n# --- " + snippet.label + " ---\n" + snippet.ttl);
    } else {
      setTtlContent(snippet.ttl);
    }
    setValidation(null);
    setCommitResult(null);
  };

  return (
    <div className="h-full flex">
      {/* Snippets Sidebar */}
      <div className="w-64 border-r border-border bg-secondary/20 flex flex-col">
        <div className="p-3 border-b border-border">
          <span className="text-xs font-bold uppercase text-gray-500">TTL Snippets</span>
          <p className="text-[10px] text-gray-600 mt-1">Click to insert into editor</p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {snippets.map((snippet, i) => (
            <button
              key={i}
              onClick={() => loadSnippet(snippet)}
              className="w-full text-left p-2.5 bg-[#111] border border-[#1a1a1a] rounded-lg hover:border-[#6EBE46]/30 transition-colors group"
            >
              <div className="text-xs font-medium text-white group-hover:text-[#6EBE46]">
                {snippet.label}
              </div>
              <div className="text-[10px] text-gray-500 mt-0.5">
                {snippet.description}
              </div>
            </button>
          ))}
        </div>

        {/* Schema Context Toggle */}
        <div className="border-t border-border p-3">
          <button
            onClick={() => setShowSchema(!showSchema)}
            className="text-xs text-gray-500 hover:text-[#6EBE46] flex items-center gap-1 w-full"
          >
            <Database className="w-3 h-3" />
            {showSchema ? "Hide" : "Show"} Schema Context
          </button>
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 flex flex-col">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-[#0e0e0e]">
          <div className="flex items-center gap-3">
            <FileCode className="w-4 h-4 text-[#E6AA32]" />
            <span className="text-sm font-medium text-white">Turtle (TTL) Editor</span>
            <span className="text-[10px] text-gray-500">
              Write raw RDF triples for advanced ontology features
            </span>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={namedGraph}
              onChange={(e) => setNamedGraph(e.target.value)}
              placeholder="Named graph (optional)"
              className="neo-input text-xs px-2 py-1 w-48"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            />
            <button
              onClick={handleValidate}
              disabled={isValidating || !ttlContent.trim()}
              className="neo-button-secondary px-3 py-1.5 text-xs flex items-center gap-1 disabled:opacity-50"
            >
              {isValidating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
              Validate
            </button>
            <button
              onClick={handleCommit}
              disabled={isCommitting || !validation?.valid}
              className="neo-button px-3 py-1.5 text-xs flex items-center gap-1 disabled:opacity-50"
            >
              {isCommitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
              Commit to GraphDB
            </button>
          </div>
        </div>

        {/* Editor Area */}
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col">
            <textarea
              value={ttlContent}
              onChange={(e) => {
                setTtlContent(e.target.value);
                setValidation(null);
                setCommitResult(null);
              }}
              placeholder={`@prefix proto: <https://proto.atlas/ontology/> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .

# Write your Turtle triples here...
# Use snippets on the left for common patterns.`}
              className="flex-1 p-4 bg-[#080808] text-[#8B8B8B] resize-none focus:outline-none"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "13px",
                lineHeight: "1.6",
                tabSize: 4,
              }}
              spellCheck={false}
            />

            {/* Validation / Commit Result Bar */}
            {(validation || commitResult) && (
              <div className={`px-4 py-2 border-t border-border text-xs ${
                commitResult
                  ? commitResult.startsWith("✓") ? "bg-green-900/20 text-green-400" : "bg-red-900/20 text-red-400"
                  : validation?.valid
                    ? "bg-green-900/20 text-green-400"
                    : "bg-red-900/20 text-red-400"
              }`} style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                {commitResult ? (
                  <span>{commitResult}</span>
                ) : validation?.valid ? (
                  <div>
                    <span className="font-medium">✓ Valid — </span>
                    <span>{validation.preview}</span>
                    {validation.classes && validation.classes.length > 0 && (
                      <span className="ml-3 text-gray-500">
                        Classes: {validation.classes.map(c => c.split("/").pop()).join(", ")}
                      </span>
                    )}
                  </div>
                ) : (
                  <div>
                    <span className="font-medium">✗ Invalid — </span>
                    <span>{validation?.error}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Schema Context Sidebar */}
          {showSchema && (
            <div className="w-72 border-l border-border bg-[#0a0a0a] overflow-y-auto">
              <div className="p-3 border-b border-border">
                <span className="text-xs font-bold uppercase text-gray-500">Schema Reference</span>
              </div>
              <pre
                className="p-3 text-[10px] text-gray-500 whitespace-pre-wrap"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              >
                {schemaContext || "Schema not available — is the query engine running?"}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// =====================================================
// MODAL COMPONENT
// =====================================================

const Modal: React.FC<{
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  width?: "sm" | "md" | "lg";
}> = ({ onClose, title, children, width = "md" }) => {
  const widthClass = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-2xl",
  }[width];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className={`neo-card p-6 bg-card ${widthClass} w-full mx-4 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

export default OntologyManager;