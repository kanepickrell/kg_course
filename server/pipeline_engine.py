"""
Pipeline Engine
===============
Core engine for executing data pipelines defined in the DataPipeline collection.

This module:
1. Reads pipeline configurations from ArangoDB
2. Executes queries against source collections
3. Merges payload files when configured
4. Applies filters from query parameters
5. Returns processed data
6. Generates API configs that point to PLUGIN endpoints (when pluginId is set)

Usage:
    from pipeline_engine import PipelineEngine
    
    engine = PipelineEngine(db)
    result = engine.execute("library-modules-operator", filters={"category": "Cobalt Strike"})
"""

import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime


class PipelineEngine:
    """
    Executes data pipelines against ArangoDB collections.
    """
    
    def __init__(self, db, payload_base_dir: str = "./data/payloads"):
        """
        Initialize the pipeline engine.
        
        Args:
            db: ArangoDB database connection
            payload_base_dir: Base directory for payload files
        """
        self.db = db
        self.payload_base_dir = payload_base_dir
        self._config_cache: Dict[str, Dict] = {}
    
    # =========================================================================
    # Configuration Management
    # =========================================================================
    
    def get_pipeline_config(self, pipeline_key: str) -> Dict:
        """
        Load pipeline configuration from DataPipeline collection.
        
        Args:
            pipeline_key: The _key of the pipeline document
            
        Returns:
            Pipeline configuration dict
            
        Raises:
            ValueError: If pipeline not found
        """
        # Check cache first
        if pipeline_key in self._config_cache:
            return self._config_cache[pipeline_key]
        
        # Load from database
        if not self.db.has_collection("DataPipeline"):
            raise ValueError("DataPipeline collection does not exist")
        
        collection = self.db.collection("DataPipeline")
        
        if not collection.has(pipeline_key):
            raise ValueError(f"Pipeline '{pipeline_key}' not found")
        
        config = collection.get(pipeline_key)
        
        # Cache it
        self._config_cache[pipeline_key] = config
        
        return config
    
    def list_pipelines(self) -> List[Dict]:
        """
        List all available pipelines.
        
        Returns:
            List of pipeline summaries
        """
        if not self.db.has_collection("DataPipeline"):
            return []
        
        collection = self.db.collection("DataPipeline")
        
        pipelines = []
        for doc in collection.all():
            pipelines.append({
                "key": doc["_key"],
                "name": doc.get("name", doc["_key"]),
                "description": doc.get("description", ""),
                "source": doc.get("source", {}).get("collection", "Unknown"),
                "status": doc.get("status", "active"),
                "pluginId": doc.get("pluginId", None),  # Include pluginId
                "endpoints": list(doc.get("endpoints", {}).keys())
            })
        
        return pipelines
    
    def create_pipeline(self, config: Dict) -> Dict:
        """
        Create a new pipeline configuration.
        
        Args:
            config: Pipeline configuration dict (must include _key)
            
        Returns:
            Created pipeline document
        """
        if not self.db.has_collection("DataPipeline"):
            self.db.create_collection("DataPipeline")
        
        collection = self.db.collection("DataPipeline")
        
        # Add metadata
        config["metadata"] = config.get("metadata", {})
        config["metadata"]["createdAt"] = datetime.utcnow().isoformat() + "Z"
        config["metadata"]["updatedAt"] = config["metadata"]["createdAt"]
        
        # Set defaults
        config.setdefault("status", "active")
        config.setdefault("version", 1)
        
        result = collection.insert(config)
        
        # Clear cache
        self._config_cache.pop(config["_key"], None)
        
        return {**config, "_id": result["_id"], "_rev": result["_rev"]}
    
    def update_pipeline(self, pipeline_key: str, updates: Dict) -> Dict:
        """
        Update an existing pipeline configuration.
        
        Args:
            pipeline_key: The _key of the pipeline to update
            updates: Fields to update
            
        Returns:
            Updated pipeline document
        """
        collection = self.db.collection("DataPipeline")
        
        if not collection.has(pipeline_key):
            raise ValueError(f"Pipeline '{pipeline_key}' not found")
        
        # Get current doc
        current = collection.get(pipeline_key)
        
        # Merge updates
        for key, value in updates.items():
            if key not in ["_key", "_id", "_rev"]:
                current[key] = value
        
        # Update metadata
        current["metadata"] = current.get("metadata", {})
        current["metadata"]["updatedAt"] = datetime.utcnow().isoformat() + "Z"
        current["version"] = current.get("version", 0) + 1
        
        result = collection.update(current)
        
        # Clear cache
        self._config_cache.pop(pipeline_key, None)
        
        return {**current, "_rev": result["_rev"]}
    
    def delete_pipeline(self, pipeline_key: str) -> bool:
        """
        Delete a pipeline configuration.
        
        Args:
            pipeline_key: The _key of the pipeline to delete
            
        Returns:
            True if deleted
        """
        collection = self.db.collection("DataPipeline")
        
        if not collection.has(pipeline_key):
            raise ValueError(f"Pipeline '{pipeline_key}' not found")
        
        collection.delete(pipeline_key)
        
        # Clear cache
        self._config_cache.pop(pipeline_key, None)
        
        return True
    
    # =========================================================================
    # Pipeline Execution
    # =========================================================================
    
    def execute(
        self,
        pipeline_key: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Execute a pipeline and return data.
        
        Args:
            pipeline_key: The _key of the pipeline to execute
            filters: Query parameter filters
            limit: Max results to return
            offset: Pagination offset
            
        Returns:
            {
                "success": True,
                "data": [...],
                "count": 42,
                "total": 100,
                "pipeline": "pipeline-name",
                "pagination": {"limit": 100, "offset": 0}
            }
        """
        config = self.get_pipeline_config(pipeline_key)
        filters = filters or {}
        
        source = config.get("source", {})
        collection_name = source.get("collection")
        
        if not collection_name:
            raise ValueError(f"Pipeline '{pipeline_key}' has no source collection")
        
        if not self.db.has_collection(collection_name):
            raise ValueError(f"Source collection '{collection_name}' does not exist")
        
        # Build and execute query
        pagination = config.get("pagination", {})
        actual_limit = min(
            limit or pagination.get("defaultLimit", 100),
            pagination.get("maxLimit", 500)
        )
        
        # Build filter conditions
        filter_conditions = self._build_filters(config, filters)
        
        # Get total count
        count_query = f"""
            FOR doc IN {collection_name}
                FILTER {filter_conditions}
                COLLECT WITH COUNT INTO total
                RETURN total
        """
        total = list(self.db.aql.execute(count_query))[0]
        
        # Get data
        data_query = f"""
            FOR doc IN {collection_name}
                FILTER {filter_conditions}
                SORT doc.name ASC
                LIMIT @offset, @limit
                RETURN doc
        """
        
        cursor = self.db.aql.execute(
            data_query,
            bind_vars={"offset": offset, "limit": actual_limit}
        )
        documents = list(cursor)
        
        # Merge payloads if configured
        if source.get("mergePayload", False):
            documents = [self._merge_payload(doc, source) for doc in documents]
        
        return {
            "success": True,
            "data": documents,
            "count": len(documents),
            "total": total,
            "pipeline": config.get("name", pipeline_key),
            "pagination": {
                "limit": actual_limit,
                "offset": offset,
                "hasMore": offset + len(documents) < total
            }
        }
    
    def execute_detail(self, pipeline_key: str, document_key: str) -> Dict[str, Any]:
        """
        Get a single document by key.
        
        Args:
            pipeline_key: The pipeline to use
            document_key: The _key of the document to fetch
            
        Returns:
            {"success": True, "data": {...}}
        """
        config = self.get_pipeline_config(pipeline_key)
        source = config.get("source", {})
        collection_name = source.get("collection")
        
        if not self.db.has_collection(collection_name):
            raise ValueError(f"Collection '{collection_name}' not found")
        
        collection = self.db.collection(collection_name)
        
        if not collection.has(document_key):
            return {"success": False, "error": "Not found", "data": None}
        
        doc = collection.get(document_key)
        
        # Merge payload if configured
        if source.get("mergePayload", False):
            doc = self._merge_payload(doc, source)
        
        return {"success": True, "data": doc}
    
    def execute_aggregation(
        self,
        pipeline_key: str,
        group_by: str
    ) -> Dict[str, Any]:
        """
        Execute an aggregation (e.g., categories, tactics with counts).
        
        Args:
            pipeline_key: The pipeline to use
            group_by: Field to group by
            
        Returns:
            {"success": True, "data": [{"value": "X", "count": 10}, ...]}
        """
        config = self.get_pipeline_config(pipeline_key)
        source = config.get("source", {})
        collection_name = source.get("collection")
        
        query = f"""
            FOR doc IN {collection_name}
                FILTER doc.{group_by} != null
                COLLECT value = doc.{group_by} WITH COUNT INTO count
                SORT value ASC
                RETURN {{value: value, count: count}}
        """
        
        results = list(self.db.aql.execute(query))
        
        return {"success": True, "data": results, "groupBy": group_by}
    
    def execute_stats(self, pipeline_key: str) -> Dict[str, Any]:
        """
        Get statistics for a pipeline's source collection.
        
        Args:
            pipeline_key: The pipeline to use
            
        Returns:
            Statistics dict
        """
        config = self.get_pipeline_config(pipeline_key)
        source = config.get("source", {})
        collection_name = source.get("collection")
        
        collection = self.db.collection(collection_name)
        total = collection.count()
        
        # Get counts by common fields
        stats = {"total": total}
        
        # By category
        cat_query = f"""
            FOR doc IN {collection_name}
                FILTER doc.category != null
                COLLECT category = doc.category WITH COUNT INTO count
                RETURN {{category: category, count: count}}
        """
        stats["byCategory"] = list(self.db.aql.execute(cat_query))
        
        # By tactic
        tactic_query = f"""
            FOR doc IN {collection_name}
                FILTER doc.tactic != null
                COLLECT tactic = doc.tactic WITH COUNT INTO count
                RETURN {{tactic: tactic, count: count}}
        """
        stats["byTactic"] = list(self.db.aql.execute(tactic_query))
        
        # By risk level
        risk_query = f"""
            FOR doc IN {collection_name}
                FILTER doc.riskLevel != null
                COLLECT riskLevel = doc.riskLevel WITH COUNT INTO count
                RETURN {{riskLevel: riskLevel, count: count}}
        """
        stats["byRiskLevel"] = list(self.db.aql.execute(risk_query))
        
        # By execution type
        exec_query = f"""
            FOR doc IN {collection_name}
                FILTER doc.executionType != null
                COLLECT executionType = doc.executionType WITH COUNT INTO count
                RETURN {{executionType: executionType, count: count}}
        """
        stats["byExecutionType"] = list(self.db.aql.execute(exec_query))
        
        return {"success": True, "stats": stats}
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _build_filters(self, config: Dict, params: Dict[str, Any]) -> str:
        """
        Build AQL filter conditions from query parameters.
        
        Args:
            config: Pipeline configuration
            params: Query parameters from request
            
        Returns:
            AQL filter string
        """
        conditions = ["true"]  # Start with always-true
        
        filter_defs = config.get("filters", [])
        
        for filter_def in filter_defs:
            param_name = filter_def.get("param")
            field = filter_def.get("field")
            op = filter_def.get("op", "eq")
            
            if param_name not in params or not params[param_name]:
                continue
            
            value = params[param_name]
            
            # Handle multiple fields (OR condition)
            if isinstance(field, list):
                field_conditions = []
                for f in field:
                    field_conditions.append(self._single_filter(f, op, value))
                conditions.append(f"({' OR '.join(field_conditions)})")
            else:
                conditions.append(self._single_filter(field, op, value))
        
        return " AND ".join(conditions)
    
    def _single_filter(self, field: str, op: str, value: Any) -> str:
        """Generate a single AQL filter condition."""
        # Escape single quotes in value
        if isinstance(value, str):
            escaped_value = value.replace("'", "\\'")
        else:
            escaped_value = value
        
        if op == "eq":
            return f"doc.{field} == '{escaped_value}'"
        elif op == "neq":
            return f"doc.{field} != '{escaped_value}'"
        elif op == "contains":
            return f"CONTAINS(LOWER(doc.{field} || ''), LOWER('{escaped_value}'))"
        elif op == "in":
            return f"doc.{field} IN {json.dumps(value)}"
        elif op == "gt":
            return f"doc.{field} > {value}"
        elif op == "lt":
            return f"doc.{field} < {value}"
        elif op == "gte":
            return f"doc.{field} >= {value}"
        elif op == "lte":
            return f"doc.{field} <= {value}"
        else:
            return "true"
    
    def _merge_payload(self, doc: Dict, source_config: Dict) -> Dict:
        """
        Merge payload file data into document.
        
        Args:
            doc: The document from ArangoDB
            source_config: Source configuration with payload settings
            
        Returns:
            Document with payload fields merged
        """
        key = doc.get("_key", "")
        payload_dir = source_config.get("payloadDir", self.payload_base_dir)
        payload_fields = source_config.get("payloadFields", [])
        
        # Build payload path
        payload_path = os.path.join(payload_dir, f"{key}.json")
        
        if not os.path.exists(payload_path):
            # No payload file - return doc with empty defaults for expected fields
            for field in payload_fields:
                if field not in doc:
                    doc[field] = [] if field in ["inputs", "outputs", "parameters"] else None
            return doc
        
        try:
            with open(payload_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            
            # Merge specified fields from payload
            for field in payload_fields:
                # Check both lowercase and capitalized versions
                if field in payload:
                    doc[field] = payload[field]
                elif field.capitalize() in payload:
                    doc[field] = payload[field.capitalize()]
                elif field[0].upper() + field[1:] in payload:
                    doc[field] = payload[field[0].upper() + field[1:]]
            
            return doc
            
        except Exception as e:
            print(f"Warning: Failed to load payload for {key}: {e}")
            return doc
    
    def clear_cache(self):
        """Clear the configuration cache."""
        self._config_cache.clear()


# =============================================================================
# Code Generator - UPDATED TO USE PLUGIN ENDPOINTS
# =============================================================================

class ApiConfigGenerator:
    """
    Generates api.ts configuration file from pipeline definitions.
    
    When a pipeline has a pluginId associated, the generated endpoints
    point to the PLUGIN system (/api/plugins/{id}/...) instead of the
    pipeline system. This ensures the plugin's enable/disable toggle
    controls access to the data.
    """
    
    def __init__(self, pipeline_engine: PipelineEngine):
        self.engine = pipeline_engine
    
    def generate(self, pipeline_keys: List[str], options: Dict = None) -> str:
        """
        Generate api.ts content for the specified pipelines.
        
        Args:
            pipeline_keys: List of pipeline keys to include
            options: Generation options (envVar, defaultBaseUrl, etc.)
            
        Returns:
            TypeScript code as string
        """
        options = options or {}
        env_var = options.get("envVar", "VITE_API_URL")
        default_base_url = options.get("defaultBaseUrl", "http://localhost:8000")
        const_name = options.get("constName", "API_CONFIG")
        
        # Collect all endpoints from all pipelines
        endpoints = {}
        
        for pipeline_key in pipeline_keys:
            try:
                config = self.engine.get_pipeline_config(pipeline_key)
                
                # Check if pipeline is associated with a plugin
                plugin_id = config.get("pluginId")
                
                if plugin_id:
                    # Generate PLUGIN endpoints (respects enable/disable)
                    pipeline_endpoints = self._generate_plugin_endpoints(plugin_id, config)
                else:
                    # Generate PIPELINE endpoints (no enable/disable control)
                    pipeline_endpoints = self._generate_pipeline_endpoints(pipeline_key, config)
                
                endpoints.update(pipeline_endpoints)
                        
            except Exception as e:
                print(f"Warning: Could not load pipeline '{pipeline_key}': {e}")
                continue
        
        # Generate TypeScript
        lines = [
            "// Generated by ProtoGraph Pipeline Engine",
            f"// Generated: {datetime.utcnow().isoformat()}Z",
            "// DO NOT EDIT - Regenerate from ProtoGraph UI",
            "",
            f"const API_BASE_URL = import.meta.env.{env_var} || '{default_base_url}';",
            "",
            f"export const {const_name} = {{",
            "  BASE_URL: API_BASE_URL,",
            "  ENDPOINTS: {"
        ]
        
        # Add endpoints
        endpoint_lines = []
        for name, config in endpoints.items():
            if config.get("hasParam"):
                # Function endpoint
                path = config["path"]
                endpoint_lines.append(f"    {name}: (key: string) => `{path}`,")
            else:
                # Static endpoint
                endpoint_lines.append(f"    {name}: '{config['path']}',")
        
        lines.extend(endpoint_lines)
        
        lines.extend([
            "  }",
            "};",
            "",
            "// Type declaration for Vite env variables",
            "declare global {",
            "  interface ImportMetaEnv {",
            f"    {env_var}?: string;",
            "  }",
            "}"
        ])
        
        return "\n".join(lines)
    
    def _generate_plugin_endpoints(self, plugin_id: str, config: Dict) -> Dict[str, Dict]:
        """
        Generate endpoints that point to the PLUGIN system.
        
        These endpoints respect the plugin's active/inactive status.
        When plugin is disabled, these endpoints return error/empty.
        
        Args:
            plugin_id: The plugin identifier (e.g., "operator")
            config: Pipeline configuration
            
        Returns:
            Dict of endpoint configurations
        """
        # Create a clean prefix from plugin_id
        # e.g., "operator" -> "OPERATOR"
        prefix = plugin_id.upper().replace("-", "_")
        
        base_path = f"/api/plugins/{plugin_id}"
        
        endpoints = {
            # Main data endpoint - matches plugin's configured endpoint
            f"{prefix}_MODULES": {
                "path": f"{base_path}/modules",
                "hasParam": False
            },
            
            # Detail endpoint (get single item by key)
            f"{prefix}_MODULE_DETAIL": {
                "path": f"{base_path}/modules/${{key}}",
                "hasParam": True
            },
            
            # Aggregation endpoints
            f"{prefix}_CATEGORIES": {
                "path": f"{base_path}/categories",
                "hasParam": False
            },
            f"{prefix}_TACTICS": {
                "path": f"{base_path}/tactics",
                "hasParam": False
            },
            f"{prefix}_STATS": {
                "path": f"{base_path}/stats",
                "hasParam": False
            },
            
            # Validation endpoint
            f"{prefix}_VALIDATE": {
                "path": f"{base_path}/validate",
                "hasParam": False
            },
        }
        
        return endpoints
    
    def _generate_pipeline_endpoints(self, pipeline_key: str, config: Dict) -> Dict[str, Dict]:
        """
        Generate endpoints that point directly to pipeline system.
        
        Fallback when no plugin is associated. These do NOT respect 
        any enable/disable toggle.
        
        Args:
            pipeline_key: The pipeline key
            config: Pipeline configuration
            
        Returns:
            Dict of endpoint configurations
        """
        # Create a clean prefix from pipeline key
        # e.g., "library-modules-operator" -> "LIBRARY_MODULES"
        prefix = pipeline_key.replace("-operator", "").replace("-", "_").upper()
        
        base_path = f"/api/pipelines/{pipeline_key}"
        
        endpoints = {
            prefix: {
                "path": base_path,
                "hasParam": False
            },
            f"{prefix}_DETAIL": {
                "path": f"{base_path}/detail/${{key}}",
                "hasParam": True
            },
            f"{prefix}_CATEGORIES": {
                "path": f"{base_path}/categories",
                "hasParam": False
            },
            f"{prefix}_TACTICS": {
                "path": f"{base_path}/tactics",
                "hasParam": False
            },
            f"{prefix}_STATS": {
                "path": f"{base_path}/stats",
                "hasParam": False
            },
            f"{prefix}_VALIDATE": {
                "path": f"{base_path}/validate",
                "hasParam": False
            },
        }
        
        return endpoints