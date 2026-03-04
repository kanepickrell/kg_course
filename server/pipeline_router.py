"""
Pipeline API Router
===================
FastAPI router for pipeline management and execution.

Endpoints:
- GET  /api/pipelines                     - List all pipelines
- POST /api/pipelines                     - Create a new pipeline
- GET  /api/pipelines/{key}               - Execute pipeline (get data)
- GET  /api/pipelines/{key}/config        - Get pipeline configuration
- PUT  /api/pipelines/{key}               - Update pipeline
- DELETE /api/pipelines/{key}             - Delete pipeline
- GET  /api/pipelines/{key}/detail/{doc}  - Get single document
- GET  /api/pipelines/{key}/categories    - Get categories aggregation
- GET  /api/pipelines/{key}/tactics       - Get tactics aggregation
- GET  /api/pipelines/{key}/stats         - Get statistics
- GET  /api/pipelines/{key}/generate      - Generate api.ts code

Usage:
    from pipeline_router import create_pipeline_router
    from pipeline_engine import PipelineEngine
    
    engine = PipelineEngine(db)
    router = create_pipeline_router(engine)
    app.include_router(router)
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


# =============================================================================
# Request/Response Models
# =============================================================================

class PipelineSource(BaseModel):
    """Source collection configuration"""
    collection: str = Field(..., description="Name of the source collection")
    mergePayload: bool = Field(False, description="Whether to merge payload files")
    payloadDir: Optional[str] = Field("./data/payloads", description="Directory for payload files")
    payloadFields: List[str] = Field(default_factory=list, description="Fields to merge from payload")


class PipelineEndpoint(BaseModel):
    """Endpoint configuration"""
    path: str = Field(..., description="URL path for this endpoint")
    method: str = Field("GET", description="HTTP method")
    description: Optional[str] = Field(None, description="Endpoint description")


class PipelineFilter(BaseModel):
    """Filter configuration"""
    param: str = Field(..., description="Query parameter name")
    field: Any = Field(..., description="Document field(s) to filter on")
    op: str = Field("eq", description="Filter operation: eq, neq, contains, in, gt, lt, gte, lte")


class PipelinePagination(BaseModel):
    """Pagination configuration"""
    enabled: bool = Field(True)
    defaultLimit: int = Field(100)
    maxLimit: int = Field(500)


class PipelineCaching(BaseModel):
    """Caching configuration"""
    enabled: bool = Field(True)
    ttlSeconds: int = Field(300)


class PipelineCodeGen(BaseModel):
    """Code generation configuration"""
    typescript: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CreatePipelineRequest(BaseModel):
    """Request body for creating a pipeline"""
    key: str = Field(..., description="Unique pipeline key (used in URL)", alias="_key")
    name: str = Field(..., description="Human-readable pipeline name")
    description: Optional[str] = Field(None, description="Pipeline description")
    source: PipelineSource
    endpoints: Dict[str, PipelineEndpoint] = Field(default_factory=dict)
    filters: List[PipelineFilter] = Field(default_factory=list)
    pagination: PipelinePagination = Field(default_factory=PipelinePagination)
    caching: PipelineCaching = Field(default_factory=PipelineCaching)
    codeGen: Optional[PipelineCodeGen] = Field(default_factory=PipelineCodeGen)
    
    class Config:
        populate_by_name = True


class UpdatePipelineRequest(BaseModel):
    """Request body for updating a pipeline"""
    name: Optional[str] = None
    description: Optional[str] = None
    source: Optional[PipelineSource] = None
    endpoints: Optional[Dict[str, PipelineEndpoint]] = None
    filters: Optional[List[PipelineFilter]] = None
    pagination: Optional[PipelinePagination] = None
    caching: Optional[PipelineCaching] = None
    codeGen: Optional[PipelineCodeGen] = None
    status: Optional[str] = None


class GenerateConfigRequest(BaseModel):
    """Request body for generating API config"""
    pipelines: List[str] = Field(..., description="Pipeline keys to include")
    envVar: str = Field("VITE_API_URL", description="Environment variable name")
    defaultBaseUrl: str = Field("http://localhost:8000", description="Default API base URL")
    constName: str = Field("API_CONFIG", description="TypeScript const name")


# =============================================================================
# Router Factory
# =============================================================================

def create_pipeline_router(pipeline_engine) -> APIRouter:
    """
    Create FastAPI router for pipeline operations.
    
    Args:
        pipeline_engine: Instance of PipelineEngine
        
    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])
    
    # Import the generator
    from pipeline_engine import ApiConfigGenerator
    generator = ApiConfigGenerator(pipeline_engine)
    
    # =========================================================================
    # Pipeline Management Endpoints
    # =========================================================================
    
    @router.get("")
    async def list_pipelines():
        """List all available pipelines."""
        try:
            pipelines = pipeline_engine.list_pipelines()
            return {
                "success": True,
                "count": len(pipelines),
                "pipelines": pipelines
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("")
    async def create_pipeline(request: CreatePipelineRequest):
        """Create a new pipeline configuration."""
        try:
            config = request.model_dump(by_alias=True)
            # Rename 'key' to '_key' for ArangoDB
            if 'key' in config:
                config['_key'] = config.pop('key')
            
            result = pipeline_engine.create_pipeline(config)
            return {
                "success": True,
                "message": f"Pipeline '{request.key}' created",
                "pipeline": result
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/{pipeline_key}/config")
    async def get_pipeline_config(pipeline_key: str):
        """Get pipeline configuration (not data)."""
        try:
            config = pipeline_engine.get_pipeline_config(pipeline_key)
            return {
                "success": True,
                "config": config
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.put("/{pipeline_key}")
    async def update_pipeline(pipeline_key: str, request: UpdatePipelineRequest):
        """Update a pipeline configuration."""
        try:
            updates = {k: v for k, v in request.model_dump().items() if v is not None}
            result = pipeline_engine.update_pipeline(pipeline_key, updates)
            return {
                "success": True,
                "message": f"Pipeline '{pipeline_key}' updated",
                "pipeline": result
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.delete("/{pipeline_key}")
    async def delete_pipeline(pipeline_key: str):
        """Delete a pipeline configuration."""
        try:
            pipeline_engine.delete_pipeline(pipeline_key)
            return {
                "success": True,
                "message": f"Pipeline '{pipeline_key}' deleted"
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # =========================================================================
    # Pipeline Execution Endpoints
    # =========================================================================
    
    @router.get("/{pipeline_key}")
    async def execute_pipeline(
        pipeline_key: str,
        request: Request,
        limit: Optional[int] = Query(None, le=500),
        offset: int = Query(0, ge=0)
    ):
        """
        Execute a pipeline and return data.
        
        Supports dynamic query parameters based on pipeline filter configuration.
        """
        try:
            # Extract all query params (for filters)
            filters = dict(request.query_params)
            filters.pop("limit", None)
            filters.pop("offset", None)
            
            result = pipeline_engine.execute(
                pipeline_key=pipeline_key,
                filters=filters,
                limit=limit,
                offset=offset
            )
            
            return result
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            print(f"Pipeline execution error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/{pipeline_key}/detail/{document_key}")
    async def get_document(pipeline_key: str, document_key: str):
        """Get a single document by key."""
        try:
            result = pipeline_engine.execute_detail(pipeline_key, document_key)
            
            if not result.get("success") or result.get("data") is None:
                raise HTTPException(status_code=404, detail="Document not found")
            
            return result
            
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/{pipeline_key}/categories")
    async def get_categories(pipeline_key: str):
        """Get category aggregation."""
        try:
            result = pipeline_engine.execute_aggregation(pipeline_key, "category")
            return {
                "success": True,
                "categories": result["data"]
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/{pipeline_key}/tactics")
    async def get_tactics(pipeline_key: str):
        """Get tactic aggregation."""
        try:
            result = pipeline_engine.execute_aggregation(pipeline_key, "tactic")
            return {
                "success": True,
                "tactics": result["data"]
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/{pipeline_key}/stats")
    async def get_stats(pipeline_key: str):
        """Get pipeline statistics."""
        try:
            result = pipeline_engine.execute_stats(pipeline_key)
            return result
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # =========================================================================
    # Code Generation Endpoints
    # =========================================================================
    
    @router.get("/{pipeline_key}/generate")
    async def generate_api_config_single(
        pipeline_key: str,
        env_var: str = Query("VITE_API_URL"),
        default_base_url: str = Query("http://localhost:8000"),
        const_name: str = Query("API_CONFIG")
    ):
        """Generate api.ts for a single pipeline."""
        try:
            code = generator.generate(
                pipeline_keys=[pipeline_key],
                options={
                    "envVar": env_var,
                    "defaultBaseUrl": default_base_url,
                    "constName": const_name
                }
            )
            
            return PlainTextResponse(
                content=code,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=api.ts"
                }
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/generate")
    async def generate_api_config_multi(request: GenerateConfigRequest):
        """Generate api.ts for multiple pipelines."""
        try:
            code = generator.generate(
                pipeline_keys=request.pipelines,
                options={
                    "envVar": request.envVar,
                    "defaultBaseUrl": request.defaultBaseUrl,
                    "constName": request.constName
                }
            )
            
            return PlainTextResponse(
                content=code,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=api.ts"
                }
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return router