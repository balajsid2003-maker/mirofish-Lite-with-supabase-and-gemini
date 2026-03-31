-- ═══════════════════════════════════════════════════════════
-- MiroFish Lite — Schema Migration: vector 768 → 3072
-- Run this in your Supabase SQL editor AFTER running supabase_setup.sql
-- Only needed if you already ran supabase_setup.sql with vector(768)
-- ═══════════════════════════════════════════════════════════

-- Drop old indexes before altering columns
DROP INDEX IF EXISTS kg_nodes_embedding_idx;
DROP INDEX IF EXISTS agent_memory_embedding_idx;

-- Alter columns to new dimension
ALTER TABLE kg_nodes ALTER COLUMN embedding TYPE vector(768);
ALTER TABLE agent_memory ALTER COLUMN embedding TYPE vector(768);

-- Recreate indexes
CREATE INDEX IF NOT EXISTS kg_nodes_embedding_idx
    ON kg_nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
    ON agent_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Update RPC functions to use vector(768)
DROP FUNCTION IF EXISTS search_kg_nodes(TEXT, vector, INT);
DROP FUNCTION IF EXISTS search_agent_memory(TEXT, INT, vector, INT);

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
