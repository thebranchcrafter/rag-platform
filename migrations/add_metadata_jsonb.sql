-- Migration: Add JSONB metadata columns for multi-tenancy support
-- This migration adds metadata columns to both documents and document_chunks tables
-- and creates GIN indexes for efficient filtering

-- Step 1: Add metadata column to documents table
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'documents' 
        AND column_name = 'metadata'
    ) THEN
        ALTER TABLE documents 
        ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';
        
        RAISE NOTICE 'Added metadata column to documents table';
    ELSE
        RAISE NOTICE 'metadata column already exists in documents table';
    END IF;
END $$;

-- Step 2: Add metadata column to document_chunks table
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'document_chunks' 
        AND column_name = 'metadata'
    ) THEN
        ALTER TABLE document_chunks 
        ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';
        
        RAISE NOTICE 'Added metadata column to document_chunks table';
    ELSE
        RAISE NOTICE 'metadata column already exists in document_chunks table';
    END IF;
END $$;

-- Step 3: Create GIN index for metadata filtering on document_chunks
CREATE INDEX IF NOT EXISTS idx_chunks_metadata 
ON document_chunks USING gin(metadata);

-- Step 4: Backfill existing rows with empty metadata object
UPDATE documents 
SET metadata = '{}'::jsonb
WHERE metadata IS NULL;

UPDATE document_chunks 
SET metadata = '{}'::jsonb
WHERE metadata IS NULL;

-- Step 5: Remove old document_metadata column if it exists (optional cleanup)
-- Uncomment if you want to remove the old Text column
-- DO $$ 
-- BEGIN
--     IF EXISTS (
--         SELECT 1 FROM information_schema.columns 
--         WHERE table_name = 'documents' 
--         AND column_name = 'document_metadata'
--     ) THEN
--         ALTER TABLE documents DROP COLUMN document_metadata;
--         RAISE NOTICE 'Removed old document_metadata column';
--     END IF;
-- END $$;

-- Verification queries (run these to verify migration)
-- SELECT COUNT(*) FROM documents WHERE metadata IS NULL;  -- Should be 0
-- SELECT COUNT(*) FROM document_chunks WHERE metadata IS NULL;  -- Should be 0
-- \d+ document_chunks  -- Check index exists
