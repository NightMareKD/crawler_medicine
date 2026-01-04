-- Migration 001: Corpus Schema Extensions
-- Adds language annotation, Q&A pairs, bias tracking, and versioning support

-- =============================================
-- 0. Base Ingestion Tables (Queue + Storage Metadata)
-- =============================================

CREATE TABLE IF NOT EXISTS crawl_queue (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT,
    source_agency TEXT,
    priority TEXT,
    priority_score DOUBLE PRECISION,
    status TEXT NOT NULL,
    scheduled_time TIMESTAMPTZ,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    last_attempt_at TIMESTAMPTZ,
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    context_id TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_ingest (
    id TEXT PRIMARY KEY,
    url TEXT,
    content JSONB,
    provenance JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    processing_status JSONB DEFAULT '{}'::jsonb,
    assets JSONB DEFAULT '{}'::jsonb,
    asset_counts JSONB DEFAULT '{}'::jsonb,
    ocr JSONB DEFAULT '{}'::jsonb,
    priority TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ocr_queue (
    id TEXT PRIMARY KEY,
    context_id TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    priority TEXT,
    status TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    last_error TEXT,
    result JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    document_id TEXT NOT NULL,
    url TEXT,
    success BOOLEAN,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    details JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_crawl_queue_status_priority ON crawl_queue (status, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_queue_scheduled_time ON crawl_queue (scheduled_time);
CREATE INDEX IF NOT EXISTS idx_ocr_queue_status_created_at ON ocr_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_ocr_queue_status_priority ON ocr_queue (status, priority);

-- =============================================
-- 1. Extend raw_ingest table with language/annotation columns
-- =============================================

-- Ensure base columns exist even if raw_ingest was created earlier with a different schema.
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS url TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS content JSONB;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS provenance JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS processing_status JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS assets JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS asset_counts JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS ocr JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS priority TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS detected_language TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS language_confidence FLOAT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS is_romanized BOOLEAN DEFAULT FALSE;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS romanized_type TEXT; -- 'singlish', 'tamilish', 'english', null
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS translated_text JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '[]'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS intent TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS region TEXT;

-- =============================================
-- 2. Q&A Pairs Table
-- =============================================

CREATE TABLE IF NOT EXISTS qa_pairs (
    id TEXT PRIMARY KEY,
    
    -- Question fields
    question_text TEXT NOT NULL,
    question_language TEXT,  -- 'sinhala', 'tamil', 'english'
    question_is_romanized BOOLEAN DEFAULT FALSE,
    question_romanized_type TEXT, -- 'singlish', 'tamilish', null
    
    -- Answer fields
    answer_text TEXT NOT NULL,
    answer_language TEXT,
    
    -- Annotations
    intent TEXT,
    domain TEXT,
    entities JSONB DEFAULT '[]'::jsonb,
    
    -- Source tracking
    source_context_id TEXT REFERENCES raw_ingest(id),
    source_url TEXT,
    
    -- Review status
    verified BOOLEAN DEFAULT FALSE,
    reviewer_id TEXT,
    review_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 3. Corpus Statistics Table (Bias Tracking)
-- =============================================

CREATE TABLE IF NOT EXISTS corpus_statistics (
    id TEXT PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    
    -- Counts
    total_documents INTEGER DEFAULT 0,
    total_qa_pairs INTEGER DEFAULT 0,
    
    -- Language distribution
    language_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"sinhala": 1200, "tamil": 800, "english": 2000, "romanized": 500}
    
    -- Romanized breakdown
    romanized_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"singlish": 300, "tamilish": 150, "mixed": 50}
    
    -- Region distribution
    region_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"colombo": 500, "kandy": 200, "rural": 100}
    
    -- Domain distribution  
    domain_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"dengue": 400, "mental_health": 150, "opd": 300}
    
    -- Intent distribution
    intent_distribution JSONB DEFAULT '{}'::jsonb,
    
    -- Bias flags
    bias_alerts JSONB DEFAULT '[]'::jsonb,
    -- Example: [{"type": "underrepresented", "category": "tamil", "severity": "high"}]
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 4. Content Versions Table (Deduplication)
-- =============================================

CREATE TABLE IF NOT EXISTS content_versions (
    id TEXT PRIMARY KEY,
    context_id TEXT REFERENCES raw_ingest(id),
    content_hash TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    previous_version_id TEXT,
    changes_summary TEXT,
    content_diff JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 5. Indexes for Performance
-- =============================================

-- Language queries
CREATE INDEX IF NOT EXISTS idx_raw_ingest_language ON raw_ingest(detected_language);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_romanized ON raw_ingest(is_romanized) WHERE is_romanized = TRUE;
CREATE INDEX IF NOT EXISTS idx_raw_ingest_domain ON raw_ingest(domain);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_intent ON raw_ingest(intent);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_region ON raw_ingest(region);

-- Q&A queries
CREATE INDEX IF NOT EXISTS idx_qa_pairs_language ON qa_pairs(question_language);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_romanized ON qa_pairs(question_is_romanized) WHERE question_is_romanized = TRUE;
CREATE INDEX IF NOT EXISTS idx_qa_pairs_domain ON qa_pairs(domain);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_verified ON qa_pairs(verified);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_source ON qa_pairs(source_context_id);

-- Deduplication
CREATE INDEX IF NOT EXISTS idx_content_versions_hash ON content_versions(content_hash);
CREATE INDEX IF NOT EXISTS idx_content_versions_context ON content_versions(context_id);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_hash ON raw_ingest(content_hash);

-- Statistics
CREATE INDEX IF NOT EXISTS idx_corpus_stats_date ON corpus_statistics(snapshot_date DESC);

-- =============================================
-- 6. Triggers for updated_at
-- =============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_qa_pairs_updated_at ON qa_pairs;
CREATE TRIGGER update_qa_pairs_updated_at
    BEFORE UPDATE ON qa_pairs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
