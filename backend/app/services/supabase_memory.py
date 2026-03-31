"""
Supabase Memory Layer — replaces Zep Cloud.
Provides node/edge storage for knowledge graphs and agent memory retrieval
using PostgreSQL + pgvector via Supabase.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from ..utils.supabase_client import get_client
from ..utils.gemini_service import GeminiService

logger = logging.getLogger("mirofish.supabase_memory")


class SupabaseMemory:
    """
    Memory layer backed by Supabase (PostgreSQL + pgvector).
    Replaces all Zep-based graph and memory operations.
    """

    # ─── Knowledge Graph: Nodes ───────────────────────────────────────────────

    def store_node(self, graph_id: str, node_data: Dict[str, Any]) -> str:
        """Upsert a knowledge graph node. Returns node_uuid."""
        node_uuid = node_data.get("node_uuid") or node_data.get("uuid") or str(uuid.uuid4())
        name = node_data.get("name", "")
        summary = node_data.get("summary", "")

        # Generate embedding for semantic search
        embed_text = f"{name} {summary}".strip()
        embedding = GeminiService.get_instance().embed(embed_text) if embed_text else None

        client = get_client()
        payload = {
            "graph_id": graph_id,
            "node_uuid": node_uuid,
            "name": name,
            "labels": node_data.get("labels", []),
            "summary": summary,
            "attributes": node_data.get("attributes", {}),
        }
        if embedding:
            payload["embedding"] = embedding

        try:
            client.table("kg_nodes").upsert(payload, on_conflict="node_uuid").execute()
        except Exception as e:
            logger.warning("store_node failed: %s", str(e)[:120])

        return node_uuid

    def store_edge(self, graph_id: str, edge_data: Dict[str, Any]) -> str:
        """Upsert a knowledge graph edge. Returns edge_uuid."""
        edge_uuid = edge_data.get("edge_uuid") or edge_data.get("uuid") or str(uuid.uuid4())
        client = get_client()
        payload = {
            "graph_id": graph_id,
            "edge_uuid": edge_uuid,
            "name": edge_data.get("name", ""),
            "fact": edge_data.get("fact", ""),
            "source_node_uuid": edge_data.get("source_node_uuid") or edge_data.get("source_uuid"),
            "target_node_uuid": edge_data.get("target_node_uuid") or edge_data.get("target_uuid"),
            "attributes": edge_data.get("attributes", {}),
        }
        try:
            client.table("kg_edges").upsert(payload, on_conflict="edge_uuid").execute()
        except Exception as e:
            logger.warning("store_edge failed: %s", str(e)[:120])
        return edge_uuid

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return all nodes for a graph."""
        try:
            client = get_client()
            result = (
                client.table("kg_nodes")
                .select("node_uuid,name,labels,summary,attributes,created_at")
                .eq("graph_id", graph_id)
                .execute()
            )
            rows = result.data or []
            # Normalize to expected shape
            return [
                {
                    "uuid": r["node_uuid"],
                    "name": r.get("name", ""),
                    "labels": r.get("labels") or [],
                    "summary": r.get("summary", ""),
                    "attributes": r.get("attributes") or {},
                    "created_at": r.get("created_at"),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("get_all_nodes failed: %s", str(e)[:120])
            return []

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return all edges for a graph."""
        try:
            client = get_client()
            result = (
                client.table("kg_edges")
                .select(
                    "edge_uuid,name,fact,source_node_uuid,target_node_uuid,attributes,created_at"
                )
                .eq("graph_id", graph_id)
                .execute()
            )
            rows = result.data or []
            return [
                {
                    "uuid": r["edge_uuid"],
                    "name": r.get("name", ""),
                    "fact": r.get("fact", ""),
                    "source_node_uuid": r.get("source_node_uuid", ""),
                    "target_node_uuid": r.get("target_node_uuid", ""),
                    "attributes": r.get("attributes") or {},
                    "created_at": r.get("created_at"),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("get_all_edges failed: %s", str(e)[:120])
            return []

    def search_nodes(
        self, graph_id: str, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Semantic similarity search over kg_nodes using pgvector."""
        try:
            embedding = GeminiService.get_instance().embed(query, task_type="retrieval_query")
            client = get_client()
            # Use Supabase RPC for pgvector similarity
            result = client.rpc(
                "search_kg_nodes",
                {
                    "p_graph_id": graph_id,
                    "p_embedding": embedding,
                    "p_top_k": top_k,
                },
            ).execute()
            rows = result.data or []
            return [
                {
                    "uuid": r.get("node_uuid", ""),
                    "name": r.get("name", ""),
                    "labels": r.get("labels") or [],
                    "summary": r.get("summary", ""),
                    "attributes": r.get("attributes") or {},
                    "similarity": r.get("similarity", 0.0),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(
                "search_nodes pgvector RPC not available, falling back to text search: %s",
                str(e)[:120],
            )
            # Fallback: return all nodes filtered by name/summary contains query
            all_nodes = self.get_all_nodes(graph_id)
            q_lower = query.lower()
            scored = [
                n
                for n in all_nodes
                if q_lower in (n.get("name") or "").lower()
                or q_lower in (n.get("summary") or "").lower()
            ]
            return scored[:top_k]

    def search_edges(
        self, graph_id: str, query: str, top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Text search over kg_edges facts."""
        try:
            all_edges = self.get_all_edges(graph_id)
            q_lower = query.lower()
            scored = [
                e
                for e in all_edges
                if q_lower in (e.get("fact") or "").lower()
                or q_lower in (e.get("name") or "").lower()
            ]
            return scored[:top_k]
        except Exception as e:
            logger.error("search_edges failed: %s", str(e)[:120])
            return []

    def get_node_and_edges(
        self, graph_id: str, node_uuid: str
    ) -> Dict[str, Any]:
        """Get a single node with all its edges."""
        all_nodes = self.get_all_nodes(graph_id)
        all_edges = self.get_all_edges(graph_id)
        node = next((n for n in all_nodes if n["uuid"] == node_uuid), None)
        if not node:
            return {}
        related = [
            e
            for e in all_edges
            if e["source_node_uuid"] == node_uuid or e["target_node_uuid"] == node_uuid
        ]
        return {**node, "related_edges": related}

    def delete_graph(self, graph_id: str) -> None:
        """Delete all nodes and edges for a graph."""
        try:
            client = get_client()
            client.table("kg_nodes").delete().eq("graph_id", graph_id).execute()
            client.table("kg_edges").delete().eq("graph_id", graph_id).execute()
        except Exception as e:
            logger.error("delete_graph failed: %s", str(e)[:120])

    def get_graph_stats(self, graph_id: str) -> Dict[str, Any]:
        """Return node and edge count for a graph."""
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        entity_types: set = set()
        for n in nodes:
            for label in (n.get("labels") or []):
                if label not in ("Entity", "Node"):
                    entity_types.add(label)
        return {
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "entity_types": list(entity_types),
        }

    # ─── Agent memory (conversation history) ─────────────────────────────────

    def store_memory(
        self,
        session_id: str,
        content: str,
        role: str = "user",
        agent_id: int = 0,
    ) -> None:
        """Store a memory entry with embedding."""
        embedding = GeminiService.get_instance().embed(content)
        client = get_client()
        try:
            client.table("agent_memory").insert(
                {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "role": role,
                    "content": content,
                    "embedding": embedding,
                }
            ).execute()
        except Exception as e:
            logger.warning("store_memory failed: %s", str(e)[:120])

    def retrieve_memory(
        self,
        session_id: str,
        query: str,
        agent_id: int = 0,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant memories via pgvector similarity."""
        try:
            embedding = GeminiService.get_instance().embed(query, task_type="retrieval_query")
            client = get_client()
            result = client.rpc(
                "search_agent_memory",
                {
                    "p_session_id": session_id,
                    "p_agent_id": agent_id,
                    "p_embedding": embedding,
                    "p_top_k": top_k,
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(
                "retrieve_memory pgvector RPC failed, falling back: %s", str(e)[:120]
            )
            # Fallback: return recent entries
            try:
                client = get_client()
                result = (
                    client.table("agent_memory")
                    .select("role,content,created_at")
                    .eq("session_id", session_id)
                    .eq("agent_id", agent_id)
                    .order("created_at", desc=True)
                    .limit(top_k)
                    .execute()
                )
                return result.data or []
            except Exception:
                return []

    # ─── Simulation steps ─────────────────────────────────────────────────────

    def store_simulation_step(
        self,
        simulation_id: str,
        round_num: int,
        step_data: Dict[str, Any],
        platform: str = "",
    ) -> None:
        """Store a simulation step to Supabase."""
        client = get_client()
        try:
            client.table("simulation_steps").insert(
                {
                    "simulation_id": simulation_id,
                    "round_num": round_num,
                    "platform": platform,
                    "step_data": step_data,
                }
            ).execute()
        except Exception as e:
            logger.warning("store_simulation_step failed: %s", str(e)[:120])

    def get_simulation_steps(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Retrieve all simulation steps."""
        try:
            client = get_client()
            result = (
                client.table("simulation_steps")
                .select("round_num,platform,step_data,created_at")
                .eq("simulation_id", simulation_id)
                .order("created_at")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error("get_simulation_steps failed: %s", str(e)[:120])
            return []


# Singleton
_memory_instance: Optional[SupabaseMemory] = None


def get_memory() -> SupabaseMemory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = SupabaseMemory()
    return _memory_instance
