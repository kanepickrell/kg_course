/**
 * PipelineBuilder.tsx
 * 
 * Main UI for creating and managing data pipelines in ProtoGraph.
 * Users can:
 * - View all existing pipelines
 * - Create new pipelines with visual configuration
 * - Generate api.ts code for external apps
 * 
 * Dependencies: React, shadcn/ui components, lucide-react icons
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  Plus,
  Trash2,
  Download,
  Play,
  Settings,
  Database,
  Code,
  Filter,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Copy,
  ExternalLink,
  Loader2,
  FileCode,
  Pencil,
} from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

interface Pipeline {
  _key: string;  // This is what we use internally
  key?: string;  // This is what the API returns in list
  name: string;
  description?: string;
  status: 'active' | 'inactive' | 'draft';
  source: {
    collection: string;
    mergePayload: boolean;
    payloadDir?: string;
    payloadFields: string[];
  };
  endpoints: Record<string, {
    path: string;
    method: string;
    description?: string;
  }>;
  filters: Array<{
    param: string;
    field: string | string[];
    op: string;
  }>;
  pagination: {
    enabled: boolean;
    defaultLimit: number;
    maxLimit: number;
  };
  caching: {
    enabled: boolean;
    ttlSeconds: number;
  };
  codeGen?: {
    typescript?: {
      constName?: string;
      envVar?: string;
      defaultBaseUrl?: string;
    };
  };
  metadata?: {
    createdAt?: string;
    createdBy?: string;
    updatedAt?: string;
  };
}

interface Collection {
  name: string;
  count: number;
  type: 'document' | 'edge';
}

// =============================================================================
// API Service
// =============================================================================

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const pipelineApi = {
  async listPipelines(): Promise<{ pipelines: Pipeline[] }> {
    const res = await fetch(`${API_BASE}/api/pipelines`);
    if (!res.ok) throw new Error('Failed to fetch pipelines');
    const data = await res.json();
    // Map 'key' from API to '_key' for internal use
    return {
      ...data,
      pipelines: (data.pipelines || []).map((p: any) => ({
        ...p,
        _key: p.key || p._key,  // Handle both formats
      })),
    };
  },

  async createPipeline(pipeline: Partial<Pipeline>): Promise<Pipeline> {
    const res = await fetch(`${API_BASE}/api/pipelines`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pipeline),
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Failed to create pipeline');
    }
    return res.json();
  },

  async updatePipeline(key: string, updates: Partial<Pipeline>): Promise<Pipeline> {
    const res = await fetch(`${API_BASE}/api/pipelines/${key}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to update pipeline');
    return res.json();
  },

  async deletePipeline(key: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/pipelines/${key}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete pipeline');
  },

  async executePipeline(key: string, params?: Record<string, string>): Promise<any> {
    const url = new URL(`${API_BASE}/api/pipelines/${key}`);
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.append(k, v));
    }
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error('Failed to execute pipeline');
    return res.json();
  },

  async generateCode(key: string): Promise<string> {
    const res = await fetch(`${API_BASE}/api/pipelines/${key}/generate`);
    if (!res.ok) throw new Error('Failed to generate code');
    return res.text();
  },

  async getCollections(): Promise<Collection[]> {
    const res = await fetch(`${API_BASE}/explore-db`);
    if (!res.ok) throw new Error('Failed to fetch collections');
    const data = await res.json();
    return data.collections.map((name: string) => ({
      name,
      count: 0,
      type: 'document' as const,
    }));
  },
};

// =============================================================================
// Pipeline List Component
// =============================================================================

interface PipelineListProps {
  pipelines: Pipeline[];
  onSelect: (pipeline: Pipeline) => void;
  onDelete: (key: string) => void;
  onRefresh: () => void;
  loading: boolean;
}

function PipelineList({ pipelines, onSelect, onDelete, onRefresh, loading }: PipelineListProps) {
  return (
    <Card className="border-[#2d2d2d] bg-[#111]">
      <CardHeader className="pb-3 border-b border-[#2d2d2d]">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg" style={{ fontFamily: "'Rajdhani', sans-serif" }}>Data Pipelines</CardTitle>
            <CardDescription style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
              Configure how your data is exposed via API
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} className="border-[#2d2d2d] text-[#888] hover:border-[#6EBE46] hover:text-[#6EBE46]">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {pipelines.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-20 h-20 rounded-full mx-auto mb-5 flex items-center justify-center bg-[#1a1a1a] border border-[#2d2d2d]">
              <Database className="h-8 w-8 text-[#A09678]" />
            </div>
            <p className="text-[#ccc] font-semibold mb-1" style={{ fontFamily: "'Rajdhani', sans-serif", fontSize: 16 }}>
              No pipelines configured yet
            </p>
            <p className="text-[#666] mb-6" style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
              Create your first pipeline to expose collection data via API
            </p>
            <div className="flex items-center justify-center gap-6 text-[#555]" style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}>
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#6EBE46]" />
                REST endpoints
              </div>
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#E6AA32]" />
                Query filters
              </div>
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#A09678]" />
                Code generation
              </div>
            </div>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Endpoints</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pipelines.map((pipeline) => (
                <TableRow key={pipeline._key}>
                  <TableCell>
                    <div>
                      <div className="font-medium">{pipeline.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {pipeline._key}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{pipeline.source.collection}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={pipeline.status === 'active' ? 'default' : 'secondary'}
                    >
                      {pipeline.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {Object.keys(pipeline.endpoints || {}).length} endpoints
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSelect(pipeline)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onDelete(pipeline._key)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Pipeline Editor Component
// =============================================================================

interface PipelineEditorProps {
  pipeline?: Pipeline | null;
  collections: Collection[];
  onSave: (pipeline: Partial<Pipeline>) => Promise<void>;
  onCancel: () => void;
}

const DEFAULT_PIPELINE: Partial<Pipeline> = {
  name: '',
  description: '',
  status: 'draft',
  source: {
    collection: '',
    mergePayload: false,
    payloadDir: './data/payloads',
    payloadFields: [],
  },
  endpoints: {
    list: { path: '', method: 'GET', description: 'Get all items' },
    detail: { path: '', method: 'GET', description: 'Get item by key' },
    categories: { path: '', method: 'GET', description: 'Get categories' },
    tactics: { path: '', method: 'GET', description: 'Get tactics' },
    stats: { path: '', method: 'GET', description: 'Get statistics' },
  },
  filters: [],
  pagination: {
    enabled: true,
    defaultLimit: 100,
    maxLimit: 500,
  },
  caching: {
    enabled: true,
    ttlSeconds: 300,
  },
  codeGen: {
    typescript: {
      constName: 'API_CONFIG',
      envVar: 'VITE_API_URL',
      defaultBaseUrl: 'http://localhost:8000',
    },
  },
};

const PAYLOAD_FIELD_OPTIONS = [
  'inputs',
  'outputs',
  'parameters',
  'requirements',
  'executionType',
  'cobaltStrikeCommand',
  'robotKeyword',
  'robotTemplate',
  'shellCommand',
  'estimatedDuration',
  'subcategory',
  'icon',
];

const FILTER_OPERATORS = [
  { value: 'eq', label: 'Equals' },
  { value: 'neq', label: 'Not Equals' },
  { value: 'contains', label: 'Contains' },
  { value: 'in', label: 'In List' },
  { value: 'gt', label: 'Greater Than' },
  { value: 'lt', label: 'Less Than' },
];

function PipelineEditor({ pipeline, collections, onSave, onCancel }: PipelineEditorProps) {
  const [formData, setFormData] = useState<Partial<Pipeline>>(
    pipeline || DEFAULT_PIPELINE
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!pipeline;

  // Generate key from name
  const generateKey = (name: string) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
  };

  // Update endpoints when collection changes
  const updateEndpoints = (collection: string) => {
    const basePath = `/api/pipelines/${generateKey(formData.name || collection)}`;
    setFormData((prev) => ({
      ...prev,
      endpoints: {
        list: { path: basePath, method: 'GET', description: 'Get all items' },
        detail: { path: `${basePath}/detail/{key}`, method: 'GET', description: 'Get item by key' },
        categories: { path: `${basePath}/categories`, method: 'GET', description: 'Get categories' },
        tactics: { path: `${basePath}/tactics`, method: 'GET', description: 'Get tactics' },
        stats: { path: `${basePath}/stats`, method: 'GET', description: 'Get statistics' },
      },
    }));
  };

  // Add filter
  const addFilter = () => {
    setFormData((prev) => ({
      ...prev,
      filters: [
        ...(prev.filters || []),
        { param: '', field: '', op: 'eq' },
      ],
    }));
  };

  // Remove filter
  const removeFilter = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      filters: prev.filters?.filter((_, i) => i !== index),
    }));
  };

  // Update filter
  const updateFilter = (index: number, updates: Partial<Pipeline['filters'][0]>) => {
    setFormData((prev) => ({
      ...prev,
      filters: prev.filters?.map((f, i) => (i === index ? { ...f, ...updates } : f)),
    }));
  };

  // Handle save
  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      // Validate
      if (!formData.name) throw new Error('Pipeline name is required');
      if (!formData.source?.collection) throw new Error('Source collection is required');

      // Add key if new
      const pipelineData = {
        ...formData,
        _key: isEditing ? pipeline._key : generateKey(formData.name),
      };

      await onSave(pipelineData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save pipeline');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEditing ? 'Edit Pipeline' : 'Create New Pipeline'}</CardTitle>
        <CardDescription>
          {isEditing
            ? `Editing: ${pipeline.name}`
            : 'Configure how your data collection is exposed via API'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="basic" className="space-y-4">
          <TabsList>
            <TabsTrigger value="basic">Basic</TabsTrigger>
            <TabsTrigger value="source">Source</TabsTrigger>
            <TabsTrigger value="filters">Filters</TabsTrigger>
            <TabsTrigger value="endpoints">Endpoints</TabsTrigger>
            <TabsTrigger value="codegen">Code Gen</TabsTrigger>
          </TabsList>

          {/* Basic Tab */}
          <TabsContent value="basic" className="space-y-4">
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="name">Pipeline Name *</Label>
                <Input
                  id="name"
                  placeholder="e.g., Library Modules - Operator"
                  value={formData.name || ''}
                  onChange={(e) => {
                    setFormData((prev) => ({ ...prev, name: e.target.value }));
                    if (!isEditing) {
                      updateEndpoints(formData.source?.collection || '');
                    }
                  }}
                />
                {formData.name && (
                  <p className="text-xs text-muted-foreground">
                    Key: <code>{generateKey(formData.name)}</code>
                  </p>
                )}
              </div>

              <div className="grid gap-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  placeholder="What is this pipeline for?"
                  value={formData.description || ''}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                  }
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="status">Status</Label>
                <Select
                  value={formData.status}
                  onValueChange={(value: Pipeline['status']) =>
                    setFormData((prev) => ({ ...prev, status: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="draft">Draft</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </TabsContent>

          {/* Source Tab */}
          <TabsContent value="source" className="space-y-4">
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="collection">Source Collection *</Label>
                <Select
                  value={formData.source?.collection || ''}
                  onValueChange={(value) => {
                    setFormData((prev) => ({
                      ...prev,
                      source: { ...prev.source!, collection: value },
                    }));
                    updateEndpoints(value);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a collection" />
                  </SelectTrigger>
                  <SelectContent>
                    {collections.map((coll) => (
                      <SelectItem key={coll.name} value={coll.name}>
                        {coll.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Merge Payload Files</Label>
                  <p className="text-xs text-muted-foreground">
                    Load additional data from JSON payload files
                  </p>
                </div>
                <Switch
                  checked={formData.source?.mergePayload || false}
                  onCheckedChange={(checked) =>
                    setFormData((prev) => ({
                      ...prev,
                      source: { ...prev.source!, mergePayload: checked },
                    }))
                  }
                />
              </div>

              {formData.source?.mergePayload && (
                <>
                  <div className="grid gap-2">
                    <Label htmlFor="payloadDir">Payload Directory</Label>
                    <Input
                      id="payloadDir"
                      value={formData.source?.payloadDir || './data/payloads'}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          source: { ...prev.source!, payloadDir: e.target.value },
                        }))
                      }
                    />
                  </div>

                  <div className="grid gap-2">
                    <Label>Payload Fields to Merge</Label>
                    <div className="flex flex-wrap gap-2">
                      {PAYLOAD_FIELD_OPTIONS.map((field) => (
                        <Badge
                          key={field}
                          variant={
                            formData.source?.payloadFields?.includes(field)
                              ? 'default'
                              : 'outline'
                          }
                          className="cursor-pointer"
                          onClick={() => {
                            const current = formData.source?.payloadFields || [];
                            const updated = current.includes(field)
                              ? current.filter((f) => f !== field)
                              : [...current, field];
                            setFormData((prev) => ({
                              ...prev,
                              source: { ...prev.source!, payloadFields: updated },
                            }));
                          }}
                        >
                          {field}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </>
              )}

              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Pagination</Label>
                    <p className="text-xs text-muted-foreground">Enable result pagination</p>
                  </div>
                  <Switch
                    checked={formData.pagination?.enabled || false}
                    onCheckedChange={(checked) =>
                      setFormData((prev) => ({
                        ...prev,
                        pagination: { ...prev.pagination!, enabled: checked },
                      }))
                    }
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Caching</Label>
                    <p className="text-xs text-muted-foreground">Cache responses</p>
                  </div>
                  <Switch
                    checked={formData.caching?.enabled || false}
                    onCheckedChange={(checked) =>
                      setFormData((prev) => ({
                        ...prev,
                        caching: { ...prev.caching!, enabled: checked },
                      }))
                    }
                  />
                </div>
              </div>

              {formData.pagination?.enabled && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label>Default Limit</Label>
                    <Input
                      type="number"
                      value={formData.pagination?.defaultLimit || 100}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          pagination: {
                            ...prev.pagination!,
                            defaultLimit: parseInt(e.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>Max Limit</Label>
                    <Input
                      type="number"
                      value={formData.pagination?.maxLimit || 500}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          pagination: {
                            ...prev.pagination!,
                            maxLimit: parseInt(e.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              )}

              {formData.caching?.enabled && (
                <div className="grid gap-2">
                  <Label>Cache TTL (seconds)</Label>
                  <Input
                    type="number"
                    value={formData.caching?.ttlSeconds || 300}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        caching: {
                          ...prev.caching!,
                          ttlSeconds: parseInt(e.target.value),
                        },
                      }))
                    }
                  />
                </div>
              )}
            </div>
          </TabsContent>

          {/* Filters Tab */}
          <TabsContent value="filters" className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-medium">Dynamic Filters</h4>
                <p className="text-sm text-muted-foreground">
                  Define query parameters that consumers can use to filter results
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={addFilter}>
                <Plus className="h-4 w-4 mr-2" />
                Add Filter
              </Button>
            </div>

            {formData.filters?.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground border-2 border-dashed rounded-lg">
                <Filter className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No filters configured</p>
                <p className="text-xs">Add filters to allow consumers to query your data</p>
              </div>
            ) : (
              <div className="space-y-3">
                {formData.filters?.map((filter, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-3 p-3 border rounded-lg"
                  >
                    <div className="flex-1 grid grid-cols-3 gap-3">
                      <div>
                        <Label className="text-xs">Query Param</Label>
                        <Input
                          placeholder="e.g., category"
                          value={filter.param}
                          onChange={(e) =>
                            updateFilter(index, { param: e.target.value })
                          }
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Document Field</Label>
                        <Input
                          placeholder="e.g., category"
                          value={Array.isArray(filter.field) ? filter.field.join(', ') : filter.field}
                          onChange={(e) =>
                            updateFilter(index, { field: e.target.value })
                          }
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Operator</Label>
                        <Select
                          value={filter.op}
                          onValueChange={(value) => updateFilter(index, { op: value })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {FILTER_OPERATORS.map((op) => (
                              <SelectItem key={op.value} value={op.value}>
                                {op.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeFilter(index)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Common filter presets */}
            <div className="pt-4">
              <h4 className="text-sm font-medium mb-2">Quick Add Presets</h4>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setFormData((prev) => ({
                      ...prev,
                      filters: [
                        ...(prev.filters || []),
                        { param: 'category', field: 'category', op: 'eq' },
                      ],
                    }));
                  }}
                >
                  + Category
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setFormData((prev) => ({
                      ...prev,
                      filters: [
                        ...(prev.filters || []),
                        { param: 'tactic', field: 'tactic', op: 'eq' },
                      ],
                    }));
                  }}
                >
                  + Tactic
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setFormData((prev) => ({
                      ...prev,
                      filters: [
                        ...(prev.filters || []),
                        { param: 'search', field: 'name,description', op: 'contains' },
                      ],
                    }));
                  }}
                >
                  + Search
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setFormData((prev) => ({
                      ...prev,
                      filters: [
                        ...(prev.filters || []),
                        { param: 'risk_level', field: 'riskLevel', op: 'eq' },
                      ],
                    }));
                  }}
                >
                  + Risk Level
                </Button>
              </div>
            </div>
          </TabsContent>

          {/* Endpoints Tab */}
          <TabsContent value="endpoints" className="space-y-4">
            <div>
              <h4 className="font-medium">Generated Endpoints</h4>
              <p className="text-sm text-muted-foreground">
                These endpoints will be created based on your pipeline configuration
              </p>
            </div>

            <div className="space-y-2">
              {Object.entries(formData.endpoints || {}).map(([key, endpoint]) => (
                <div
                  key={key}
                  className="flex items-center gap-3 p-3 border rounded-lg"
                >
                  <Badge variant="outline" className="font-mono">
                    {endpoint.method}
                  </Badge>
                  <code className="flex-1 text-sm">{endpoint.path || '(auto-generated)'}</code>
                  <span className="text-sm text-muted-foreground">{endpoint.description}</span>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* Code Gen Tab */}
          <TabsContent value="codegen" className="space-y-4">
            <div>
              <h4 className="font-medium">TypeScript Code Generation</h4>
              <p className="text-sm text-muted-foreground">
                Configure how the api.ts file is generated for consumers
              </p>
            </div>

            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label>Const Name</Label>
                <Input
                  value={formData.codeGen?.typescript?.constName || 'API_CONFIG'}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      codeGen: {
                        ...prev.codeGen,
                        typescript: {
                          ...prev.codeGen?.typescript,
                          constName: e.target.value,
                        },
                      },
                    }))
                  }
                />
              </div>

              <div className="grid gap-2">
                <Label>Environment Variable</Label>
                <Input
                  value={formData.codeGen?.typescript?.envVar || 'VITE_API_URL'}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      codeGen: {
                        ...prev.codeGen,
                        typescript: {
                          ...prev.codeGen?.typescript,
                          envVar: e.target.value,
                        },
                      },
                    }))
                  }
                />
              </div>

              <div className="grid gap-2">
                <Label>Default Base URL</Label>
                <Input
                  value={formData.codeGen?.typescript?.defaultBaseUrl || 'http://localhost:8000'}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      codeGen: {
                        ...prev.codeGen,
                        typescript: {
                          ...prev.codeGen?.typescript,
                          defaultBaseUrl: e.target.value,
                        },
                      },
                    }))
                  }
                />
              </div>
            </div>
          </TabsContent>
        </Tabs>

        {error && (
          <div className="mt-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {isEditing ? 'Update Pipeline' : 'Create Pipeline'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Code Preview Dialog
// =============================================================================

interface CodePreviewProps {
  pipelineKey: string;
  pipelineName: string;
}

function CodePreviewDialog({ pipelineKey, pipelineName }: CodePreviewProps) {
  const [code, setCode] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadCode = async () => {
    setLoading(true);
    try {
      const generatedCode = await pipelineApi.generateCode(pipelineKey);
      setCode(generatedCode);
    } catch (err) {
      setCode('// Failed to generate code');
    } finally {
      setLoading(false);
    }
  };

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadCode = () => {
    const blob = new Blob([code], { type: 'text/typescript' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'api.ts';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" onClick={loadCode}>
          <Code className="h-4 w-4 mr-2" />
          Generate Code
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>Generated api.ts</DialogTitle>
          <DialogDescription>
            Drop this file into your consumer app (e.g., Operator)
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <ScrollArea className="h-[400px] border rounded-lg">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : (
              <pre className="p-4 text-sm font-mono">{code}</pre>
            )}
          </ScrollArea>

          <div className="absolute top-2 right-2 flex gap-2">
            <Button variant="ghost" size="sm" onClick={copyCode}>
              {copied ? (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={copyCode}>
            <Copy className="h-4 w-4 mr-2" />
            {copied ? 'Copied!' : 'Copy'}
          </Button>
          <Button onClick={downloadCode}>
            <Download className="h-4 w-4 mr-2" />
            Download api.ts
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Pipeline Builder Component
// =============================================================================

export function PipelineBuilder() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPipeline, setSelectedPipeline] = useState<Pipeline | null>(null);
  const [showEditor, setShowEditor] = useState(false);

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [pipelinesData, collectionsData] = await Promise.all([
        pipelineApi.listPipelines(),
        pipelineApi.getCollections(),
      ]);
      setPipelines(pipelinesData.pipelines || []);
      setCollections(collectionsData);
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle save
  const handleSave = async (pipelineData: Partial<Pipeline>) => {
    if (selectedPipeline) {
      await pipelineApi.updatePipeline(selectedPipeline._key, pipelineData);
    } else {
      await pipelineApi.createPipeline(pipelineData);
    }
    setShowEditor(false);
    setSelectedPipeline(null);
    loadData();
  };

  // Handle delete
  const handleDelete = async (key: string) => {
    if (confirm('Are you sure you want to delete this pipeline?')) {
      await pipelineApi.deletePipeline(key);
      loadData();
    }
  };

  // Handle select for editing
  const handleSelect = (pipeline: Pipeline) => {
    setSelectedPipeline(pipeline);
    setShowEditor(true);
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: "'Rajdhani', sans-serif", letterSpacing: 1 }}>Pipeline Builder</h1>
          <p className="text-[#888]" style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
            Create data pipelines and generate API configurations
          </p>
        </div>
        <Button
          onClick={() => { setSelectedPipeline(null); setShowEditor(true); }}
          className="bg-[#6EBE46] text-[#0a0a0a] hover:bg-[#7ECF56] font-bold"
          style={{ fontFamily: "'Rajdhani', sans-serif", letterSpacing: 1 }}
        >
          <Plus className="h-4 w-4 mr-2" />
          New Pipeline
        </Button>
      </div>

      {showEditor ? (
        <PipelineEditor
          pipeline={selectedPipeline}
          collections={collections}
          onSave={handleSave}
          onCancel={() => { setShowEditor(false); setSelectedPipeline(null); }}
        />
      ) : (
        <>
          <PipelineList
            pipelines={pipelines}
            onSelect={handleSelect}
            onDelete={handleDelete}
            onRefresh={loadData}
            loading={loading}
          />

          {/* Quick Actions for existing pipelines */}
          {pipelines.length > 0 && (
            <Card className="border-[#2d2d2d] bg-[#111]">
              <CardHeader>
                <CardTitle className="text-lg" style={{ fontFamily: "'Rajdhani', sans-serif" }}>Quick Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  {pipelines.map((p) => (
                    <CodePreviewDialog
                      key={p._key}
                      pipelineKey={p._key}
                      pipelineName={p.name}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

export default PipelineBuilder;