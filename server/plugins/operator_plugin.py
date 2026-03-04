#!/usr/bin/env python3
"""
Operator TTP Library Plugin
Exposes LibraryModule artifacts to Operator UI
"""

from typing import List, Dict, Any
from .base import Plugin, PluginConfig, FieldMapping


class OperatorPlugin(Plugin):
    """Plugin for Operator TTP workflow builder"""
    
    def __init__(self):
        config = PluginConfig(
            id="operator",
            name="Operator TTP Library",
            description="Expose library modules to Operator workflow builder",
            endpoint="/api/plugins/operator/modules",
            icon="⚙️",
            active=False,  # Starts inactive, user enables it
            collections=["LibraryModule", "CobaltStrikeModule"],
            field_mappings=[
                FieldMapping(source="_key", target="_key"),
                FieldMapping(source="_key", target="id"),
                FieldMapping(source="name", target="name"),
                FieldMapping(source="category", target="category"),
                FieldMapping(source="tactic", target="tactic"),
                FieldMapping(source="icon", target="icon"),
                FieldMapping(source="payload.subcategory", target="subcategory"),
                FieldMapping(source="payload.description", target="description"),
                FieldMapping(source="payload.riskLevel", target="riskLevel"),
                FieldMapping(source="payload.estimatedDuration", target="estimatedDuration"),
                FieldMapping(source="payload.executionType", target="executionType"),
                FieldMapping(source="payload.cobaltStrikeCommand", target="cobaltStrikeCommand"),
                FieldMapping(source="payload.robotKeyword", target="robotKeyword"),
                FieldMapping(source="payload.robotTemplate", target="robotTemplate"),
                FieldMapping(source="payload.shellCommand", target="shellCommand"),
                FieldMapping(source="payload.inputs", target="inputs"),
                FieldMapping(source="payload.outputs", target="outputs"),
                FieldMapping(source="payload.parameters", target="parameters"),
                FieldMapping(source="payload.requirements", target="requirements"),
                FieldMapping(source="payload.metadata", target="metadata"),
            ],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            created_by="system"
        )
        super().__init__(config)
    
    def transform_data(self, nodes: List[dict], payloads: Dict[str, dict]) -> List[dict]:
        """
        Transform ProtoGraph nodes + payloads into Operator's LibraryModule format
        """
        modules = []
        
        for node in nodes:
            node_key = node.get("_key")
            payload = payloads.get(node_key, {})
            
            # Build module with defaults
            module = {
                "_key": node.get("_key"),
                "id": node.get("_key"),
                "name": node.get("name", "Unnamed Module"),
                "category": node.get("category", ""),
                "tactic": node.get("tactic", "TA0002"),
                "icon": node.get("icon", "⚙️"),
                # Defaults for required Operator fields
                "subcategory": "",
                "description": "",
                "riskLevel": "medium",
                "estimatedDuration": 60,
                "executionType": "shell_command",
                "inputs": [],
                "outputs": [],
                "parameters": [],
                "requirements": {
                    "c2Server": False,
                    "listeners": [],
                    "payloads": [],
                    "sshConnections": [],
                    "externalTools": [],
                    "libraries": []
                },
                "metadata": {
                    "version": "1.0",
                    "lastUpdated": node.get("ingested_at", ""),
                    "updatedBy": node.get("created_by", "system"),
                    "validationStatus": "draft",
                    "changeLog": "",
                    "owner": node.get("created_by", ""),
                    "status": "active",
                    "tags": []
                }
            }
            
            # Apply field mappings from payload
            for mapping in self.config.field_mappings:
                if mapping.source.startswith("payload."):
                    # Extract from payload
                    payload_field = mapping.source.replace("payload.", "")
                    if payload_field in payload:
                        module[mapping.target] = payload[payload_field]
                else:
                    # Extract from node
                    if mapping.source in node:
                        module[mapping.target] = node[mapping.source]
            
            modules.append(module)
        
        return modules
    
    def validate_data(self, data: List[dict]) -> bool:
        """Validate modules have required Operator fields"""
        required_fields = ["id", "name", "tactic", "category"]
        
        for module in data:
            for field in required_fields:
                if field not in module or not module[field]:
                    print(f"⚠️  Module missing required field: {field}")
                    return False
        
        return True


# Auto-register on import
from .base import PluginRegistry
from datetime import datetime

operator_plugin = OperatorPlugin()
PluginRegistry.register(operator_plugin)