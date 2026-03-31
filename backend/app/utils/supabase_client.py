"""
Supabase client singleton + schema bootstrap.
Replaces all Zep graph storage with PostgreSQL + pgvector via Supabase.
"""

import logging
from typing import Optional

from supabase import create_client, Client

from ..config import Config

logger = logging.getLogger("mirofish.supabase_client")

_client: Optional[Client] = None

# SQL to create tables if not exist — run once on startup
BOOTSTRAP_SQL = """
-- Enable pgvector extension (requires Supabase project with pgvector enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge graph nodes (replaces Zep graph nodes)
CREATE TABLE IF NOT EXISTS kg_nodes (
    id          BIGSERIAL PRIMARY KEY,
    graph_id    TEXT NOT NULL,
    node_uuid   TEXT UNIQUE NOT NULL,
    name        TEXT,
    labels      TEXT[],
    summary     TEXT,
    attributes  JSONB DEFAULT '{}',
    embedding   vector(768),
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kg_nodes_graph_id_idx ON kg_nodes (graph_id);
CREATE INDEX IF NOT EXISTS kg_nodes_embedding_idx ON kg_nodes
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Knowledge graph edges (replaces Zep graph edges)
CREATE TABLE IF NOT EXISTS kg_edges (
    id              BIGSERIAL PRIMARY KEY,
    graph_id        TEXT NOT NULL,
    edge_uuid       TEXT UNIQUE NOT NULL,
    name            TEXT,
    fact            TEXT,
    source_node_uuid TEXT,
    target_node_uuid TEXT,
    attributes      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kg_edges_graph_id_idx ON kg_edges (graph_id);
CREATE INDEX IF NOT EXISTS kg_edges_source_idx ON kg_edges (source_node_uuid);
CREATE INDEX IF NOT EXISTS kg_edges_target_idx ON kg_edges (target_node_uuid);

-- Agent memory / conversation history
CREATE TABLE IF NOT EXISTS agent_memory (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    agent_id    INT  NOT NULL DEFAULT 0,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_memory_session_idx ON agent_memory (session_id, agent_id);
CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx ON agent_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Simulation steps log
CREATE TABLE IF NOT EXISTS simulation_steps (
    id              BIGSERIAL PRIMARY KEY,
    simulation_id   TEXT NOT NULL,
    round_num       INT,
    platform        TEXT,
    step_data       JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sim_steps_sim_id_idx ON simulation_steps (simulation_id);
"""


def get_client() -> Client:
    """Return the Supabase singleton client, initializing if needed."""
    global _client
    if _client is None:
        url = Config.SUPABASE_URL
        key = Config.SUPABASE_KEY
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured")
        _client = create_client(url, key)
        logger.info("Supabase client initialized: %s", url)
    return _client


def ensure_schema() -> None:
    """
    Bootstrap the database schema (idempotent).
    Called once on app startup via the Supabase RPC or direct SQL.

    Note: Supabase's Python client uses PostgREST API which does NOT support
    raw DDL. Schema must be created via the Supabase dashboard SQL editor,
    or during a migration step. This function logs the SQL for reference.
    """
    logger.info(
        "Schema bootstrap SQL (run in Supabase SQL editor if not already done):\n%s",
        BOOTSTRAP_SQL,
    )
