-- ═══════════════════════════════════════════════════════════
-- MiroFish Lite — Supabase Database Setup
-- Run this SQL in your Supabase project SQL editor:
-- https://supabase.com/dashboard/project/yohzymtnlvdlrxomtdbs/sql
-- ═══════════════════════════════════════════════════════════

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Knowledge graph nodes (replaces Zep graph nodes)
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
CREATE INDEX IF NOT EXISTS kg_nodes_name_idx ON kg_nodes (name);
CREATE INDEX IF NOT EXISTS kg_nodes_embedding_idx
    ON kg_nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Step 3: Knowledge graph edges (replaces Zep graph edges)
CREATE TABLE IF NOT EXISTS kg_edges (
    id               BIGSERIAL PRIMARY KEY,
    graph_id         TEXT NOT NULL,
    edge_uuid        TEXT UNIQUE NOT NULL,
    name             TEXT,
    fact             TEXT,
    source_node_uuid TEXT,
    target_node_uuid TEXT,
    attributes       JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kg_edges_graph_id_idx ON kg_edges (graph_id);
CREATE INDEX IF NOT EXISTS kg_edges_source_idx ON kg_edges (source_node_uuid);
CREATE INDEX IF NOT EXISTS kg_edges_target_idx ON kg_edges (target_node_uuid);

-- Step 4: Agent conversation memory
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
CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
    ON agent_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Step 5: Simulation steps log
CREATE TABLE IF NOT EXISTS simulation_steps (
    id              BIGSERIAL PRIMARY KEY,
    simulation_id   TEXT NOT NULL,
    round_num       INT,
    platform        TEXT,
    step_data       JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sim_steps_sim_id_idx ON simulation_steps (simulation_id);

-- Step 6: pgvector RPC functions for semantic search

CREATE OR REPLACE FUNCTION search_kg_nodes(
    p_graph_id   TEXT,
    p_embedding  vector(768),
    p_top_k      INT DEFAULT 5
)
RETURNS TABLE (
    node_uuid   TEXT,
    name        TEXT,
    labels      TEXT[],
    summary     TEXT,
    attributes  JSONB,
    similarity  FLOAT
)
LANGUAGE sql STABLE AS $$
    SELECT
        node_uuid, name, labels, summary, attributes,
        1 - (embedding <=> p_embedding) AS similarity
    FROM kg_nodes
    WHERE graph_id = p_graph_id
      AND embedding IS NOT NULL
    ORDER BY embedding <=> p_embedding
    LIMIT p_top_k;
$$;

CREATE OR REPLACE FUNCTION search_agent_memory(
    p_session_id TEXT,
    p_agent_id   INT,
    p_embedding  vector(768),
    p_top_k      INT DEFAULT 3
)
RETURNS TABLE (
    role        TEXT,
    content     TEXT,
    created_at  TIMESTAMPTZ,
    similarity  FLOAT
)
LANGUAGE sql STABLE AS $$
    SELECT
        role, content, created_at,
        1 - (embedding <=> p_embedding) AS similarity
    FROM agent_memory
    WHERE session_id = p_session_id
      AND agent_id   = p_agent_id
      AND embedding IS NOT NULL
    ORDER BY embedding <=> p_embedding
    LIMIT p_top_k;
$$;
