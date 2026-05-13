-- ============================================================================
-- NeuralToolRouter — PostgreSQL Init Script
-- Runs automatically on first container start via docker-entrypoint-initdb.d
-- ============================================================================

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable uuid-ossp for UUID generation (fallback if not using gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
