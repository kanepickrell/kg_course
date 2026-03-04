// lib/graph/schemaFilter.ts
// Utilities for filtering schema vs data nodes in ProtoGraph

/**
 * Collections that contain schema/ontology definitions (not user data)
 * These are the meta-layer that defines how data should be structured
 */
export const SCHEMA_COLLECTIONS = [
  // Ontology concepts
  'ontology_concepts',
  'concepts',
  
  // Taxonomy definitions
  'ontology_taxonomies', 
  'taxonomy_terms',
  'taxonomies',
  
  // Relationship type definitions
  'ontology_relationships',
  'relationship_types',
  
  // Any other meta collections
  'ontology_properties',
  'schema_definitions',
] as const;

/**
 * URI prefixes that indicate schema nodes
 */
export const SCHEMA_URI_PREFIXES = [
  'proto:concept/',
  'proto:taxonomy/',
  'proto:relationship/',
  'proto:property/',
] as const;

/**
 * Node category for filtering
 */
export type NodeCategory = 'data' | 'schema' | 'agent';

/**
 * Determine if a node is a schema node based on its properties
 */
export function isSchemaNode(node: {
  id: string;
  type?: string;
  collection?: string;
  uri?: string;
  _id?: string;
}): boolean {
  // Check collection name
  const collection = node.collection || node.type || (node._id?.split('/')[0]);
  if (collection && SCHEMA_COLLECTIONS.some(sc => 
    collection.toLowerCase().includes(sc.toLowerCase())
  )) {
    return true;
  }
  
  // Check URI prefix
  if (node.uri && SCHEMA_URI_PREFIXES.some(prefix => 
    node.uri!.startsWith(prefix)
  )) {
    return true;
  }
  
  // Check ID patterns (e.g., "proto:concept/LibraryModule")
  if (node.id && SCHEMA_URI_PREFIXES.some(prefix => 
    node.id.startsWith(prefix)
  )) {
    return true;
  }
  
  return false;
}

/**
 * Categorize a node
 */
export function categorizeNode(node: {
  id: string;
  type?: string;
  collection?: string;
  uri?: string;
  _id?: string;
  nodeCategory?: NodeCategory;
}): NodeCategory {
  // If already categorized, use that
  if (node.nodeCategory) {
    return node.nodeCategory;
  }
  
  // Check for agent nodes (future neural routing layer)
  if (node.type === 'ClusterAgent' || node.type === 'HubAgent') {
    return 'agent';
  }
  
  // Check if schema
  if (isSchemaNode(node)) {
    return 'schema';
  }
  
  return 'data';
}

/**
 * Filter mode options
 */
export type FilterMode = 'data' | 'data_schema' | 'all';

/**
 * Filter nodes based on mode
 */
export function filterNodesByMode<T extends {
  id: string;
  type?: string;
  collection?: string;
  uri?: string;
  _id?: string;
  nodeCategory?: NodeCategory;
}>(nodes: T[], mode: FilterMode): T[] {
  switch (mode) {
    case 'data':
      return nodes.filter(n => categorizeNode(n) === 'data');
    case 'data_schema':
      return nodes.filter(n => {
        const cat = categorizeNode(n);
        return cat === 'data' || cat === 'schema';
      });
    case 'all':
      return nodes;
    default:
      return nodes.filter(n => categorizeNode(n) === 'data');
  }
}

/**
 * Filter edges to only include those connecting visible nodes
 */
export function filterEdgesForVisibleNodes<
  N extends { id: string },
  E extends { source: string | { id: string }; target: string | { id: string } }
>(edges: E[], visibleNodes: N[]): E[] {
  const visibleIds = new Set(visibleNodes.map(n => n.id));
  
  return edges.filter(edge => {
    const sourceId = typeof edge.source === 'string' ? edge.source : edge.source.id;
    const targetId = typeof edge.target === 'string' ? edge.target : edge.target.id;
    return visibleIds.has(sourceId) && visibleIds.has(targetId);
  });
}

/**
 * Get summary of node categories in graph
 */
export function getNodeCategorySummary(nodes: Array<{
  id: string;
  type?: string;
  collection?: string;
  uri?: string;
  _id?: string;
  nodeCategory?: NodeCategory;
}>): { data: number; schema: number; agent: number; total: number } {
  const summary = { data: 0, schema: 0, agent: 0, total: nodes.length };
  
  for (const node of nodes) {
    const category = categorizeNode(node);
    summary[category]++;
  }
  
  return summary;
}