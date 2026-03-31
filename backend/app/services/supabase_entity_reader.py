"""
Supabase Entity Reader — replaces ZepEntityReader.
Reads knowledge graph nodes from Supabase and exposes the same
EntityNode / FilteredEntities interface the rest of the app expects.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .supabase_memory import get_memory

logger = logging.getLogger("mirofish.supabase_entity_reader")


# ─── Data classes (same interface as former zep_entity_reader.py) ─────────────

@dataclass
class EntityNode:
    """Entity node data structure — mirrors former Zep EntityNode."""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """Return dominant custom label (not 'Entity' / 'Node')."""
        for label in self.labels:
            if label not in ("Entity", "Node"):
                return label
        return None


@dataclass
class FilteredEntities:
    """Filtered entity collection."""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


# ─── Reader ───────────────────────────────────────────────────────────────────

class SupabaseEntityReader:
    """
    Reads entities from Supabase kg_nodes / kg_edges.
    Drop-in replacement for ZepEntityReader — same public methods.
    """

    def __init__(self):
        self.memory = get_memory()

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return raw node dicts for a graph."""
        return self.memory.get_all_nodes(graph_id)

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return raw edge dicts for a graph."""
        return self.memory.get_all_edges(graph_id)

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        """
        Filter nodes to those matching defined entity types.
        Logic mirrors former ZepEntityReader.filter_defined_entities().
        """
        logger.info("Filtering entities for graph %s …", graph_id)

        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        node_map = {n["uuid"]: n for n in all_nodes}

        filtered: List[EntityNode] = []
        entity_types_found: Set[str] = set()

        for node in all_nodes:
            labels = node.get("labels") or []
            custom_labels = [l for l in labels if l not in ("Entity", "Node")]

            if not custom_labels:
                continue  # generic node, skip

            if defined_entity_types:
                matching = [l for l in custom_labels if l in defined_entity_types]
                if not matching:
                    continue
                entity_type = matching[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node.get("name", ""),
                labels=labels,
                summary=node.get("summary", ""),
                attributes=node.get("attributes") or {},
            )

            if enrich_with_edges:
                related_edges = []
                related_node_uuids: Set[str] = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "outgoing",
                                "edge_name": edge.get("name", ""),
                                "fact": edge.get("fact", ""),
                                "target_node_uuid": edge["target_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "incoming",
                                "edge_name": edge.get("name", ""),
                                "fact": edge.get("fact", ""),
                                "source_node_uuid": edge["source_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges
                entity.related_nodes = [
                    {
                        "uuid": node_map[ru]["uuid"],
                        "name": node_map[ru].get("name", ""),
                        "labels": node_map[ru].get("labels") or [],
                        "summary": node_map[ru].get("summary", ""),
                    }
                    for ru in related_node_uuids
                    if ru in node_map
                ]

            filtered.append(entity)

        logger.info(
            "Entity filter complete: total=%d matched=%d types=%s",
            total_count,
            len(filtered),
            entity_types_found,
        )

        return FilteredEntities(
            entities=filtered,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered),
        )

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        """Get all entities of a specific type."""
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
