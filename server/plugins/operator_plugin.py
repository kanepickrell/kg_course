#!/usr/bin/env python3
"""
Operator TTP Library Plugin
Exposes LibraryModule artifacts to the Operator/Lumen UI.

Set active=True because this is a first-party system plugin,
not a user-optional integration. It should always be on.
"""

from datetime import datetime
from typing import List, Dict

from .base import Plugin, PluginConfig, FieldMapping, PluginRegistry


class OperatorPlugin(Plugin):
    """Plugin for the Operator / Lumen TTP workflow builder."""

    def __init__(self):
        config = PluginConfig(
            id="operator",
            name="Operator TTP Library",
            description="Expose library modules to the Operator/Lumen workflow builder",
            endpoint="/api/plugins/operator/modules",
            icon="⚙️",
            active=True,   # Always on — first-party plugin
            collections=["LibraryModule"],
            field_mappings=[
                FieldMapping(source="_key",                        target="_key"),
                FieldMapping(source="_key",                        target="id"),
                FieldMapping(source="name",                        target="name"),
                FieldMapping(source="category",                    target="category"),
                FieldMapping(source="tactic",                      target="tactic"),
                FieldMapping(source="icon",                        target="icon"),
                FieldMapping(source="payload.subcategory",         target="subcategory"),
                FieldMapping(source="payload.description",         target="description"),
                FieldMapping(source="payload.riskLevel",           target="riskLevel"),
                FieldMapping(source="payload.estimatedDuration",   target="estimatedDuration"),
                FieldMapping(source="payload.executionType",       target="executionType"),
                FieldMapping(source="payload.cobaltStrikeCommand", target="cobaltStrikeCommand"),
                FieldMapping(source="payload.robotKeyword",        target="robotKeyword"),
                FieldMapping(source="payload.robotTemplate",       target="robotTemplate"),
                FieldMapping(source="payload.shellCommand",        target="shellCommand"),
                FieldMapping(source="payload.inputs",              target="inputs"),
                FieldMapping(source="payload.outputs",             target="outputs"),
                FieldMapping(source="payload.parameters",          target="parameters"),
                FieldMapping(source="payload.requirements",        target="requirements"),
                FieldMapping(source="payload.metadata",            target="metadata"),
            ],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            created_by="system",
        )
        super().__init__(config)

    def transform_data(self, nodes: List[dict], payloads: Dict[str, dict]) -> List[dict]:
        """
        Transform GraphDB nodes + payload files into Operator's LibraryModule format.
        nodes: list of dicts from gdb.get_library_modules()
        payloads: dict of key -> payload JSON
        """
        modules = []

        for node in nodes:
            key = node.get("_key", "")
            payload = payloads.get(key, {})

            module = {
                "_key": key,
                "id": key,
                "name": node.get("name", "Unnamed Module"),
                "category": node.get("category", ""),
                "tactic": node.get("tactic", ""),
                "icon": node.get("icon", "⚙️"),
                # Operator-required defaults
                "subcategory": "",
                "description": node.get("description", ""),
                "riskLevel": node.get("riskLevel", "medium"),
                "estimatedDuration": "1-5 min",
                "executionType": "shell_command",
                "cobaltStrikeCommand": "",
                "robotKeyword": "",
                "robotTemplate": "",
                "shellCommand": "",
                "inputs": [],
                "outputs": [],
                "parameters": [],
                "requirements": {
                    "c2Server": False,
                    "listeners": [],
                    "payloads": [],
                    "sshConnections": [],
                    "externalTools": [],
                    "libraries": [],
                },
                "metadata": {
                    "version": "1.0",
                    "status": "active",
                    "tags": [],
                },
            }

            # Apply field mappings — payload fields take precedence over graph fields
            for mapping in self.config.field_mappings:
                if mapping.source.startswith("payload."):
                    field = mapping.source[len("payload."):]
                    if field in payload:
                        module[mapping.target] = payload[field]
                else:
                    if mapping.source in node and node[mapping.source] is not None:
                        module[mapping.target] = node[mapping.source]

            modules.append(module)

        return modules

    def validate_data(self, data: List[dict]) -> bool:
        for module in data:
            for field in ("id", "name", "category"):
                if not module.get(field):
                    print(f"⚠️ Operator plugin: module missing '{field}': {module.get('id', '?')}")
                    return False
        return True


# Auto-register on import
operator_plugin = OperatorPlugin()
PluginRegistry.register(operator_plugin)