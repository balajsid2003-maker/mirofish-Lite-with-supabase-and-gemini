"""
Supabase Graph Builder — replaces GraphBuilderService (Zep).
Extracts entities from text using Gemini, stores them in Supabase
kg_nodes and kg_edges tables. Fully async (threaded).
"""

import json
import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from .supabase_memory import get_memory
from ..utils.llm_client import LLMClient
from .text_processor import TextProcessor

logger = logging.getLogger("mirofish.supabase_graph_builder")

# How many text chunks to extract entities from per Gemini call (batching)
CHUNKS_PER_EXTRACTION_CALL = 5


class GraphInfo:
    """Graph summary returned after build."""

    def __init__(self, graph_id: str, node_count: int, edge_count: int, entity_types: List[str]):
        self.graph_id = graph_id
        self.node_count = node_count
        self.edge_count = edge_count
        self.entity_types = entity_types

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge graph extraction engine.
Extract entities and relationships from the provided text.
Return ONLY valid JSON. No markdown. No explanations.
"""

EXTRACTION_USER_PROMPT = """\
Text:
{text}

Ontology entity types allowed: {entity_types}
Edge types allowed: {edge_types}

Extract all entities and relationships you can find.
Return JSON:
{{
  "nodes": [
    {{"uuid": "<unique_id>", "name": "<entity name>", "labels": ["<EntityType>", "Entity"], "summary": "<1-2 sentence summary>", "attributes": {{}}}}
  ],
  "edges": [
    {{"uuid": "<unique_id>", "name": "<EDGE_TYPE>", "fact": "<relationship sentence>", "source_node_uuid": "<uuid of source node>", "target_node_uuid": "<uuid of target node>", "attributes": {{}}}}
  ]
}}
"""


class SupabaseGraphBuilderService:
    """
    Builds a knowledge graph from text using Gemini + Supabase.
    Replaces GraphBuilderService (Zep).
    """

    def __init__(self):
        self.llm = LLMClient()
        self.memory = get_memory()
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = CHUNKS_PER_EXTRACTION_CALL,
        use_lite_mode: bool = False,
    ) -> str:
        """Start async graph build. Returns task_id."""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"

        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "graph_id": graph_id,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )

        thread = threading.Thread(
            target=self._build_worker,
            args=(task_id, graph_id, text, ontology, chunk_size, chunk_overlap, batch_size, use_lite_mode),
            daemon=True,
        )
        thread.start()
        return task_id

    def _build_worker(
        self,
        task_id: str,
        graph_id: str,
        text: str,
        ontology: Dict[str, Any],
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        use_lite_mode: bool = False,
    ):
        """Worker thread: extract entities and store in Supabase."""
        try:
            self.task_manager.update_task(
                task_id, status=TaskStatus.PROCESSING, progress=5, message="Chunking text…"
            )

            # 1. Split text into chunks
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            logger.info("Graph build: %d chunks to process", total_chunks)

            self.task_manager.update_task(
                task_id, progress=10, message=f"Text split into {total_chunks} chunks"
            )

            # 2. Build ontology type lists for the prompt
            entity_types = [e.get("name", "") for e in ontology.get("entity_types", [])]
            edge_types = [e.get("name", "") for e in ontology.get("edge_types", [])]

            # 3. Batch extraction
            all_nodes: Dict[str, Dict] = {}  # uuid -> node
            all_edges: List[Dict] = []
            total_batches = max(1, -(-total_chunks // batch_size))  # ceiling division

            for batch_idx in range(0, total_chunks, batch_size):
                batch = chunks[batch_idx: batch_idx + batch_size]
                batch_text = "\n\n---\n\n".join(batch)
                batch_num = batch_idx // batch_size + 1

                progress = 10 + int((batch_num / total_batches) * 75)
                self.task_manager.update_task(
                    task_id,
                    progress=progress,
                    message=f"Extracting batch {batch_num}/{total_batches}…",
                )

                try:
                    prompt = EXTRACTION_USER_PROMPT.format(
                        text=batch_text[:6000],  # cap to avoid token overflow
                        entity_types=", ".join(entity_types),
                        edge_types=", ".join(edge_types),
                    )
                    result = self.llm.chat_json(
                        messages=[
                            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2,
                    )
                    for node in result.get("nodes", []):
                        if not node.get("uuid"):
                            node["uuid"] = str(uuid.uuid4())
                        all_nodes[node["uuid"]] = node
                    all_edges.extend(result.get("edges", []))

                except Exception as e:
                    logger.warning("Extraction batch %d failed: %s", batch_num, str(e)[:80])

            # 4. Store nodes and edges in Supabase
            self.task_manager.update_task(
                task_id, progress=85, message=f"Storing {len(all_nodes)} nodes…"
            )
            for node_data in all_nodes.values():
                node_data["node_uuid"] = node_data.pop("uuid", str(uuid.uuid4()))
                self.memory.store_node(graph_id, node_data)

            self.task_manager.update_task(
                task_id, progress=92, message=f"Storing {len(all_edges)} edges…"
            )
            for edge_data in all_edges:
                edge_data["edge_uuid"] = edge_data.pop("uuid", str(uuid.uuid4()))
                self.memory.store_edge(graph_id, edge_data)

            # 5. Final stats
            stats = self.memory.get_graph_stats(graph_id)
            self.task_manager.complete_task(
                task_id,
                {
                    "graph_id": graph_id,
                    "graph_info": stats,
                    "chunks_processed": total_chunks,
                },
            )
            logger.info(
                "Graph build complete: graph_id=%s nodes=%d edges=%d",
                graph_id,
                stats["node_count"],
                stats["edge_count"],
            )

        except Exception as e:
            import traceback
            self.task_manager.fail_task(task_id, f"{str(e)}\n{traceback.format_exc()}")

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Return full graph data (nodes + edges)."""
        nodes = self.memory.get_all_nodes(graph_id)
        edges = self.memory.get_all_edges(graph_id)
        node_map = {n["uuid"]: n.get("name", "") for n in nodes}

        edges_data = []
        for e in edges:
            edges_data.append(
                {
                    **e,
                    "source_node_name": node_map.get(e.get("source_node_uuid", ""), ""),
                    "target_node_name": node_map.get(e.get("target_node_uuid", ""), ""),
                }
            )

        return {
            "graph_id": graph_id,
            "nodes": nodes,
            "edges": edges_data,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def delete_graph(self, graph_id: str) -> None:
        """Delete all graph data from Supabase."""
        self.memory.delete_graph(graph_id)

    # ── Convenience alias to match old GraphBuilderService API ───────────────
    def create_graph(self, name: str) -> str:
        """Generate a new graph_id (no remote setup needed with Supabase)."""
        return f"mirofish_{uuid.uuid4().hex[:16]}"

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Ontology is stored in task metadata; no separate step needed."""
        logger.debug("set_ontology called for graph %s (no-op with Supabase)", graph_id)
